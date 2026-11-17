"""Demo only: the import map and the stylesheets every example page loads, built once at startup.

The shared ES modules (shared/client/*.js, shared/ui/*.js) import bare specifiers ("survey-core",
"lodash/debounce"). No Python package carries SurveyJS's browser builds, so the import map points every
specifier at unpkg: the SurveyJS packages at the version in shared/surveyjs-version.json, the others at
the pins below. One place pins every page. To self-host them, copy each package's fesm/ files into
static/vendor/ and point UNPKG at "/static/vendor" (README: Front end).
"""

import json
from functools import cache
from typing import Any

from app.settings import ROOT

UNPKG = "https://unpkg.com"

# Every SurveyJS specifier the shared modules and the SurveyJS builds import: [package, its browser ES module],
# each checked in https://unpkg.com/<package>@<version>/?meta (the package.json "exports" "import" entries)
SURVEYJS_SPECIFIERS = {
    "survey-core": ("survey-core", "fesm/survey-core.mjs"),
    "survey-core/collaboration": ("survey-core", "fesm/collaboration/index.mjs"),
    "survey-core/i18n": ("survey-core", "fesm/i18n/index.mjs"),
    "survey-js-ui": ("survey-js-ui", "fesm/survey-js-ui.mjs"),
    "survey-creator-core": ("survey-creator-core", "fesm/survey-creator-core.mjs"),
    "survey-creator-core/collaboration": ("survey-creator-core", "fesm/collaboration.mjs"),
    "survey-creator-js": ("survey-creator-js", "fesm/survey-creator-js.mjs"),
    "survey-analytics": ("survey-analytics", "fesm/survey.analytics.mjs"),
}

# The other packages. chart.js and @kurkle/color are the versions survey-analytics allows (^4.5.1), as in the
# reference's lock file. highlight.js's own es/ files re-export its CommonJS lib/ (they are for bundlers), so a
# browser gets no default export: @highlightjs/cdn-assets is the same release built as browser ES modules.
HIGHLIGHT = f"{UNPKG}/@highlightjs/cdn-assets@11.12.0"
THIRD_PARTY = {
    "chart.js": f"{UNPKG}/chart.js@4.5.1/dist/chart.js",
    "@kurkle/color": f"{UNPKG}/@kurkle/color@0.3.4/dist/color.esm.js",
    "lodash/debounce": f"{UNPKG}/lodash-es@4.18.1/debounce.js",
    "highlight.js/lib/core": f"{HIGHLIGHT}/es/core.min.js",
    **{f"highlight.js/lib/languages/{language}": f"{HIGHLIGHT}/es/languages/{language}.min.js"
       for language in ("csharp", "javascript", "json", "php", "python", "typescript")},
}

HIGHLIGHT_THEME = f"{HIGHLIGHT}/styles/github-dark.min.css"
"""highlight.js's github-dark theme, for the Code tab."""

FONTS = [f"/shared/ui/fonts/lato/LatoLatin-{weight}.woff2" for weight in ("Regular", "Medium", "Semibold", "Bold")]


@cache
def surveyjs_version() -> str:
    """The SurveyJS version every page pins (shared/surveyjs-version.json)."""
    return json.loads((ROOT / "shared" / "surveyjs-version.json").read_text(encoding="utf-8"))["version"]


def _surveyjs(package: str, file: str) -> str:
    return f"{UNPKG}/{package}@{surveyjs_version()}/{file}"


@cache
def import_map() -> dict[str, Any]:
    imports = {specifier: _surveyjs(package, file) for specifier, (package, file) in SURVEYJS_SPECIFIERS.items()}
    return {"imports": {**imports, **THIRD_PARTY}}


@cache
def stylesheets() -> dict[str, list[str]]:
    """The SurveyJS styles per page theme, in the order the pages need them (after the site stylesheet)."""
    core = _surveyjs("survey-core", "survey-core.min.css")
    adapter = _surveyjs("survey-core", "themes/adapters/tailwind4.min.css")
    return {
        "survey": [core, _surveyjs("survey-core", "collaboration.min.css"), adapter, "/shared/ui/survey-overrides.css"],
        "creator": [core, _surveyjs("survey-creator-core", "survey-creator-core.min.css"),
                    _surveyjs("survey-creator-core", "collaboration.min.css"), adapter],
        "dashboard": [core, _surveyjs("survey-analytics", "survey.analytics.min.css"), adapter],
    }
