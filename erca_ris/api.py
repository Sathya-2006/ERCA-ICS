"""
Backward-compatible launcher.

Historically this project was started with:
    python erca_ris/api.py
which broke because of how the package was executed (relative imports only
work when run as a package). This module now runs correctly both ways:

    python -m erca_ris.api        # recommended, matches package imports
    uvicorn app.main:app --reload # preferred for development (auto-reload)

Both start the same FastAPI application defined in app/main.py.
"""
from __future__ import annotations

import uvicorn


def main():
    uvicorn.run("app.main:app", host="127.0.0.1", port=5001, reload=False)


if __name__ == "__main__":
    main()
