"""serve.py refuses a port that something answers on, with the meta prompt's message, before any startup work:
uvicorn's own bind error comes after the lifespan, which would already have seeded the database."""

import os
import socket
import subprocess
import sys
from pathlib import Path

from app.settings import ROOT


def test_serve_refuses_a_busy_port_before_any_startup_work(tmp_path: Path) -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        data_dir = tmp_path / "data"
        env = {**os.environ, "APP_PORT": str(port), "DATA_DIR": str(data_dir), "SURVEYJS_BUILD": "test@0000000"}
        result = subprocess.run([sys.executable, "serve.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert result.stderr.strip() == (f"Port {port} is already in use. Another copy of this app (another checkout or branch?) "
                                     "may be running. Stop it, or set APP_PORT.")
    assert not data_dir.exists(), "nothing was created or seeded"


def test_the_version_check_comes_first() -> None:
    source = (ROOT / "serve.py").read_text(encoding="utf-8")
    assert source.index("sys.version_info < (3, 14)") < source.index("from app")
    for script in ("scripts/check.py", "scripts/contract.py", "scripts/readme.py", "tests/conftest.py"):
        text = (ROOT / script).read_text(encoding="utf-8")
        assert "Python 3.14 or newer is required (this is" in text, script
