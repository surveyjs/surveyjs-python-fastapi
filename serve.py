"""Start the app: `python serve.py`, or `python serve.py --reload` while you edit.

It checks the Python version and the port before anything else, prints which checkout is serving, then runs
uvicorn with the proxy headers on. `uvicorn app.main:app` and `fastapi dev` work too, without these checks.
"""

import sys

if sys.version_info < (3, 14):
    print(f"Python 3.14 or newer is required (this is {sys.version.split()[0]})", file=sys.stderr)
    raise SystemExit(1)

import os
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def port_answers(port: int) -> bool:
    """Is something already answering on the port? Don't rely on uvicorn's bind error: on Windows it comes after
    the app's startup (which seeds the database), and a server on 0.0.0.0 and another on 127.0.0.1 can both bind."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def git_build() -> str | None:
    """`<branch>@<short commit>` of this checkout, or None without git."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=2, check=True).stdout.strip()
    try:
        return f"{git('rev-parse', '--abbrev-ref', 'HEAD')}@{git('rev-parse', '--short', 'HEAD')}"
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    from app.settings import Settings  # reads .env and the environment, nothing else

    settings = Settings()
    if port_answers(settings.app_port):
        print(f"Port {settings.app_port} is already in use. Another copy of this app (another checkout or branch?) "
              "may be running. Stop it, or set APP_PORT.", file=sys.stderr)
        return 1

    build = settings.surveyjs_build or git_build()
    if build:
        os.environ["SURVEYJS_BUILD"] = build   # the app reads it once; with --reload, the worker inherits it
    print(f"Serving {ROOT}{f' ({build})' if build else ''} on http://127.0.0.1:{settings.app_port}", flush=True)

    import uvicorn
    from uvicorn.config import LOGGING_CONFIG

    # uvicorn's log format for the app's own loggers too (app, app.surveyjs, app.relay…), to stderr
    log_config = {**LOGGING_CONFIG, "loggers": {**LOGGING_CONFIG["loggers"],
                                                "app": {"handlers": ["default"], "level": "INFO", "propagate": False}}}
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload="--reload" in sys.argv[1:],
        proxy_headers=True,                                  # X-Forwarded-Proto and -For, from these addresses:
        forwarded_allow_ips=settings.forwarded_allow_ips,
        log_config=log_config,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
