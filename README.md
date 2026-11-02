# Todo Sync for Home Assistant

Two-way sync between **any two Home Assistant to-do lists**. Add an item on your phone in one app and it shows
up in the other, check it off in the store and it's checked off everywhere.

Typical use: keep a store's shopping list (for example [ICA](https://github.com/douglasstier/ha-ica)) in sync with
**Google Keep**, Todoist, Microsoft To Do, Bring!, the local HA shopping list, or anything else that exposes a
`todo.*` entity.

## What gets synced

| You do this in one list | The other list does this |
|---|---|
| Add an item | The item is added |
| Check an item off | It is checked off |
| Un-check an item | It is opened again |
| Rename an item | It is renamed |
| Delete an item | It is **checked off**, never deleted |

Only **open** items are synced. Lists like Google Keep keep hundreds of old checked-off items as history, and
Todo Sync leaves that history alone: nothing checked off is ever copied across.

**No duplicates.** If you add "Milk" and the other list already has "Milk" checked off from last week, that
item is re-opened instead of a second "Milk" being added. Matching ignores case and extra spaces.

**Nothing is ever deleted.** Removing an item on one side only checks it off on the other side, so a mistake in
one app can't wipe the other list.

## How it works

- A sync runs a few seconds after either list changes, and every 5 minutes as a safety net.
- Todo Sync remembers which item in list A belongs to which item in list B, and the status and name they had
  at the last sync. That is how it can tell "checked off just now" from "checked off a year ago", and "deleted"
  from "never synced". Once an item is done on both sides, the pair is forgotten.
- If both sides changed the same item differently between two syncs, *checked off* wins.
- If one of the lists is unavailable, the sync waits and tries again later.
- The memory is stored in `.storage/todo_sync.<entry id>` and removed when you delete the integration.

How fast changes arrive depends on the integrations behind the lists. Todo Sync reacts within seconds once
Home Assistant sees a change, but for example Google Keep Sync polls Keep every 15 minutes.

## Requirements

- Home Assistant 2025.1 or later.
- Two to-do entities that support adding and updating items. Lists that can't rename or delete items still
  work, the rest of the sync just skips those steps.

## Installation

**HACS (recommended)**

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/douglasstier/ha-todo-sync`, category *Integration*.
2. Install **Todo Sync** and restart Home Assistant.

**Manual**

Copy `custom_components/todo_sync` into your `config/custom_components/` folder and restart Home Assistant.

## Setup

*Settings → Devices & services → Add integration → Todo Sync*, then pick the two lists. The order doesn't matter.

On the first sync, all open items from both lists are merged. Add the integration again to sync more pairs of lists.

## Example: ICA ⇄ Google Keep

1. Install [ICA Shopping Lists](https://github.com/douglasstier/ha-ica) and
   [Google Keep Sync](https://github.com/watkins-matt/home-assistant-google-keep-sync), and expose one list from each.
2. Add Todo Sync with `todo.ica_<your list>` and `todo.google_keep_<your list>`.
3. Write the shopping list in Keep at home, and tick items off in the ICA app in the store.

## License

MIT, see [LICENSE](LICENSE).
