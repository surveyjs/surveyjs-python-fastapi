"""The pages: every example renders with its module, the import map and window.SURVEYJS_PAGE; inline JSON can't end
its <script>; the layout's ids and blocks are where the reference puts them; /shared serves only its four folders
with JavaScript MIME types; and behind a TLS proxy the page's URLs are https and wss."""

import asyncio
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.demo.manifest import read_manifest
from app.main import create_app
from tests.conftest import Api, make_settings, page_config, start_app

STEPS = read_manifest()["steps"]
SLUGS = [step["slug"] for step in STEPS]
START_OVER = ["save-response", "load-definition-variables-data", "resume-progress", "store-files", "choices-from-web",
              "async-functions", "relational-storage", "validate-response", "extract-from-paper"]
SPECIFIERS = ["survey-core", "survey-core/collaboration", "survey-core/i18n", "survey-js-ui", "survey-creator-core",
              "survey-creator-core/collaboration", "survey-creator-js", "survey-analytics", "chart.js", "@kurkle/color",
              "lodash/debounce", "highlight.js/lib/core", "highlight.js/lib/languages/python"]


def import_map(html: str) -> dict:
    return json.loads(re.search(r'<script type="importmap">(.*?)</script>', html).group(1))


def stylesheets(html: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="([^"]+)">', html)


def test_every_example_renders_its_module_after_the_shared_ui_with_the_import_map_and_the_page_config(api: Api) -> None:
    version = read_manifest()["surveyjsVersion"]
    for step in STEPS:
        r = api.get(step["page"])
        assert r.status_code == 200, step["slug"]
        html = r.text
        scripts = re.findall(r'<script type="module" src="([^"]+)">', html)
        assert scripts == ["/shared/ui/code-highlight.js", "/shared/ui/page-tabs.js", f"/{step['files']['client']}"], step["slug"]
        imports = import_map(html)["imports"]
        for specifier in SPECIFIERS:
            assert specifier in imports, f"{step['slug']}: {specifier}"
        assert imports["survey-core"] == f"https://unpkg.com/survey-core@{version}/fesm/survey-core.mjs"
        assert html.index('<script type="importmap">') < html.index('<script type="module"')
        config = page_config(html)
        assert (config["slug"], config["version"]) == (step["slug"], version)
        assert list(config["relay"]) == ["fill", "edit"] and config["relay"]["fill"]["port"] == 8000
        for role in (role for role in step["files"] if role.startswith("definition")):
            assert config[role], f"{step['slug']}: {role}"
        assert f"<title>{step['title']} · SurveyJS + FastAPI</title>" in html


def test_a_script_tag_in_a_stored_definition_or_a_query_value_cant_end_the_inline_script(api: Api) -> None:
    definition = {"title": "</script><script>alert(1)</script>", "elements": [{"type": "text", "name": "q1", "title": "é & <b>"}]}
    with api.db() as conn:
        conn.execute("UPDATE forms SET json = ? WHERE key = 'work-order'", (json.dumps(definition),))
    html = api.get("/examples/extract-from-paper").text
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e" in html
    assert page_config(html)["definition"] == definition
    record = api.get("/examples/fill-together?record=%3C%2Fscript%3E%3Cb%3E").text
    assert "</script><b>" not in record and "&lt;/script&gt;&lt;b&gt;" in record


def test_start_over_is_on_exactly_the_nine_pages_between_the_other_actions_and_the_component(api: Api) -> None:
    for slug in SLUGS:
        html = api.get(f"/examples/{slug}").text
        assert ('id="start-over"' in html) == (slug in START_OVER), slug
        if slug in START_OVER:
            assert html.index('id="start-over"') < html.index('id="component"'), slug
    assert 'id="start-over"' in api.get("/claim").text
    assert '<button id="start-over" type="button" disabled' in api.get("/examples/resume-progress").text


