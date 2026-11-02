"""Constants for Todo Sync."""
from datetime import timedelta

DOMAIN = "todo_sync"
CONF_LIST_A = "list_a"
CONF_LIST_B = "list_b"
SYNC_INTERVAL = timedelta(minutes=5)
DEBOUNCE_SECONDS = 5
# Don't create the same item again while the other list hasn't shown our first add yet.
PENDING_TTL = timedelta(minutes=30)
STORAGE_VERSION = 1
