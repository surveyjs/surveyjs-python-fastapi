"""python -m scripts.check [--complete]: does this repo still match the integration docs (server-integration-v4)?

The manifest's files and regions, the region rules (no nesting, short, no plumbing in server regions), shared/
against its SHA256SUMS, the SurveyJS pins against shared/surveyjs-version.json, the service revision against
docker-compose.yml, the requirements pins, and the README's docs links. With --complete (CI, the end of a run)
all 18 examples must be in the manifest.
"""

import sys

if sys.version_info < (3, 14):
    print(f"Python 3.14 or newer is required (this is {sys.version.split()[0]})", file=sys.stderr)
    raise SystemExit(1)

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.demo.code_panel import regions_in  # noqa: E402  (after the version check)

STEPS = ["save-response", "load-definition-variables-data", "resume-progress", "store-files", "choices-from-web",
         "async-functions", "relational-storage", "fill-together", "dashboard", "creator-load-save", "creator-uploads",
         "ai-translation", "variable-presets", "edit-together", "validate-response", "lint-definition", "server-pdf",
         "extract-from-paper"]
REGION_SOURCES = ["app/routes", "app/relay", "shared/client"]
RELAY_FILES = ["app/routes/fill_together.py", "app/routes/edit_together.py"]
MAX_REGION_LINES = 24
MAX_RELAY_REGION_LINES = 60
DOCS = "https://surveyjs.io/documentation/backend-integration-python-fastapi"
# This platform's plumbing: a server region calls app/integration/ or app/db.py for these instead of showing them
PLUMBING = ["sqlite3", "lastrowid", "json.dumps", "ensure_ascii", "httpx2", "TimeoutException", "ConnectError",
            "strftime", "isoformat"]