def test_the_layout_ids_one_docs_link_and_about_where_the_reference_renders_it(api: Api, tmp_path: Path) -> None:
    ids = ["page-header", "side-panel", "panel-close", "panel-tabs", "panel-tabs-thumb", "hood", "panel-description", "try",
           "panel-requests", "readouts", "notes", "show-demo-requests", "clear-requests", "requests-empty", "requests",
           "panel-stored", "stored-updated", "stored", "main-tabs", "panel-toggle", "panel-dot", "page-tabs", "panel-demo",
           "component", "panel-code", "request-row", "stored-section", "note", "requests-count", "stored-dot"]
    for step in STEPS:
        html = api.get(f"/examples/{step['slug']}").text
        for id in ids:
            assert f'id="{id}"' in html, f"{step['slug']}: #{id}"
        assert html.count(">Documentation</a>") == 1, step["slug"]
        assert f'href="https://surveyjs.io/documentation/backend-integration-python-fastapi#{step["anchor"]}"' in html
        about = '<div class="space-y-2 text-sm text-gray-600">' in html
        assert about == (step["slug"] == "extract-from-paper"), f"{step['slug']}: the about block"
        assert ("require a developer license" in html) == step["licence"].startswith("Commercial"), step["slug"]
        assert html.count("<details data-code-section open") == len(step["regions"]), f"{step['slug']}: one section per region"
    with start_app(tmp_path, demo_mode=True) as demo:
        for slug in ("fill-together", "edit-together"):
            assert "The invite link carries your sandbox ID" in demo.get(f"/examples/{slug}").text, f"{slug} in demo mode"


def test_the_code_tab_shows_python_regions_with_github_line_links(api: Api) -> None:
    html = api.get("/examples/save-response").text
    assert '<code class="language-python block !bg-transparent p-4">' in html
    assert "/blob/main/app/routes/save_response.py#L" in html
    assert "sjs:save-response.server" in html and "sjs:save-response.client" in html


def test_the_catalog_the_pdf_loading_page_and_claim(api: Api) -> None:
    catalog = api.get("/").text
    assert "<title>Python Backend Integration with FastAPI · SurveyJS</title>" in catalog
    assert "Step-by-Step Python Backend Integration with FastAPI" in catalog
    assert "Build a Python Backend for&nbsp;Your SurveyJS Forms" in catalog
    assert ">Python integration guide</a>" in catalog
    assert catalog.count(">Run Example</a>") == 18
    assert not re.search(r"\bPHP\b|Laravel", catalog)
    assert "Generating the PDF..." in api.get("/examples/server-pdf/loading").text
    claim = api.get("/claim").text
    assert "window.FORM_DEFINITION = {" in claim
    assert 'window.FORM_VARIABLES = {"user": {"name": "Alice Martin", "plan": "premium"}};' in claim
    for path in ("/", "/examples/save-response", "/examples/server-pdf/loading"):
        assert '<link rel="canonical" href="http://testserver' in api.get(path).text, path


def test_no_page_text_names_php_laravel_or_artisan(api: Api) -> None:
    for slug in SLUGS:
        html = re.sub(r"<pre[\s\S]*?</pre>", "", api.get(f"/examples/{slug}").text)
        html = re.sub(r"languages/php|php\.min\.js", "", html)
        assert not re.search(r"\bPHP\b|Laravel|artisan|Express\b|Node\.js backend", html), slug


def test_shared_serves_its_four_folders_with_their_types_and_nothing_else(api: Api) -> None:
    for path, type in (("/shared/ui/page-tabs.js", "text/javascript"), ("/shared/client/host.js", "text/javascript"),
                       ("/shared/samples/support-help.svg", "image/svg+xml"), ("/shared/ui/fonts/lato/LatoLatin-Bold.woff2", "font/woff2"),
                       ("/shared/definitions/dashboard.json", "application/json"), ("/shared/ui/theme.css", "text/css"),
                       ("/static/css/site.css", "text/css")):
        r = api.get(path)
        assert r.status_code == 200 and r.headers["content-type"].split(";")[0] == type, path
    for path in ("/shared/seed/forms.json", "/shared/contract-tests/run.mjs", "/shared/CONTRACT", "/shared/ui/",
                 "/shared/%2e%2e/pyproject.toml", "/shared/..%2fpyproject.toml"):
        assert api.get(path).status_code == 404, path


def test_dot_dot_paths_sent_raw_answer_404(data_dir: Path) -> None:
    app = create_app(make_settings(data_dir))
    for path in ("/shared/../pyproject.toml", "/shared/client/../../pyproject.toml", "/shared/ui/../../.env"):
        status: list[int] = []

        async def send(message: dict, status: list[int] = status) -> None:
            if message["type"] == "http.response.start":
                status.append(message["status"])

        async def receive() -> dict:
            return {"type": "http.request", "body": b""}

        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
                 "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"", "headers": [],
                 "server": ("testserver", 80), "client": ("127.0.0.1", 1), "state": {}}
        asyncio.run(app(scope, receive, send))   # the path as written: httpx would resolve the dots
        assert status == [404], path


