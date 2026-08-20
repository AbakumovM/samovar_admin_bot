from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.apps.antifraud.application.interactor import AntifraudInteractor, is_past_cooldown

_NOW = datetime(2026, 8, 18, 12, 0, 0, tzinfo=UTC)


def test_is_past_cooldown_none_means_never_notified() -> None:
    assert is_past_cooldown(None, _NOW, cooldown_hours=24) is True


def test_is_past_cooldown_within_window() -> None:
    last = _NOW - timedelta(hours=1)
    assert is_past_cooldown(last, _NOW, cooldown_hours=24) is False


def test_is_past_cooldown_exactly_at_boundary() -> None:
    last = _NOW - timedelta(hours=24)
    assert is_past_cooldown(last, _NOW, cooldown_hours=24) is True


def test_is_past_cooldown_after_window() -> None:
    last = _NOW - timedelta(hours=25)
    assert is_past_cooldown(last, _NOW, cooldown_hours=24) is True


@pytest.fixture
def gateway() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def view() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def interactor(gateway: AsyncMock, view: AsyncMock) -> AntifraudInteractor:
    return AntifraudInteractor(gateway=gateway, view=view)


async def test_filter_out_cooled_down_excludes_recently_notified(
    interactor: AntifraudInteractor, view: AsyncMock
) -> None:
    view.get_last_notified_bulk.return_value = {1: _NOW - timedelta(hours=1)}

    eligible = await interactor.filter_out_cooled_down([1, 2], now=_NOW, cooldown_hours=24)

    assert eligible == {2}


async def test_filter_out_cooled_down_includes_never_notified(
    interactor: AntifraudInteractor, view: AsyncMock
) -> None:
    view.get_last_notified_bulk.return_value = {}

    eligible = await interactor.filter_out_cooled_down([1, 2], now=_NOW, cooldown_hours=24)

    assert eligible == {1, 2}


async def test_filter_out_cooled_down_includes_expired_cooldown(
    interactor: AntifraudInteractor, view: AsyncMock
) -> None:
    view.get_last_notified_bulk.return_value = {1: _NOW - timedelta(hours=48)}

    eligible = await interactor.filter_out_cooled_down([1], now=_NOW, cooldown_hours=24)

    assert eligible == {1}


async def test_mark_notified_batch_calls_gateway_for_each_id(
    interactor: AntifraudInteractor, gateway: AsyncMock
) -> None:
    await interactor.mark_notified_batch([1, 2, 3], now=_NOW)

    assert gateway.mark_notified.await_count == 3
    gateway.mark_notified.assert_any_await(1, _NOW)
    gateway.mark_notified.assert_any_await(3, _NOW)


async def test_filter_out_cooled_down_soft_uses_soft_bulk_lookup(
    interactor: AntifraudInteractor, view: AsyncMock
) -> None:
    view.get_last_soft_notified_bulk.return_value = {1: _NOW - timedelta(hours=1)}

    eligible = await interactor.filter_out_cooled_down_soft([1, 2], now=_NOW, cooldown_hours=24)

    assert eligible == {2}
    view.get_last_soft_notified_bulk.assert_awaited_once_with([1, 2])


async def test_mark_soft_notified_batch_calls_gateway_for_each_id(
    interactor: AntifraudInteractor, gateway: AsyncMock
) -> None:
    await interactor.mark_soft_notified_batch([1, 2], now=_NOW)

    assert gateway.mark_soft_notified.await_count == 2
    gateway.mark_soft_notified.assert_any_await(1, _NOW)
    gateway.mark_soft_notified.assert_any_await(2, _NOW)


async def test_filter_by_violation_threshold_default_passes_immediately(
    interactor: AntifraudInteractor, gateway: AsyncMock
) -> None:
    reached = await interactor.filter_by_violation_threshold(
        [1, 2], now=_NOW, threshold=1, window_seconds=3600
    )

    assert reached == {1, 2}
    gateway.increment_violation_count.assert_not_awaited()


async def test_filter_by_violation_threshold_excludes_not_yet_reached(
    interactor: AntifraudInteractor, gateway: AsyncMock
) -> None:
    gateway.increment_violation_count.side_effect = [1, 3]  # user 1 at 1/3, user 2 at 3/3

    reached = await interactor.filter_by_violation_threshold(
        [1, 2], now=_NOW, threshold=3, window_seconds=3600
    )

    assert reached == {2}
    gateway.reset_violation_count.assert_awaited_once_with(2)


async def test_filter_by_violation_threshold_resets_counter_on_reach(
    interactor: AntifraudInteractor, gateway: AsyncMock
) -> None:
    gateway.increment_violation_count.return_value = 3

    await interactor.filter_by_violation_threshold([1], now=_NOW, threshold=3, window_seconds=3600)

    gateway.reset_violation_count.assert_awaited_once_with(1)
