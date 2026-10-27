"""Start the Wooju server. Used by the desktop app (as a bundled sidecar) and by developers.

    wooju-server --port 8765
    wooju-server --mcp        # the Claude connection (stdio), started by Claude

When frozen by PyInstaller, the built UI and the Brain template are inside the
bundle; their locations are passed to the app through environment variables
before the app module is imported.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="wooju-server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--mcp", action="store_true", help="serve the Brain to Claude over stdio")
    args = parser.parse_args(argv)

    if args.mcp:
        from app.mcp_server import run_stdio

        run_stdio()
        return

    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        os.environ.setdefault("WOOJU_WEB_DIST", str(Path(bundle) / "web"))
        os.environ.setdefault("WOOJU_TEMPLATE_DIR", str(Path(bundle) / "template"))
        os.environ.setdefault("WOOJU_SAMPLES_DIR", str(Path(bundle) / "samples"))

    import uvicorn

    from app.main import app  # imported after the paths above are set

    uvicorn.run(app, host=args.host, port=args.port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
