"""Two-way sync of open items between two to-do entities.

State kept between runs: links between an item in list A and its twin in list B, with the
status and summary they had at the last sync. That is what lets us tell "checked off just
now" from "checked off a year ago" and "deleted" from "never synced".
"""
from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEBOUNCE_SECONDS, DOMAIN, PENDING_TTL, STORAGE_VERSION, SYNC_INTERVAL

_LOGGER = logging.getLogger(__name__)

DONE = "completed"
OPEN = "needs_action"
SIDES = ("a", "b")


def _key(summary: str | None) -> str:
    return " ".join((summary or "").split()).casefold()


def _clean(summary: str | None) -> str:
    return " ".join((summary or "").split())


class TodoSyncer:
    def __init__(self, hass: HomeAssistant, entry_id: str, list_a: str, list_b: str) -> None:
        self.hass = hass
        self.entities = {"a": list_a, "b": list_b}
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self._links: list[dict[str, Any]] = []
        # pending[side] = {key: iso time} for items we created on that side but haven't seen yet
        self._pending: dict[str, dict[str, str]] = {"a": {}, "b": {}}
        self._lock = asyncio.Lock()
        self._unsubs: list[CALLBACK_TYPE] = []
        self._debouncer = Debouncer(
            hass, _LOGGER, cooldown=DEBOUNCE_SECONDS, immediate=False, function=self.async_sync
        )

    async def async_start(self) -> None:
        data = await self._store.async_load() or {}
        self._links = data.get("links", [])
        self._pending = data.get("pending", {"a": {}, "b": {}})
        self._unsubs.append(
            async_track_state_change_event(self.hass, list(self.entities.values()), self._on_change)
        )
        self._unsubs.append(async_track_time_interval(self.hass, self._on_timer, SYNC_INTERVAL))
        self.hass.async_create_task(self._debouncer.async_call())

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._debouncer.async_cancel()

    @callback
    def _on_change(self, event: Event) -> None:
        self.hass.async_create_task(self._debouncer.async_call())

    async def _on_timer(self, now: datetime) -> None:
        await self._debouncer.async_call()

    # --- service helpers -------------------------------------------------------------

    async def _items(self, side: str) -> dict[str, dict] | None:
        entity = self.entities[side]
        state = self.hass.states.get(entity)
        if state is None or state.state == "unavailable":
            return None
        resp = await self.hass.services.async_call(
            "todo", "get_items", {}, target={"entity_id": entity}, blocking=True, return_response=True
        )
        return {i["uid"]: i for i in resp[entity]["items"]}

    async def _call(self, side: str, service: str, data: dict[str, Any]) -> None:
        await self.hass.services.async_call(
            "todo", service, data, target={"entity_id": self.entities[side]}, blocking=True
        )

    async def _save(self) -> None:
        await self._store.async_save({"links": self._links, "pending": self._pending})

    # --- the sync --------------------------------------------------------------------

    async def async_sync(self) -> None:
        async with self._lock:
            try:
                await self._sync()
            except Exception:  # noqa: BLE001 - one bad run must not kill the timer
                _LOGGER.exception("Todo sync between %s and %s failed", *self.entities.values())

    async def _sync(self) -> None:
        items = {s: await self._items(s) for s in SIDES}
        if items["a"] is None or items["b"] is None:
            _LOGGER.debug("A list is unavailable, skipping sync")
            return
        changed = False
        other = {"a": "b", "b": "a"}
        pending_before = {k: dict(v) for k, v in self._pending.items()}

        # 1. Existing links: propagate status/summary changes, handle deletions.
        # Items whose link ends in this run must not be treated as new in step 2.
        handled: dict[str, set[str]] = {"a": set(), "b": set()}
        keep_links = []
        for link in self._links:
            cur = {s: items[s].get(link[f"{s}_uid"]) for s in SIDES}
            if cur["a"] is None or cur["b"] is None:
                # Deleted on one side: check it off on the other (never delete for the user).
                for s in SIDES:
                    if cur[s] is not None:
                        if cur[s]["status"] == OPEN:
                            await self._call(s, "update_item", {"item": cur[s]["uid"], "status": DONE})
                        cur[s]["status"] = DONE
                        handled[s].add(cur[s]["uid"])
                changed = True
                continue
            status, summary = link["status"], link["summary"]
            for s in SIDES:
                o = other[s]
                if cur[s]["status"] != status and cur[o]["status"] == status:
                    await self._call(o, "update_item", {"item": cur[o]["uid"], "status": cur[s]["status"]})
                    cur[o]["status"] = status = cur[s]["status"]
                    changed = True
                if _clean(cur[s]["summary"]) != summary and _clean(cur[o]["summary"]) == summary:
                    await self._call(o, "update_item", {"item": cur[o]["uid"], "rename": _clean(cur[s]["summary"])})
                    cur[o]["summary"] = summary = _clean(cur[s]["summary"])
                    changed = True
            if cur["a"]["status"] != cur["b"]["status"]:
                # Both changed differently since last sync: checked off wins.
                for s in SIDES:
                    if cur[s]["status"] != DONE:
                        await self._call(s, "update_item", {"item": cur[s]["uid"], "status": DONE})
                status = DONE
                changed = True
            if status == DONE:
                changed = True  # done on both sides: forget the link, history stays history
                for s in SIDES:
                    handled[s].add(cur[s]["uid"])
                continue
            keep_links.append({"a_uid": cur["a"]["uid"], "b_uid": cur["b"]["uid"], "status": status, "summary": summary})
        self._links = keep_links

        # 2. Open items without a twin.
        linked = {s: {l[f"{s}_uid"] for l in self._links} for s in SIDES}
        now = dt_util.utcnow()
        linked_keys = {_key(l["summary"]) for l in self._links}
        for s in SIDES:
            self._pending[s] = {
                k: t
                for k, t in self._pending[s].items()
                if k not in linked_keys and now - datetime.fromisoformat(t) < PENDING_TTL
            }
        for s in SIDES:
            o = other[s]
            for item in list(items[s].values()):
                if item["status"] != OPEN or item["uid"] in linked[s] or item["uid"] in handled[s]:
                    continue
                key = _key(item["summary"])
                unlinked_o = [i for i in items[o].values() if i["uid"] not in linked[o] and _key(i["summary"]) == key]
                twin = next((i for i in unlinked_o if i["status"] == OPEN), None)
                if twin is None and unlinked_o:
                    # Exists checked off on the other side (e.g. Keep history): reopen it.
                    twin = unlinked_o[0]
                    await self._call(o, "update_item", {"item": twin["uid"], "status": OPEN})
                    twin["status"] = OPEN
                if twin is None:
                    if key in self._pending[o]:
                        continue  # created earlier, not visible yet
                    await self._call(o, "add_item", {"item": _clean(item["summary"])})
                    self._pending[o][key] = now.isoformat()
                    changed = True
                    continue
                for side in SIDES:
                    self._pending[side].pop(key, None)
                self._links.append(
                    {f"{s}_uid": item["uid"], f"{o}_uid": twin["uid"], "status": OPEN, "summary": _clean(item["summary"])}
                )
                linked[s].add(item["uid"])
                linked[o].add(twin["uid"])
                changed = True

        # Items we just created get linked on the next run, which their own state change triggers.
        if changed or self._pending != pending_before:
            await self._save()
