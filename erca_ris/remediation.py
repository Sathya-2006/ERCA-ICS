import shutil
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME = PROJECT_ROOT / "runtime"
BACKUPS = RUNTIME / "backups"
RUNTIME.mkdir(exist_ok=True)
BACKUPS.mkdir(exist_ok=True)


SAFE_FIXES = {
    "Payment gateway connection timed out": {
        "file": "sample_app/services/payment/payment_service.py",
        "old": 'gateway_timeout = 1',
        "new": 'gateway_timeout = 10',
        "reason": "The demo timeout threshold is corrected so the simulated gateway does not immediately fail."
    },
    "Email provider unavailable": {
        "file": "sample_app/services/notification/email_service.py",
        "old": 'email_provider_available = False',
        "new": 'email_provider_available = True',
        "reason": "The demo provider availability flag is restored."
    },
    "Inventory service unavailable": {
        "file": "sample_app/services/inventory/inventory_service.py",
        "old": 'inventory_service_available = False',
        "new": 'inventory_service_available = True',
        "reason": "The demo inventory dependency availability flag is restored."
    },
    "Object storage service unavailable": {
        "file": "sample_app/services/storage/storage_service.py",
        "old": 'storage_available = False',
        "new": 'storage_available = True',
        "reason": "The demo storage dependency availability flag is restored."
    },
    "Database connection pool exhausted": {
        "file": "sample_app/services/orders/order_service.py",
        "old": 'connection_pool_available = False',
        "new": 'connection_pool_available = True',
        "reason": "The demo database pool availability flag is restored."
    },
    "Search service request timed out": {
        "file": "sample_app/services/search/search_service.py",
        "old": 'search_timeout = True',
        "new": 'search_timeout = False',
        "reason": "The demo search timeout flag is disabled."
    },
    "Report database query timed out": {
        "file": "sample_app/services/reports/report_service.py",
        "old": 'database_query_timeout = True',
        "new": 'database_query_timeout = False',
        "reason": "The demo report query timeout flag is disabled."
    },
    "Authentication token validation failed": {
        "file": "sample_app/services/auth/auth_service.py",
        "old": 'token_expired = True',
        "new": 'token_expired = False',
        "reason": "The demo token-expiry simulation is disabled."
    },
}


def get_fix(error):
    return SAFE_FIXES.get(error)


def apply_safe_fix(error):
    fix = get_fix(error)
    if not fix:
        return {"ok": False, "message": "No deterministic safe fix is registered for this error."}

    path = PROJECT_ROOT / fix["file"]
    if not path.exists():
        return {"ok": False, "message": f"Source file not found: {fix['file']}"}

    source = path.read_text()
    if fix["old"] not in source:
        return {"ok": False, "message": "Expected source pattern was not found. No change was made."}

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUPS / f"{path.name}.{timestamp}.bak"
    shutil.copy2(path, backup)

    path.write_text(source.replace(fix["old"], fix["new"], 1))

    test = subprocess.run(
        ["python", "-m", "pytest", "-q"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )

    if test.returncode != 0:
        shutil.copy2(backup, path)
        return {
            "ok": False,
            "rolled_back": True,
            "message": "Validation failed; source was automatically restored.",
            "test_output": (test.stdout + "\n" + test.stderr)[-4000:],
        }

    return {
        "ok": True,
        "rolled_back": False,
        "file": fix["file"],
        "backup": str(backup.relative_to(PROJECT_ROOT)),
        "reason": fix["reason"],
        "test_output": (test.stdout + "\n" + test.stderr)[-4000:],
    }
