"""The comments on data-corrupting pitfalls are inside the regions the docs show, the regions hold no plumbing, and
the router modules stand alone."""

import re

from app.demo.code_panel import regions_in
from app.settings import ROOT

PLUMBING = ["sqlite3", "lastrowid", "json.dumps", "ensure_ascii", "httpx2", "TimeoutException", "ConnectError",
            "strftime", "isoformat"]


def region(path: str, id: str) -> str:
    found = regions_in(path).get(id)
    assert found is not None, f"{path} has sjs:{id}"
    return found.code


def test_the_pitfall_comments_are_inside_the_regions() -> None:
    pitfalls = [
        ("app/routes/save_response.py", "save-response.server", ["The raw body, not a Pydantic model", "{} stays {}"]),
        ("app/routes/resume_progress.py", "resume-progress.server", ["The raw body, not a Pydantic model", "{} stays {}"]),
        ("app/routes/relational_storage.py", "relational-storage.server", ["The raw body, not a Pydantic model", "keys come from valueName"]),
        ("app/routes/creator_load_save.py", "creator-load-save.server", ["The raw body, not a Pydantic model", "{} stays {}"]),
        ("app/routes/variable_presets.py", "variable-presets.server", ["The raw body, not a Pydantic model", "{} stays {}"]),
        ("app/routes/validate_response.py", "validate-response.server", ["The raw body, not a Pydantic model", "fail closed"]),
        ("app/routes/lint_definition.py", "lint-definition.server", ["keeps {} as {}", "fail closed"]),
        ("app/routes/store_files.py", "store-files.server", ['"files[]"', "by the bytes, never the client's type",
                                                              "never by the client"]),
        ("app/routes/store_files.py", "store-files.download", ["404, not 403", "nosniff and sandbox"]),
        ("app/routes/choices_from_web.py", "choices-from-web.server", ["the browser can't call a service without CORS"]),
        ("app/routes/dashboard.py", "dashboard.server", ["as stored", "ISO 8601 UTC strings compare as dates"]),
        ("app/routes/extract_from_paper.py", "extract-from-paper.server", ["JSON with base64", "logged by status only"]),
        ("app/routes/load_definition_variables_data.py", "load-definition-variables-data.server", ["tojson"]),
        ("app/routes/fill_together.py", "fill-together.server", ["real session check", "refused handshake"]),
        ("app/routes/edit_together.py", "edit-together.server", ["editing together is for editors"]),
    ]
    for path, id, comments in pitfalls:
        code = region(path, id)
        for comment in comments:
            assert comment in code, f"sjs:{id} explains: {comment}"


def test_server_regions_show_no_plumbing() -> None:
    for path in sorted((ROOT / "app" / "routes").glob("*.py")):
        for id, found in regions_in(path.relative_to(ROOT).as_posix()).items():
            for token in PLUMBING:
                assert token not in found.code, f"sjs:{id} shows {token}"
            assert "app.state" not in found.code, f"sjs:{id} reaches into app.state: use a dependency"


def test_router_modules_stand_alone() -> None:
    for path in sorted((ROOT / "app" / "routes").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"^from app\.routes|^import app\.routes|^from \. ", source, re.M), f"{path.name} imports a router"
        assert "os.environ" not in source and "getenv" not in source, f"{path.name} reads the environment"
        if path.name != "__init__.py":
            assert source.startswith('"""'), f"{path.name} starts with what it serves"
            assert "router = APIRouter()" in source, path.name


def test_no_module_reads_the_environment_but_settings() -> None:
    for path in sorted((ROOT / "app").rglob("*.py")):
        if path.name != "settings.py":
            assert "os.environ" not in path.read_text(encoding="utf-8"), path
