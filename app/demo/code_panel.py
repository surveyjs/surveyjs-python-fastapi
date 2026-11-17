"""Demo only: the Code tab. It shows the files that just ran: each JSON definition, then each region the
manifest lists for the example, dedented, with a link to its lines on GitHub. Python marks regions with
`# region sjs:<id>` … `# endregion`, JavaScript with `// #region sjs:<id>` … `// #endregion`.
scripts/check.py reads regions with the same function."""

import re
from dataclasses import dataclass
from typing import Any

from app.demo.manifest import read_manifest
from app.settings import ROOT

_MARKERS = {
    ".py": (re.compile(r"^\s*#\s*region\s+sjs:(\S+)"), re.compile(r"^\s*#\s*endregion\b")),
    ".js": (re.compile(r"^\s*//\s*#region\s+sjs:(\S+)"), re.compile(r"^\s*//\s*#endregion\b")),
}
_LANGUAGES = {".py": "python", ".js": "javascript", ".json": "json"}


@dataclass
class Region:
    id: str
    start: int   # the first line inside the markers, 1-based
    end: int     # the last line inside the markers
    code: str
    count: int = 1


def _suffix(path: str) -> str:
    return path[path.rfind("."):]


def regions_in(path: str) -> dict[str, Region]:
    """Every region in a file of the repository, by id."""
    markers = _MARKERS.get(_suffix(path))
    if markers is None:
        return {}
    opening, closing = markers
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    regions: dict[str, Region] = {}
    open_id, open_line = None, 0
    for number, line in enumerate(lines, start=1):
        if (found := opening.match(line)) is not None:
            open_id, open_line = found.group(1), number
        elif open_id is not None and closing.match(line):
            if open_id in regions:
                regions[open_id].count += 1
            else:
                regions[open_id] = Region(open_id, open_line + 1, number - 1, _dedent(lines[open_line:number - 1]))
            open_id = None
    return regions


def _dedent(lines: list[str]) -> str:
    indents = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    indent = min(indents, default=0)
    return "\n".join(line[indent:] for line in lines)


def _github(github: str, path: str) -> str:
    return f"{github}/blob/{read_manifest()['branch']}/{path}"


def code_definitions(github: str, step: dict[str, Any]) -> list[dict[str, str]]:
    """The JSON definitions, shown collapsed above the regions."""
    return [{"path": path, "code": (ROOT / path).read_text(encoding="utf-8").strip(), "url": _github(github, path)}
            for role, path in step["files"].items() if role.startswith("definition")]


def code_panel(github: str, step: dict[str, Any]) -> list[dict[str, str]]:
    """The regions the manifest lists for an example, from its client file and every server* file, in manifest order."""
    panel = []
    for role, path in step["files"].items():
        if role != "client" and not role.startswith("server"):
            continue
        for region_id, region in regions_in(path).items():
            if region_id in step["regions"]:
                panel.append({
                    "id": region_id,
                    "role": "client" if role == "client" else "server",
                    "path": path,
                    "language": _LANGUAGES.get(_suffix(path), "plaintext"),
                    "code": region.code,
                    "url": f"{_github(github, path)}#L{region.start}-L{region.end}",
                })
    return panel
