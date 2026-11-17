"""python -m scripts.readme: regenerates the README's example table (between the steps markers) from
surveyjs-integration.json."""

import sys

if sys.version_info < (3, 14):
    print(f"Python 3.14 or newer is required (this is {sys.version.split()[0]})", file=sys.stderr)
    raise SystemExit(1)

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = "https://surveyjs.io/documentation/backend-integration-python"


def main() -> int:
    manifest = json.loads((ROOT / "surveyjs-integration.json").read_text(encoding="utf-8"))
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")

    def file(step: dict, role: str) -> str:
        path = step["files"].get(role)
        return f"[`{path}`]({path})" if path else "—"

    def run(step: dict) -> str:
        return f"[{step['page']}]({manifest['live']}{step['page']})" if manifest.get("live") else f"`{step['page']}`"

    rows = ["| Example | Run | Server | Client | Page | Licence |", "|---|---|---|---|---|---|"]
    rows += [f"| [{step['title']}]({DOCS}#{step['anchor']}) | {run(step)} | {file(step, 'server')} | {file(step, 'client')} "
             f"| {file(step, 'page')} | {step['licence']} |" for step in manifest["steps"]]

    marker = re.compile(r"(<!-- steps:start[^>]*-->)[\s\S]*?(<!-- steps:end -->)")
    if not marker.search(readme):
        print("README.md needs <!-- steps:start --> and <!-- steps:end --> markers.", file=sys.stderr)
        return 1
    readme_path.write_text(marker.sub(lambda m: f"{m.group(1)}\n" + "\n".join(rows) + f"\n{m.group(2)}", readme),
                           encoding="utf-8", newline="\n")
    print(f"Updated the example table in README.md ({len(manifest['steps'])} examples).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