def test_x_forwarded_proto_https_gives_https_urls_and_wss_relays(data_dir: Path) -> None:
    app = create_app(make_settings(data_dir))
    proxied = ProxyHeadersMiddleware(app, trusted_hosts="*")   # what uvicorn runs with proxy_headers=True
    with TestClient(proxied, base_url="http://demo.example.com") as client:
        headers = {"X-Forwarded-Proto": "https", "Cookie": "demo_user=alice"}
        html = client.get("/examples/fill-together", headers=headers).text
        assert '<link rel="canonical" href="https://demo.example.com/examples/fill-together">' in html
        assert page_config(html)["relay"]["fill"]["url"] == "wss://demo.example.com"
        assert '<link rel="canonical" href="https://demo.example.com/">' in client.get("/", headers=headers).text
        plain = client.get("/examples/edit-together", headers={"Cookie": "demo_user=alice"}).text
        assert page_config(plain)["relay"]["edit"]["url"] == "ws://demo.example.com"


def test_relay_urls_win_when_set(tmp_path: Path) -> None:
    with start_app(tmp_path, relay_url="wss://relay.example.com", edit_relay_url="wss://edit.example.com") as api:
        relay = page_config(api.get("/examples/edit-together").text)["relay"]
        assert (relay["fill"]["url"], relay["edit"]["url"]) == ("wss://relay.example.com", "wss://edit.example.com")


def test_the_stylesheets_come_in_the_meta_prompts_order(api: Api) -> None:
    def names(path: str) -> list[str]:
        return [re.sub(r"^https://unpkg\.com/(@?[^@]+)@[^/]+/", r"\1/", href) for href in stylesheets(api.get(path).text)]
    head = ["/shared/ui/fonts.css", "/static/css/site.css"]
    highlight = "@highlightjs/cdn-assets/styles/github-dark.min.css"
    assert names("/examples/save-response") == [*head, "survey-core/survey-core.min.css", "survey-core/collaboration.min.css",
                                                "survey-core/themes/adapters/tailwind4.min.css", "/shared/ui/survey-overrides.css", highlight]
    assert names("/examples/creator-load-save") == [*head, "survey-core/survey-core.min.css",
                                                    "survey-creator-core/survey-creator-core.min.css",
                                                    "survey-creator-core/collaboration.min.css",
                                                    "survey-core/themes/adapters/tailwind4.min.css", highlight]
    assert names("/examples/dashboard") == [*head, "survey-core/survey-core.min.css", "survey-analytics/survey.analytics.min.css",
                                            "survey-core/themes/adapters/tailwind4.min.css", highlight]
    assert ".sd-theme-root { --sjs2-typography-font-family-text: var(--font-sans); }" in api.get("/examples/dashboard").text
    assert names("/examples/creator-load-save?form")[2] == "survey-core/survey-core.min.css"
    assert api.get("/").text.count('rel="preload" as="font"') == 4


def test_the_build_line_shows_when_surveyjs_build_is_set(tmp_path: Path) -> None:
    with start_app(tmp_path, surveyjs_build="main@abc1234") as api:
        assert "Running main@abc1234" in api.get("/").text
        assert "Running main@abc1234" in api.get("/examples/dashboard").text


def test_health_needs_no_database(tmp_path: Path) -> None:
    with start_app(tmp_path) as api:
        api.settings.database_path.unlink(missing_ok=True)
        assert (api.get("/up").status_code, api.get("/up").json()) == (200, {"status": "ok"})
        assert not api.settings.database_path.exists()


def test_fill_and_edit_together_add_their_record_and_form_to_the_page_config(api: Api) -> None:
    assert 'window.SURVEYJS_PAGE.formId = "contact-team";' in api.get("/examples/edit-together?form=contact-team").text
    assert 'window.SURVEYJS_PAGE.formId = "support-team";' in api.get("/examples/edit-together").text
    assert 'window.SURVEYJS_PAGE.record = "new";' in api.get("/examples/fill-together?record=new").text
