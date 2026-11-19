"""python -m scripts.contract [--steps save-response,choices-from-web] [--smoke]

Runs the shared contract test (shared/contract-tests/run.mjs), or with --smoke the smoke test
(shared/smoke/run.mjs), against a fresh DATA_DIR and this app on a free port, then stops the app and exits with
the test's code. Works on Windows and Linux; needs Node 22+ on PATH for the test itself.

Passed through from the environment: SERVICE (off or on; off points the app at a port nothing listens on), AI (off or stub), VALIDATE_RESPONSES, LINT_DEFINITIONS,
DEMO_MODE, SURVEYJS_SERVICE_URL and the AI_* settings. With AI=stub, start the stub first (docker-compose.ci.yml)
and set AI_BASE_URL=http://127.0.0.1:3020/v1 AI_API_KEY=stub AI_MODEL=stub. The relays run in the app, so
RELAY_URL and EDIT_RELAY_URL are its ws:// origin.
"""

import sys

if sys.version_info < (3, 14):
    print(f"Python 3.14 or newer is required (this is {sys.version.split()[0]})", file=sys.stderr)
    raise SystemExit(1)

import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Off means off: the app's settings.env and .env must not switch translation or extraction on. A space overrides
# them with nothing.
AI_SETTINGS = ["AI_API_KEY", "SURVEYJS_AI_PROVIDER", "SURVEYJS_AI_MODEL", "SURVEYJS_OLLAMA_BASE_URL", "OPENAI_API_KEY",
               "ANTHROPIC_API_KEY"]
SWITCHES = ["VALIDATE_RESPONSES", "LINT_DEFINITIONS", "DEMO_MODE"]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for(url: str, app: subprocess.Popen[bytes], seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if app.poll() is not None:
            raise RuntimeError(f"The app stopped with exit code {app.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as answer:
                if answer.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"The app did not answer {url} within {seconds} s")


def main() -> int:
    args = sys.argv[1:]
    smoke = "--smoke" in args
    steps = re.search(r"--steps[= ](\S+)", " ".join(args))
    node = shutil.which("node")
    if node is None:
        print("Node.js 22 or newer is needed on PATH to run the contract test (shared/contract-tests/run.mjs).", file=sys.stderr)
        return 1

    data_dir = Path(tempfile.mkdtemp(prefix="surveyjs-contract-"))
    port = free_port()
    origin = f"http://127.0.0.1:{port}"
    env = {**os.environ, "DATA_DIR": str(data_dir), "APP_PORT": str(port), "APP_HOST": "127.0.0.1",
           "SERVICE": os.environ.get("SERVICE", "off"), "AI": os.environ.get("AI", "off"),
           "SURVEYJS_BUILD": os.environ.get("SURVEYJS_BUILD", "contract"), "PYTHONUNBUFFERED": "1"}
    for switch in SWITCHES:   # what the test expects is what the app runs with, whatever settings.env and .env say
        env[switch] = os.environ.get(switch) or "false"
    if env["AI"] != "stub":
        env.update({name: " " for name in AI_SETTINGS})
    if env["SERVICE"] == "off":   # off means not running, also when a service answers on 3010: a port nothing listens on
        env["SURVEYJS_SERVICE_URL"] = f"http://127.0.0.1:{free_port()}"

    log = (data_dir.parent / f"{data_dir.name}.log").open("w+b")
    app = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    code = 1
    try:
        wait_for(f"{origin}/up", app)
        print(f"Started the app on port {port} (DATA_DIR {data_dir})", flush=True)
        test = "shared/smoke/run.mjs" if smoke else "shared/contract-tests/run.mjs"
        code = subprocess.call([node, test, *([f"--steps={steps.group(1)}"] if steps else [])], cwd=ROOT,
                               env={**env, "BASE_URL": origin, "RELAY_URL": f"ws://127.0.0.1:{port}",
                                    "EDIT_RELAY_URL": f"ws://127.0.0.1:{port}"})
    except RuntimeError as error:
        print(error, file=sys.stderr)
    finally:
        app.terminate()
        try:
            app.wait(timeout=10)
        except subprocess.TimeoutExpired:
            app.kill()
            app.wait()
        log.seek(0)
        output = log.read().decode("utf-8", "replace")
        log.close()
        if code != 0 and output:
            print(f"--- the app's output\n{output[-4000:]}")
        Path(log.name).unlink(missing_ok=True)
        shutil.rmtree(data_dir, ignore_errors=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
