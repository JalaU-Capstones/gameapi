"""Export the FastAPI OpenAPI schema to a JSON file.

Run with: uv run python scripts/export_openapi.py
Output: .docs/contracts/openapi/openapi.json
"""

from __future__ import annotations

import json
from pathlib import Path

from gameapi.main import app

OUTPUT = Path(".docs/contracts/openapi/openapi.json")


def main() -> None:
    spec = app.openapi()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(spec, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT} ({len(json.dumps(spec))} bytes)")


if __name__ == "__main__":
    main()
