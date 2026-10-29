from __future__ import annotations

import re

from backend.app.config import PROJECT_ROOT

SECRET_NAME = re.compile(r"(_TOKEN|API_KEY|SECRET|PASSWORD)$")


def _example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    lines = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def test_every_config_variable_is_in_env_example() -> None:
    config_source = (PROJECT_ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
    used = set(re.findall(r'os\.getenv\(\s*"([A-Z0-9_]+)"', config_source))

    assert used  # the pattern still finds the variables
    assert used <= set(_example_values())


def test_env_example_secrets_are_blank() -> None:
    values = _example_values()
    secret_names = [name for name in values if SECRET_NAME.search(name)]

    assert secret_names  # the secrets are listed, not left out
    assert all(values[name] == "" for name in secret_names)
