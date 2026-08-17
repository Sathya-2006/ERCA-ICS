import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME = PROJECT_ROOT / "runtime"
STORE = RUNTIME / "incidents.json"
RUNTIME.mkdir(exist_ok=True)
LOCK = threading.Lock()


def _load():
    if not STORE.exists():
        return []
    try:
        return json.loads(STORE.read_text())
    except Exception:
        return []


def _save(items):
    STORE.write_text(json.dumps(items, indent=2))


def now():
    return datetime.now(timezone.utc).isoformat()


def create_incident(payload):
    with LOCK:
        items = _load()
        incident = {
            "id": "INC-" + uuid.uuid4().hex[:8].upper(),
            "created_at": now(),
            "updated_at": now(),
            "status": "OPEN",
            "notification_status": "UNREAD",
            **payload,
        }
        items.insert(0, incident)
        _save(items)
        return incident


def list_incidents():
    with LOCK:
        return _load()


def get_incident(incident_id):
    return next((x for x in _load() if x["id"] == incident_id), None)


def update_incident(incident_id, **changes):
    with LOCK:
        items = _load()
        for item in items:
            if item["id"] == incident_id:
                item.update(changes)
                item["updated_at"] = now()
                _save(items)
                return item
    return None


def mark_read(incident_id):
    return update_incident(incident_id, notification_status="READ")