MARKERS = {".py": (r"^\s*#\s*region\b", r"^\s*#\s*endregion\b"), ".js": (r"^\s*//\s*#region\b", r"^\s*//\s*#endregion\b")}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def files(folder: str) -> list[str]:
    return sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def check(complete: bool) -> list[str]:
    errors: list[str] = []

    # ---- shared/: CONTRACT, UPSTREAM and the hashes (shared/ is a copy: fixes go to surveyjs-php-laravel)
    contract = read("shared/CONTRACT").strip() if (ROOT / "shared/CONTRACT").is_file() else ""
    if contract != "server-integration-v4":
        errors.append(f'shared/CONTRACT must read server-integration-v4, found "{contract}"')
    upstream = read("shared/UPSTREAM").strip() if (ROOT / "shared/UPSTREAM").is_file() else ""
    if not re.fullmatch(r"surveyjs/surveyjs-php-laravel@[0-9a-f]{7,40}", upstream):
        errors.append(f'shared/UPSTREAM must name the copied commit (surveyjs/surveyjs-php-laravel@<sha>), found "{upstream}"')
    expected = {line[66:]: line[:64] for line in read("shared/SHA256SUMS").splitlines() if line.strip()}
    actual = {path.removeprefix("shared/"): hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
              for path in files("shared") if path not in ("shared/SHA256SUMS", "shared/UPSTREAM")}
    for path, digest in expected.items():
        if path not in actual:
            errors.append(f"shared/{path} is listed in shared/SHA256SUMS but missing")
        elif actual[path] != digest:
            errors.append(f"shared/{path} differs from shared/SHA256SUMS: shared/ is a copy, fix it in surveyjs-php-laravel"
                          " (on Windows, check that .gitattributes keeps LF line endings)")
    errors += [f"shared/{path} is not listed in shared/SHA256SUMS" for path in actual if path not in expected]

    # ---- versions: the manifest, shared/surveyjs-version.json and package.json pin the same SurveyJS
    manifest = json.loads(read("surveyjs-integration.json"))
    version = json.loads(read("shared/surveyjs-version.json"))["version"]
    if manifest.get("surveyjsVersion") != version:
        errors.append(f"surveyjsVersion in the manifest is {manifest.get('surveyjsVersion')}, shared/surveyjs-version.json says {version}")
    pinned = json.loads(read("package.json")).get("devDependencies", {}).get("survey-core")
    if pinned != version:
        errors.append(f"package.json pins survey-core to {pinned}, expected exactly {version} (the lint spec imports it)")
    if (ROOT / "package-lock.json").is_file():
        locked = json.loads(read("package-lock.json")).get("packages", {}).get("node_modules/survey-core", {}).get("version")
        if locked != version:
            errors.append(f"package-lock.json has survey-core {locked}, expected {version}: run npm install")
    if manifest.get("serverSideWorkflows") != "service":
        errors.append(f'serverSideWorkflows must be "service", found {manifest.get("serverSideWorkflows")}')
    service = re.search(r"surveyjs-server\.git#([0-9a-f]{40})", read("docker-compose.yml"))
    if not service or manifest.get("surveyjsService") != f"surveyjs/surveyjs-server@{service.group(1)}":
        errors.append("surveyjsService in the manifest differs from the surveyjs build context in docker-compose.yml")

    # ---- requirements: runtime pins only, exact versions; the dev file adds pytest to them
    for line in read("requirements.txt").splitlines():
        if line.strip() and not line.startswith("#") and not re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", line.strip()):
            errors.append(f"requirements.txt: {line.strip()} is not pinned with ==")
    dev = [line.strip() for line in read("requirements-dev.txt").splitlines() if line.strip() and not line.startswith("#")]
    if not dev or dev[0] != "-r requirements.txt" or not any(re.fullmatch(r"pytest==[0-9.]+", line) for line in dev):
        errors.append("requirements-dev.txt must start with -r requirements.txt and pin pytest with ==")

    # ---- the manifest's files
    for step in manifest["steps"]:
        for role, path in step.get("files", {}).items():
            if not (ROOT / path).is_file():
                errors.append(f"{step['slug']}: {role} file {path} is missing")
        if step.get("status") not in ("done", "not-in-repo"):
            errors.append(f"{step['slug']}: unknown status {step.get('status')}")

    # ---- regions: markers balanced, each region once, short, listed, and in its example's client or server files
    found: dict[str, list[str]] = {}
    for path in (path for folder in REGION_SOURCES for path in files(folder) if path[path.rfind("."):] in MARKERS):
        opening, closing = MARKERS[path[path.rfind("."):]]
        open_at = 0
        for number, line in enumerate(read(path).splitlines(), start=1):
            if re.match(opening, line):
                if open_at:
                    errors.append(f"{path}:{number}: a region opens inside another region")
                open_at = number
            elif re.match(closing, line):
                if not open_at:
                    errors.append(f"{path}:{number}: endregion without region")
                open_at = 0
        if open_at:
            errors.append(f"{path}:{open_at}: a region is never closed")
        for region_id, region in regions_in(path).items():
            found.setdefault(region_id, []).append(path)
            lines = region.end - region.start + 1
            limit = MAX_RELAY_REGION_LINES if path in RELAY_FILES else MAX_REGION_LINES
            if lines > limit:
                errors.append(f"Region sjs:{region_id} in {path} has {lines} lines (at most {limit})")
            if region.count > 1:
                errors.append(f"Region sjs:{region_id} appears {region.count} times in {path}")
            if path.startswith("app/"):
                errors += [f"Region sjs:{region_id} in {path} shows {token}: move it into app/integration/ or app/db.py"
                           for token in PLUMBING if token in region.code]
    listed = {region_id for step in manifest["steps"] for region_id in step["regions"]}
    for step in manifest["steps"]:
        sources = [path for role, path in step["files"].items() if role == "client" or role.startswith("server")]
        for region_id in step["regions"]:
            where = found.get(region_id, [])
            if len(where) != 1:
                errors.append(f"{step['slug']}: region sjs:{region_id} found {len(where)} times, expected exactly once")
            elif where[0] not in sources:
                errors.append(f"{step['slug']}: region sjs:{region_id} is in {where[0]}, not in the example's client or server file")
    errors += [f"Region sjs:{region_id} in {where[0]} is not listed in the manifest"
               for region_id, where in found.items() if region_id not in listed]

    # ---- README: the prose links the docs page exactly twice (the generated table always holds it)
    prose = re.sub(r"<!-- steps:start[\s\S]*?<!-- steps:end -->", "", read("README.md"))
    links = [m.group(1) or m.group(2) for m in re.finditer(r"\]\((https?://[^)\s]+)\)|<(https?://[^>\s]+)>", prose)]
    links = [url for url in links if url.startswith(DOCS) or re.match(r"https?://(www\.)?surveyjs\.io(/documentation)?/backend-integration(?!/examples)", url)]
    if len(links) != 2 or any(url != DOCS for url in links):
        errors.append(f"README.md must link to the docs exactly twice outside the example table, both to {DOCS}; found {len(links)}")

    if complete:
        slugs = {step["slug"] for step in manifest["steps"]}
        errors += [f"Example {slug} is missing from surveyjs-integration.json" for slug in STEPS if slug not in slugs]
    return errors


def main() -> int:
    errors = check("--complete" in sys.argv[1:])
    for error in errors:
        print(f"ERROR  {error}", file=sys.stderr)
    if errors:
        return 1
    steps = len(json.loads(read("surveyjs-integration.json"))["steps"])
    print(f"OK: {steps} examples, regions, shared/, versions and pins are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
