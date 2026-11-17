"""Every setting, read once from the environment and .env. No other module reads os.environ.

create_app() builds one Settings and handlers get it through the SettingsDep dependency. Real
environment variables win over .env, so Docker, CI and the contract runner can override any key.
"""

import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.requests import HTTPConnection

ROOT = Path(__file__).resolve().parent.parent
"""The repository root: shared/, templates/ and surveyjs-integration.json live here."""

_SWITCH = re.compile(r"^(1|true|on|yes)$", re.IGNORECASE)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore")

    # Where the app listens. serve.py refuses a port something already answers on.
    app_port: int = 8000
    app_host: str = "127.0.0.1"

    # The SQLite database, uploads, visitor sandboxes and relay snapshots
    data_dir: Path = Path("storage")

    # Run Server-Side Workflows: SurveyJS Server (github.com/surveyjs/surveyjs-server), next to this app
    surveyjs_service_url: str = "http://localhost:3010"
    validate_responses: bool = False   # app/routes/validate_response.py replaces save_response.py
    lint_definitions: bool = False     # app/routes/lint_definition.py replaces creator_load_save.py

    # Demo only: a private SQLite copy and uploads folder per visitor (README: How data works in the demo)
    demo_mode: bool = False

    # The relays run in this app, on its port. Set these to a proxy's origin (wss://example.com) when it
    # serves /ws/ on another host; unset, the pages use their own origin.
    relay_url: str | None = None
    edit_relay_url: str | None = None

    # Shown in the browser: host.js calls setLicenseKey() only when it is set
    surveyjs_license_key: str | None = None

    # Translate with AI: any OpenAI-compatible /chat/completions endpoint
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str | None = None
    ai_model: str = "gpt-4o-mini"

    # Extract Responses from Documents: Docker Compose passes these to the SurveyJS service under its
    # own names (AI_PROVIDER, AI_MODEL, OLLAMA_BASE_URL). The app reads them only for the page's banner.
    surveyjs_ai_provider: str | None = None
    surveyjs_ai_model: str | None = None
    surveyjs_ollama_base_url: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Which checkout answered, `<branch>@<commit>`: serve.py sets it from git, deploys set it themselves
    surveyjs_build: str | None = None

    # Where the pages link: the docs (each example adds #<anchor>) and the repository (View on GitHub)
    surveyjs_docs: str = "https://surveyjs.io/documentation/backend-integration-python"
    surveyjs_github: str = "https://github.com/surveyjs/surveyjs-python-fastapi"

    # uvicorn trusts X-Forwarded-For and X-Forwarded-Proto from these addresses (the Docker image: *)
    forwarded_allow_ips: str = "127.0.0.1"

    @field_validator("validate_responses", "lint_definitions", "demo_mode", mode="before")
    @classmethod
    def _switch(cls, value: Any) -> bool:
        """Switches accept 1, true, on or yes, as the contract test does; anything else is off."""
        return value is True or bool(_SWITCH.match(str(value).strip()))

    @field_validator("relay_url", "edit_relay_url", "surveyjs_license_key", "ai_api_key", "surveyjs_ai_provider",
                     "surveyjs_ai_model", "surveyjs_ollama_base_url", "openai_api_key", "anthropic_api_key", "surveyjs_build",
                     mode="before")
    @classmethod
    def _text(cls, value: Any) -> str | None:
        """Blank means unset. A variable set to a space overrides .env with nothing (the contract runner's AI=off)."""
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("surveyjs_service_url", "ai_base_url", mode="after")
    @classmethod
    def _no_trailing_slash(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("data_dir", mode="after")
    @classmethod
    def _from_root(cls, value: Path) -> Path:
        """A relative DATA_DIR is relative to the repository, wherever the app was started from."""
        return value if value.is_absolute() else (ROOT / value).resolve()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "database.sqlite"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def sandbox_dir(self) -> Path:
        return self.data_dir / "sandbox"

    @property
    def relay_dir(self) -> Path:
        return self.data_dir / "relay"


def get_settings(conn: HTTPConnection) -> Settings:
    return conn.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


if __name__ == "__main__":   # python -m app.settings: what the app runs with here, secrets masked (the CI image job)
    _SECRETS = {"surveyjs_license_key", "ai_api_key", "openai_api_key", "anthropic_api_key"}
    for _name, _value in Settings().model_dump().items():
        print(f"{_name}={'(set)' if _name in _SECRETS and _value else _value}")
