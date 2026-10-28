from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from backend.app.config import PROJECT_ROOT, Settings, load_env_file


def test_env_file_loads_values_and_does_not_override_process_environment(monkeypatch) -> None:
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
        env_path = Path(directory) / ".env"
        env_path.write_text(
            "FROM_FILE=loaded\nEXISTING=from-file\nQUOTED='quoted value'\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("FROM_FILE", raising=False)
        monkeypatch.setenv("EXISTING", "from-process")
        monkeypatch.delenv("QUOTED", raising=False)

        load_env_file(env_path)

        assert os.environ["FROM_FILE"] == "loaded"
        assert os.environ["EXISTING"] == "from-process"
        assert os.environ["QUOTED"] == "quoted value"


def test_invalid_env_entry_is_rejected(monkeypatch) -> None:
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
        env_path = Path(directory) / ".env"
        env_path.write_text("NOT VALID\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid .env entry"):
            load_env_file(env_path)


def test_project_env_is_connected_to_settings(monkeypatch) -> None:
    with tempfile.TemporaryDirectory(dir=PROJECT_ROOT) as directory:
        env_path = Path(directory) / ".env"
        env_path.write_text(
            "GROQ_API_KEY=\nKASPARRO_GROQ_MODEL=openai/gpt-oss-20b\n",
            encoding="utf-8",
        )
        monkeypatch.setattr("backend.app.config.ENV_FILE", env_path)
        monkeypatch.delenv("KASPARRO_GROQ_MODEL", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        settings = Settings.from_environment()

        assert settings.groq_model == "openai/gpt-oss-20b"
        assert settings.groq_api_key is None


def test_settings_repr_never_exposes_groq_key(monkeypatch) -> None:
    secret = "test-secret-that-must-not-appear"
    monkeypatch.setattr(
        "backend.app.config.ENV_FILE", PROJECT_ROOT / "missing-test-environment-file"
    )
    monkeypatch.setenv("GROQ_API_KEY", secret)

    settings = Settings.from_environment()

    assert settings.groq_api_key == secret
    assert secret not in repr(settings)
