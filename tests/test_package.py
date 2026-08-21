"""Package bootstrap tests."""

from macro_event_telegram_alerts import __version__


def test_package_version() -> None:
    """The installed package exposes its bootstrap version."""
    assert __version__ == "0.0.0"
