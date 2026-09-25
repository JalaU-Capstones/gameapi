"""Entry point for `python -m gameapi`."""

import uvicorn

from gameapi.core.config import settings


def main() -> None:
    uvicorn.run(
        "gameapi.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.env == "development",
        log_level="info",
    )


if __name__ == "__main__":
    main()
