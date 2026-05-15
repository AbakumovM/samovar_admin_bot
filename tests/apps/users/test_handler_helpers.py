import pytest
from src.apps.users.controllers.telegram.handlers import _fmt_bytes, _bar


def test_fmt_bytes_gb() -> None:
    assert _fmt_bytes(2 * 1024**3) == "2.0 GB"


def test_fmt_bytes_mb() -> None:
    assert _fmt_bytes(512 * 1024**2) == "512.0 MB"


def test_fmt_bytes_fractional_gb() -> None:
    assert _fmt_bytes(int(1.5 * 1024**3)) == "1.5 GB"


def test_bar_empty() -> None:
    assert _bar(0.0) == "░░░░░░░░"


def test_bar_full() -> None:
    assert _bar(1.0) == "████████"


def test_bar_half() -> None:
    result = _bar(0.5)
    assert result == "████░░░░"


def test_bar_width() -> None:
    assert len(_bar(0.3)) == 8
