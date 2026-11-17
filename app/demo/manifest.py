"""Demo only: surveyjs-integration.json, the list of examples the catalog, the example pages and the docs read."""

import json
from functools import cache
from typing import Any

from app.settings import ROOT


@cache
def read_manifest() -> dict[str, Any]:
    return json.loads((ROOT / "surveyjs-integration.json").read_text(encoding="utf-8"))


def find_step(slug: str) -> dict[str, Any] | None:
    """The manifest's example with this slug, or None."""
    return next((step for step in read_manifest()["steps"] if step["slug"] == slug), None)


def docs_url(docs: str, step: dict[str, Any] | None = None) -> str:
    """The docs page, at the example's anchor when one is given."""
    return docs + (f"#{step['anchor']}" if step else "")
