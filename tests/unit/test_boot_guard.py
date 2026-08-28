"""SEC-01: o boot recusa subir com APP_TOKEN de exemplo (guard fail-closed)."""

from orchestrator.config import Settings, insecure_boot_errors


def test_insecure_app_token_default_rejected() -> None:
    errs = insecure_boot_errors(Settings(APP_TOKEN="dev-changeme"))  # noqa: S106
    assert errs and "APP_TOKEN" in errs[0]


def test_insecure_app_token_env_example_rejected() -> None:
    s = Settings(APP_TOKEN="dev-changeme-with-strong-random")  # noqa: S106
    assert insecure_boot_errors(s)


def test_empty_app_token_rejected() -> None:
    assert insecure_boot_errors(Settings(APP_TOKEN=""))  # noqa: S106


def test_strong_app_token_ok() -> None:
    strong = "9f2b7c1e4a6d8f0b2c4e6a8d0f1b3c5e7a9d1f3b5c7e9a1d3f5b7c9e1a3d5f7b"  # noqa: S105
    assert insecure_boot_errors(Settings(APP_TOKEN=strong)) == []


def test_escape_flag_allows_insecure_token_in_dev() -> None:
    s = Settings(APP_TOKEN="dev-changeme", ALLOW_INSECURE_APP_TOKEN=True)  # noqa: S106
    assert insecure_boot_errors(s) == []
