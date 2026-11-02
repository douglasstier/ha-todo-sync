"""Todo Sync: keep the open items of two to-do lists in sync."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_LIST_A, CONF_LIST_B
from .sync import TodoSyncer

type TodoSyncConfigEntry = ConfigEntry[TodoSyncer]


async def async_setup_entry(hass: HomeAssistant, entry: TodoSyncConfigEntry) -> bool:
    syncer = TodoSyncer(hass, entry.entry_id, entry.data[CONF_LIST_A], entry.data[CONF_LIST_B])
    await syncer.async_start()
    entry.runtime_data = syncer
    entry.async_on_unload(syncer.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TodoSyncConfigEntry) -> bool:
    return True


async def async_remove_entry(hass: HomeAssistant, entry: TodoSyncConfigEntry) -> None:
    from homeassistant.helpers.storage import Store

    from .const import DOMAIN, STORAGE_VERSION

    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
