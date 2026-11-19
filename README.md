# SurveyJS + Python: the backend integration examples on FastAPI

This is the Python code behind [Integrate SurveyJS with Python](https://surveyjs.io/documentation/backend-integration-fastapi), as a FastAPI application you can run example by example. Each example of that page has a page here that runs the real SurveyJS component against these routes, with a short "Try this" list, a live request log, a "What the server stored" panel and the code that just ran. SurveyJS has no backend of its own, so treat these as starting points for your own app.

- SurveyJS demos: [app.demos.surveyjs.io](https://app.demos.surveyjs.io)
- Backend integration examples on the SurveyJS website: [surveyjs.io/backend-integration/examples](https://surveyjs.io/backend-integration/examples)
- The same examples for other platforms: [PHP (Laravel)](https://github.com/surveyjs/surveyjs-php-laravel), [ASP.NET Core](https://github.com/surveyjs/surveyjs-aspnet-core), [Node.js (Express)](https://github.com/surveyjs/surveyjs-nodejs-express), [Python (Django)](https://github.com/surveyjs/surveyjs-python-django), [Next.js](https://github.com/surveyjs/surveyjs-nextjs), [Java (Spring Boot)](https://github.com/surveyjs/surveyjs-java-spring-boot)

There is no hosted catalog for this repository yet.

## Run it

You need Python 3.14 or later. Docker runs the SurveyJS service for the four Run Server-Side Workflows examples, and Node.js 22 or later is only for the browser tests and the CSS build (see [Prerequisites](#prerequisites)).

```powershell
git clone https://github.com/surveyjs/surveyjs-python-fastapi.git
cd surveyjs-python-fastapi
py -3.15 -m venv .venv                 # or: python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python serve.py                        # http://127.0.0.1:8000
```

```bash
git clone https://github.com/surveyjs/surveyjs-python-fastapi.git
cd surveyjs-python-fastapi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python serve.py                        # http://127.0.0.1:8000
```

`python serve.py` creates and seeds `storage/database.sqlite` on its first start. While you work on the code, run `python serve.py --reload`: uvicorn restarts the app when a file changes. FastAPI developers often type `fastapi dev` or `uvicorn app.main:app` instead; both work, but they skip the port check and the build line below.

- **Fill Forms Together** and **Edit Forms Together** use WebSocket relays that run inside the app, on its port (`/ws/rooms/<id>` and `/ws/forms/<id>`). There is nothing else to start.
- **Run Server-Side Workflows** (validate, lint, PDF, extract) call the SurveyJS service, [SurveyJS Server](https://github.com/surveyjs/surveyjs-server). Start it with `docker compose up -d surveyjs` (it listens on `http://localhost:3010`), set `VALIDATE_RESPONSES=true` and `LINT_DEFINITIONS=true` in `settings.env` to switch Validate Responses and Lint JSON Schemas on, then restart the app. Extract Responses from Documents also needs an AI provider for the service (`SURVEYJS_AI_PROVIDER` in `settings.env`, its key in `.env`, which you copy from `.env.example`).
- The tests:
  - `python -m pytest`: a few seconds, no browser, no network, no service (it is mocked); warnings are errors.
  - `python -m scripts.contract`: the shared contract test against a fresh database (`SERVICE=on` with the service running; `--smoke` for the smoke test; `--steps save-response,dashboard` for some examples).
  - `npm ci`, `npx playwright install chromium` once, then `npm run test:browser`: the shared Playwright specs.
  - `python -m scripts.check --complete`: the manifest, the regions, `shared/` and the pins.

`python serve.py` checks that nothing answers on the port first, then prints the folder it serves and its `<branch>@<commit>`:

```text
Serving C:\src\surveyjs-python-fastapi (main@4a96b83) on http://127.0.0.1:8000
```

### Prerequisites

- **Python 3.14 or later** (3.15 recommended). `serve.py`, the scripts and the tests stop at once on an older one: "Python 3.14 or newer is required (this is 3.13.5)". A missing package shows up as pip's own error at `pip install -r requirements.txt`.
- **Docker** for the SurveyJS service (`docker compose up -d surveyjs`). Without it, the four Run Server-Side Workflows examples answer `503` "SurveyJS service is not running at http://localhost:3010", and everything else works.
- **Node.js 22 or later**, only for the browser tests and the CSS build. `npm ci` on an older Node stops with npm's own `EBADENGINE` error (`engines` in `package.json`, `engine-strict` in `.npmrc`). Running the app never needs Node.

On Windows:

- Install Python 3.14 or 3.15 from [python.org](https://www.python.org/downloads/), with `py install 3.15` (the Python install manager), or with `winget install Python.Python.3.15`.
- `python` may be the Microsoft Store stub (`…\WindowsApps\python.exe`), which opens the Store instead of running. `py -3.15 -m venv .venv` avoids it; inside the activated venv, `python` is the venv's.
- If PowerShell refuses to run `Activate.ps1`, allow local scripts once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- After installing Python or Node, restart your editor, not only its terminal: VS Code's terminals inherit VS Code's environment. To refresh the current PowerShell terminal instead:

  ```powershell
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
  py --list
  ```

- Don't install `fastapi[standard]` or `uvicorn[standard]` on Python 3.15 for Windows: their extras pull in PyYAML, which has no wheel for it yet and fails to build. `requirements.txt` pins `uvicorn` and `websockets` without extras, so `--reload` uses uvicorn's own file watcher.
- Set a variable for one run like this, or put it in `settings.env`:

  ```powershell
  $env:APP_PORT=8001; python serve.py
  ```

  ```bash
  APP_PORT=8001 python serve.py
  ```

On Windows, uvicorn reports a busy port only after the app has started up (and seeded the database), and a second server can bind a port another server listens on while the first keeps answering. So `serve.py` connects to the port first and stops with "Port 8000 is already in use. Another copy of this app (another checkout or branch?) may be running. Stop it, or set APP_PORT."

### Stop everything

`Ctrl+C` in the terminal (with `--reload`, the reloader and its worker stop together), then `docker compose down` for the service. To find a server left running in another terminal or checkout:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess
Stop-Process -Id <OwningProcess>
```

```bash
lsof -i :8000
kill <PID>
```

### Run a branch or a PR

- Check the branch out in its own folder, with `git worktree add ../surveyjs-python-fastapi-pr <branch>` (for a pull request, `git fetch origin pull/<number>/head:pr-<number>` first) or a second clone. Each checkout has its own `.venv`, `.env` and `storage/`.
- Run one checkout on the default port at a time: stop the other one first, or start the second with `APP_PORT=8001` (PowerShell: `$env:APP_PORT=8001; python serve.py`).
- The SurveyJS service is shared: `docker-compose.yml` names its project `surveyjs-python`, so every checkout manages the same container.
- The page says which checkout answered: "Running `<branch>@<commit>`" under the catalog's footer buttons and at the end of every example's Description panel.

## Docker

```bash
docker compose up --build    # http://127.0.0.1:8000, with the SurveyJS service next to it
```

The image (`Dockerfile`) is `python:3.15.2-slim` with `pip install -r requirements.txt` (no dev dependencies), runs as a non-root user, and starts with `python serve.py`. Its environment sets `APP_HOST=0.0.0.0`, `DATA_DIR=/app/storage` and `FORWARDED_ALLOW_IPS=*`; real environment variables win over `settings.env`, which the image includes. `.env` isn't copied into the image: `docker compose` passes the private keys in. It creates and seeds the database on its first start. Its one volume, `/app/storage`, holds the database, the uploads, the visitor sandboxes and the relay snapshots. Logs go to stderr (`docker compose logs app`). `GET /up` answers `200 {"status": "ok"}` without touching the database.

**One process, many visitors.** The image runs one uvicorn worker, on purpose: the relay rooms, the countries cache and the demo's AI counter live in the process's memory, and a second worker would split a room in two. Concurrency comes from async I/O: an extraction that waits up to 120 seconds for the service is an `await` on the shared `httpx2.AsyncClient`, so other visitors are served meanwhile, and the `def` handlers run in FastAPI's thread pool. To scale out to several processes or hosts, move the rooms to a shared store (Redis pub/sub, for example) first; that is out of scope here.

On Windows, Docker Compose 5 can't build a service from a git URL (`failed to evaluate path "https://github.com/…"`), which the `surveyjs` service is: it hands the URL to the builder as a file path. Let Compose print the build and give it to the builder yourself, then start without building:

```powershell
docker compose build --print | docker buildx bake -f -
docker compose up -d --no-build
```

Linux and macOS (and CI) build with `docker compose up --build` as above.

### Behind a proxy

`serve.py` runs uvicorn with `proxy_headers=True`, trusting `X-Forwarded-For` and `X-Forwarded-Proto` from the addresses in `FORWARDED_ALLOW_IPS`: `127.0.0.1` by default, `*` in the image. Behind a TLS proxy, the pages' absolute URLs and the relays' `wss://` URLs then use the scheme the visitor sees, and the demo's `Secure` cookies work. In your own production, set `FORWARDED_ALLOW_IPS` to the proxy's addresses and don't publish the app's port. The relays are on the app's own host and port, so the proxy needs no extra route, only WebSocket upgrades passed through on `/ws/`. For Traefik, next to your entry point and TLS labels:

```yaml
services:
  app:
    labels:
      - traefik.http.routers.surveyjs.rule=Host(`example.com`)
      - traefik.http.services.surveyjs.loadbalancer.server.port=8000
```

Traefik passes WebSocket upgrades on by default; nginx needs `proxy_set_header Upgrade $http_upgrade;` and `proxy_set_header Connection "upgrade";` on `/ws/`. `RELAY_URL` and `EDIT_RELAY_URL` are only needed when `/ws/` is served from another origin. The SurveyJS service stays internal (`expose: ["3000"]`): only the app calls it.

## Configuration

`app/settings.py` defines one `Settings(BaseSettings)` (pydantic-settings), read once at startup from the environment and two files; handlers get it through the `SettingsDep` dependency, and no other module reads `os.environ`. `settings.env` is committed and holds every setting except the private keys. `.env` is git-ignored and holds only the private keys: `SURVEYJS_LICENSE_KEY`, `AI_API_KEY`, `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` (copy `.env.example` to it). Variables set in the environment win, then `.env`, then `settings.env`. Switches accept `1`, `true`, `on` or `yes`.

| Variable | Default | What it does |
|---|---|---|
| `APP_PORT`, `APP_HOST` | `8000`, `127.0.0.1` | Where the app listens. |
| `DATA_DIR` | `storage` | The database, uploads, sandboxes and relay snapshots. |
| `SURVEYJS_SERVICE_URL` | `http://localhost:3010` | The SurveyJS service (`docker compose up -d surveyjs`). In Compose, the app uses `http://surveyjs:3000`. |
| `VALIDATE_RESPONSES` | `false` | Validate Responses: `app/routes/validate_response.py` replaces `app/routes/save_response.py`. |
| `LINT_DEFINITIONS` | `false` | Lint JSON Schemas: `app/routes/lint_definition.py` replaces `app/routes/creator_load_save.py`. |
| `SURVEYJS_AI_PROVIDER`, `SURVEYJS_AI_MODEL`, `SURVEYJS_OLLAMA_BASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | empty | Extract Responses from Documents: Compose passes them to the service as `AI_PROVIDER`, `AI_MODEL` and `OLLAMA_BASE_URL` (`openai`, `anthropic` or `ollama`). The app reads them only for the page's banner. |
| `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` | OpenAI, empty, `gpt-4o-mini` | Translate with AI: any OpenAI-compatible `/chat/completions` endpoint. Without a key, `/api/translate` answers `501`. |
| `SURVEYJS_LICENSE_KEY` | empty | Calls `setLicenseKey()` on every page. Without it, the commercial components show a licence banner. The service at its pinned revision ignores it, so server PDFs carry the SurveyJS alert banner. |
| `RELAY_URL`, `EDIT_RELAY_URL` | empty | The relays' origin when a proxy serves `/ws/` elsewhere, for example `wss://example.com`. Empty: the page's own origin. |
| `DEMO_MODE` | `false` | The hosted demo's visitor sandboxes (below). |
| `SURVEYJS_BUILD` | from git | The `<branch>@<commit>` the pages show as "Running …". Deploys set it themselves. |
| `SURVEYJS_DOCS`, `SURVEYJS_GITHUB` | the Python docs page, this repository | Where the pages link. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | The proxies uvicorn trusts for `X-Forwarded-*` (see [Behind a proxy](#behind-a-proxy)). |

## The examples

<!-- steps:start (generated by `python -m scripts.readme` from surveyjs-integration.json) -->
| Example | Run | Server | Client | Page | Licence |
|---|---|---|---|---|---|
| [Save Responses](https://surveyjs.io/documentation/backend-integration-fastapi#save-responses) | `/examples/save-response` | [`app/routes/save_response.py`](app/routes/save_response.py) | [`shared/client/save-response.js`](shared/client/save-response.js) | [`templates/examples/save-response.html`](templates/examples/save-response.html) | MIT |
| [Load JSON Schemas, Variables, and Answers](https://surveyjs.io/documentation/backend-integration-fastapi#load-json-schemas-variables-and-answers) | `/examples/load-definition-variables-data` | [`app/routes/load_definition_variables_data.py`](app/routes/load_definition_variables_data.py) | [`shared/client/load-definition-variables-data.js`](shared/client/load-definition-variables-data.js) | [`templates/examples/load-definition-variables-data.html`](templates/examples/load-definition-variables-data.html) | MIT |
| [Resume Progress](https://surveyjs.io/documentation/backend-integration-fastapi#resume-progress) | `/examples/resume-progress` | [`app/routes/resume_progress.py`](app/routes/resume_progress.py) | [`shared/client/resume-progress.js`](shared/client/resume-progress.js) | [`templates/examples/resume-progress.html`](templates/examples/resume-progress.html) | MIT |
| [Store Files Separately](https://surveyjs.io/documentation/backend-integration-fastapi#store-files-separately) | `/examples/store-files` | [`app/routes/store_files.py`](app/routes/store_files.py) | [`shared/client/store-files.js`](shared/client/store-files.js) | [`templates/examples/store-files.html`](templates/examples/store-files.html) | MIT |
| [Load Choices from Web](https://surveyjs.io/documentation/backend-integration-fastapi#load-choices-from-web) | `/examples/choices-from-web` | [`app/routes/choices_from_web.py`](app/routes/choices_from_web.py) | [`shared/client/choices-from-web.js`](shared/client/choices-from-web.js) | [`templates/examples/choices-from-web.html`](templates/examples/choices-from-web.html) | MIT |
| [Async Calculations and Validation](https://surveyjs.io/documentation/backend-integration-fastapi#async-calculations-and-validation) | `/examples/async-functions` | [`app/routes/async_functions.py`](app/routes/async_functions.py) | [`shared/client/async-functions.js`](shared/client/async-functions.js) | [`templates/examples/async-functions.html`](templates/examples/async-functions.html) | MIT |
| [Use Relational Storage](https://surveyjs.io/documentation/backend-integration-fastapi#use-relational-storage) | `/examples/relational-storage` | [`app/routes/relational_storage.py`](app/routes/relational_storage.py) | [`shared/client/relational-storage.js`](shared/client/relational-storage.js) | [`templates/examples/relational-storage.html`](templates/examples/relational-storage.html) | MIT |
| [Fill Forms Together](https://surveyjs.io/documentation/backend-integration-fastapi#fill-forms-together) | `/examples/fill-together` | [`app/routes/fill_together.py`](app/routes/fill_together.py) | [`shared/client/fill-together.js`](shared/client/fill-together.js) | [`templates/examples/fill-together.html`](templates/examples/fill-together.html) | MIT |
| [Analyze Results with Dashboard](https://surveyjs.io/documentation/backend-integration-fastapi#analyze-results-with-dashboard) | `/examples/dashboard` | [`app/routes/dashboard.py`](app/routes/dashboard.py) | [`shared/client/dashboard.js`](shared/client/dashboard.js) | [`templates/examples/dashboard.html`](templates/examples/dashboard.html) | Commercial client |
| [Load and Save Form JSON Schemas](https://surveyjs.io/documentation/backend-integration-fastapi#load-and-save-form-json-schemas) | `/examples/creator-load-save` | [`app/routes/creator_load_save.py`](app/routes/creator_load_save.py) | [`shared/client/creator-load-save.js`](shared/client/creator-load-save.js) | [`templates/examples/creator-load-save.html`](templates/examples/creator-load-save.html) | Commercial client |
| [Upload Files](https://surveyjs.io/documentation/backend-integration-fastapi#upload-files) | `/examples/creator-uploads` | [`app/routes/store_files.py`](app/routes/store_files.py) | [`shared/client/creator-uploads.js`](shared/client/creator-uploads.js) | [`templates/examples/creator-uploads.html`](templates/examples/creator-uploads.html) | Commercial client |
| [Translate with AI](https://surveyjs.io/documentation/backend-integration-fastapi#translate-with-ai) | `/examples/ai-translation` | [`app/routes/ai_translation.py`](app/routes/ai_translation.py) | [`shared/client/ai-translation.js`](shared/client/ai-translation.js) | [`templates/examples/ai-translation.html`](templates/examples/ai-translation.html) | Commercial client, needs an AI provider |
| [Variable Presets](https://surveyjs.io/documentation/backend-integration-fastapi#variable-presets) | `/examples/variable-presets` | [`app/routes/variable_presets.py`](app/routes/variable_presets.py) | [`shared/client/variable-presets.js`](shared/client/variable-presets.js) | [`templates/examples/variable-presets.html`](templates/examples/variable-presets.html) | Commercial client |
| [Edit Forms Together](https://surveyjs.io/documentation/backend-integration-fastapi#edit-forms-together) | `/examples/edit-together` | [`app/routes/edit_together.py`](app/routes/edit_together.py) | [`shared/client/edit-together.js`](shared/client/edit-together.js) | [`templates/examples/edit-together.html`](templates/examples/edit-together.html) | Commercial client |
| [Validate Responses](https://surveyjs.io/documentation/backend-integration-fastapi#validate-responses) | `/examples/validate-response` | [`app/routes/validate_response.py`](app/routes/validate_response.py) | [`shared/client/validate-response.js`](shared/client/validate-response.js) | [`templates/examples/validate-response.html`](templates/examples/validate-response.html) | MIT |
| [Lint JSON Schemas](https://surveyjs.io/documentation/backend-integration-fastapi#lint-json-schemas) | `/examples/lint-definition` | [`app/routes/lint_definition.py`](app/routes/lint_definition.py) | [`shared/client/lint-definition.js`](shared/client/lint-definition.js) | [`templates/examples/lint-definition.html`](templates/examples/lint-definition.html) | MIT |
| [Generate PDFs](https://surveyjs.io/documentation/backend-integration-fastapi#generate-pdfs) | `/examples/server-pdf` | [`app/routes/server_pdf.py`](app/routes/server_pdf.py) | [`shared/client/server-pdf.js`](shared/client/server-pdf.js) | [`templates/examples/server-pdf.html`](templates/examples/server-pdf.html) | Commercial |
| [Extract Responses from Documents](https://surveyjs.io/documentation/backend-integration-fastapi#extract-responses-from-documents) | `/examples/extract-from-paper` | [`app/routes/extract_from_paper.py`](app/routes/extract_from_paper.py) | [`shared/client/extract-from-paper.js`](shared/client/extract-from-paper.js) | [`templates/examples/extract-from-paper.html`](templates/examples/extract-from-paper.html) | MIT, needs an AI provider |
<!-- steps:end -->

## Where each example lives

Each example is two or three files you can read on their own. The full explanation is in [the docs](https://surveyjs.io/documentation/backend-integration-fastapi).

- `app/routes/<snake_slug>.py`: the example's routes, the server code the docs show, as one `APIRouter`. `app/main.py` includes the routers in the docs' order, and picks `validate_response.py` or `save_response.py`, and `lint_definition.py` or `creator_load_save.py`, by the switches. `fill_together.py` and `edit_together.py` are the two relays, as `@router.websocket` routes; their rooms are in `app/relay/`.
- `shared/client/<slug>.js`: the example's client code, a plain ES module, the same file on every platform.
- `templates/examples/<slug>.html`: the example's page (Jinja): its description, the "Try this" list and the component.
- `app/integration/`: small helpers some routes call, so the code the docs show stays about SurveyJS. They aren't demo code:
  - `stored_json.py`: the `JsonBody` dependency, `dumps()`, `insert_response()` and `put()` (see below).
  - `surveyjs_service.py`: `SurveyJsService.post()` with its timeouts, the 503 and 504 when the service doesn't answer, and the logging.
  - `ai_translation.py`: the call to your OpenAI-compatible provider.
  - `http.py`, `ttl_cache.py`, `file_type.py`: the shared HTTP client, the countries cache, and file types by their first bytes.
- `app/db.py` (the `Db` dependency: one SQLite connection per request), `app/auth.py` (`get_current_user`, `can()`, `can_read_file()`) and `app/settings.py`.

To copy an example, copy its router module and the helpers it imports. The code the docs show is cut from these files between `# region sjs:<slug>.server` and `# endregion` (and `// #region sjs:<slug>.client` in the client modules). `surveyjs-integration.json` lists every example's files and regions; `python -m scripts.check` verifies them. SQLAlchemy or SQLModel with a JSON column works just as well as `sqlite3`; the examples use plain parameterized SQL so that a response stays visibly one JSON document.

### Shared files

`shared/` holds what every platform repository uses byte for byte: the client modules, the form definitions, samples and seed data, the page UI (`shared/ui/`), and the contract, smoke and browser tests. It is a copy of [`surveyjs-php-laravel`](https://github.com/surveyjs/surveyjs-php-laravel)'s `shared/` at the commit in `shared/UPSTREAM`; `python -m scripts.check` compares it with `shared/SHA256SUMS`. Don't edit it here: send a fix to that repository, then copy `shared/` again. `.gitattributes` keeps it in LF on Windows checkouts too, or every hash would fail.

### Editing example descriptions

The text in an example's Description panel is the `description` block of `templates/examples/<slug>.html`. It can hold several paragraphs, links and other markup:

```jinja
{% block description %}
    <p>Your custom description.</p>
    <p>More details with <strong>formatting</strong>.</p>
{% endblock %}
```

The "Try this" list is the `try` block; the layout is `templates/layouts/example.html`. The catalog cards use `need` from `surveyjs-integration.json` for their "Use when" text. After editing a template, rebuild the stylesheet (see [Front end](#front-end)) if you used a Tailwind class no other template uses.

### Storing JSON exactly as it arrives

A response, a definition, saved progress and variable presets are each one JSON document, stored as text and returned as stored.

- **A raw body, not a Pydantic model.** FastAPI developers reach for a model (`data: dict`), but a model answers `422 {detail}` for a non-object, drops the keys it doesn't declare, and may coerce values. The storing handlers take `body: JsonBody` instead (`app/integration/stored_json.py`): `json.loads(await request.body())`, which keeps every key, `{}`, `[{}]`, `None`, `""`, whitespace inside strings and `1.0`. A comment in each handler says why. Translate with AI stores nothing, so it reads a model.
- **`NaN` is refused.** Python's `json.loads` accepts `NaN`, `Infinity` and `-Infinity`; JSON doesn't, so `JsonBody` rejects them with `400 { "error": "The request body is not valid JSON" }`, like any other body that isn't JSON.
- **`ensure_ascii=False`.** `dumps()` stores `"naïve — 東京"` as it is, not as `\u` escapes, with compact separators; `1.0` stays `1.0`.
- **Dates are strings.** `created_at` is ISO 8601 UTC without fractions (`2026-11-16T12:00:00Z`, written with `strftime`), so the dashboard's date filters are string comparisons. `isoformat()` would write `+00:00` and microseconds.
- Under `/api`, every error is `{ "error": … }`, also FastAPI's own (`app/errors.py`): a router's 404 and 405 (with `Allow`), and a bad query parameter (`limit=abc`) as `400`.

### Sync and async handlers

FastAPI runs `def` handlers in its thread pool and `async def` handlers on the event loop. Here:

- Handlers that only touch SQLite are `def`. A handler that takes `JsonBody` is still `def`: the dependency reads the body on the event loop, then the handler runs in the pool.
- Handlers that wait on the network (the SurveyJS service, the AI provider, restcountries.com) or read a form (the uploads) are `async def`, and use the shared `httpx2.AsyncClient`. Never use a blocking HTTP client in an `async def`: one extraction would stall every visitor.
- The short SQLite reads and writes that those `async def` handlers make go through the same synchronous helpers; they take a millisecond. The fill relay's save runs in the thread pool (`run_in_threadpool`), under the room's lock.

## How data works in the demo

Locally, everyone shares one SQLite database, `storage/database.sqlite` (delete `storage/` to start over).

On a hosted demo (`DEMO_MODE=true`), each visitor gets a private copy of the seeded database and uploads folder, chosen by a `demo_sid` cookie, and kept until it has been unused for 24 hours (an hourly task in the app, `app/demo/pruner.py`). The "Open a second window" link in Fill Forms Together and Edit Forms Together carries that id (`?join=`), so whoever opens it works in the same copy and the same relay rooms. The demo also caps uploads at 5 MB and the AI examples at 20 calls per visitor per day, counted in this process. None of this is in the example code.

## Front end

- The pages are Jinja templates (`templates/`) through FastAPI's `Jinja2Templates`, autoescaped. Each page diffs against its Blade source in the reference repository in template syntax only, with the Tailwind class strings unchanged. Inline JSON (the page config, `window.FORM_DEFINITION`, `window.FORM_VARIABLES`) goes through Jinja's `tojson`, which escapes `<`, `>` and `&`, so a `</script>` in a definition can't end the script; no value from the database is ever `| safe`.
- The site stylesheet is Tailwind CSS v4 without Preflight: `styles/site.css` imports `tailwindcss/theme.css` (static), `tailwindcss/utilities.css` and `shared/ui/theme.css`. `npm run css` builds it into `static/css/site.css` with `@tailwindcss/cli`. The output is committed, so running the app never needs Node; CI rebuilds it and fails on a difference. The [Tailwind standalone binary](https://tailwindcss.com/blog/standalone-cli) builds the same file without Node: `tailwindcss -i styles/site.css -o static/css/site.css --minify`.
- The client code is the shared ES modules in `shared/client/` and `shared/ui/`, loaded unchanged with `<script type="module">` and an import map (`app/frontend.py`). No Python package carries SurveyJS's browser builds, so every specifier points to unpkg: the SurveyJS packages at the version in `shared/surveyjs-version.json` (`fesm/*.mjs`), and `chart.js`, `@kurkle/color`, `lodash-es` and highlight.js at pinned versions. There is no bundler.
- To self-host them, copy each package's `fesm/` files (and the CSS the pages load) into `static/vendor/<package>@<version>/` and point `UNPKG` in `app/frontend.py` at `/static/vendor`. Don't mix the script-tag builds (`survey.core.js` and friends) with the ES modules on one page: they would load SurveyJS twice.
- Python reads MIME types from the Windows registry, where `.js` or `.mjs` can be `text/plain`, and browsers refuse to run a module served that way. `app/main.py` registers `text/javascript` (and the SVG, font and CSS types) before mounting `shared/` and `static/`.
- The forms use the SurveyJS Tailwind adapter (`survey-core/themes/adapters/tailwind4.css`). No page calls `applyTheme()`: its inline styles would override the adapter.

## Not on FastAPI?

The routers only use the request, the database and the response, so they port in a few lines. Save Responses as a Flask view, reading the raw body for the same reason:

```python
@app.post("/api/responses")
def save_response():
    body = json.loads(request.get_data())   # not request.get_json(): the same raw body, parsed once
    if not isinstance(body, dict) or "formId" not in body or "data" not in body:
        return jsonify(error="Expected { formId, data }"), 400

    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    cursor = db.execute("INSERT INTO responses (form_id, data, created_at) VALUES (?, ?, ?)",
                        (body["formId"], json.dumps(body["data"], ensure_ascii=False), created_at))
    return jsonify(id=cursor.lastrowid), 201
```

Only the request and response wrappers change. Django has its own SurveyJS example repository: [surveyjs-python-django](https://github.com/surveyjs/surveyjs-python-django).

## Disclaimer

These examples must not be used as a real service as they are. They don't cover authentication, authorization, user management, access levels and other security aspects of a real survey service. The places where real checks go are marked:

- `can(user, "edit-forms")` and `can_read_file(user, file)` in `app/auth.py`: who may save definitions and presets, and who may read an uploaded file.
- `get_current_user` in `app/auth.py`: the demo version reads a `demo_user` cookie; your app reads its session there, or uses an `OAuth2PasswordBearer` / JWT dependency. The relays take the same dependency.

When you copy an example into your app, leave out the demo-only code: the `app/demo/` folder (and its lines in `app/main.py`), `app/pages.py`, `app/frontend.py`, `app/relay/room_key.py`'s sandbox keys, `templates/`, `shared/ui/` (the page frame, its tabs and highlighting, the fonts and site images) and `shared/client/host.js` (its `mountSurvey()` is one line: `renderSurvey(survey, element)` from `survey-js-ui`).

## Licence

The code in this repository is available under the [MIT licence](LICENSE).

The examples use SurveyJS Form Library, which is MIT-licensed as well. The examples marked "Commercial" in the Licence column above also use SurveyJS Survey Creator, Dashboard or PDF Generator, which are commercial products. You can integrate them and evaluate their functionality without a licence. Production use requires a developer licence for each developer who works with the SurveyJS APIs or implements the integration. See the [SurveyJS Licensing FAQ](https://surveyjs.io/faq#licensing) and the [End-User License Agreement](https://surveyjs.io/Developer-License-Agreement.pdf).
