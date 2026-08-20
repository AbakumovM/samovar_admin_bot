from datetime import datetime

from src.apps.antifraud.application.interfaces.gateway import AntifraudGateway
from src.apps.antifraud.application.interfaces.view import AntifraudCooldownView


def is_past_cooldown(last_notified: datetime | None, now: datetime, cooldown_hours: int) -> bool:
    if last_notified is None:
        return True
    return (now - last_notified).total_seconds() >= cooldown_hours * 3600


class AntifraudInteractor:
    def __init__(self, gateway: AntifraudGateway, view: AntifraudCooldownView) -> None:
        self._gateway = gateway
        self._view = view

    async def filter_out_cooled_down(
        self, remnawave_ids: list[int], now: datetime, cooldown_hours: int
    ) -> set[int]:
        last_notified = await self._view.get_last_notified_bulk(remnawave_ids)
        return {
            rid
            for rid in remnawave_ids
            if is_past_cooldown(last_notified.get(rid), now, cooldown_hours)
        }

    async def filter_out_cooled_down_soft(
        self, remnawave_ids: list[int], now: datetime, cooldown_hours: int
    ) -> set[int]:
        last_notified = await self._view.get_last_soft_notified_bulk(remnawave_ids)
        return {
            rid
            for rid in remnawave_ids
            if is_past_cooldown(last_notified.get(rid), now, cooldown_hours)
        }

    async def mark_notified_batch(self, remnawave_ids: list[int], now: datetime) -> None:
        for rid in remnawave_ids:
            await self._gateway.mark_notified(rid, now)

    async def mark_soft_notified_batch(self, remnawave_ids: list[int], now: datetime) -> None:
        for rid in remnawave_ids:
            await self._gateway.mark_soft_notified(rid, now)

    async def filter_by_violation_threshold(
        self, remnawave_ids: list[int], now: datetime, threshold: int, window_seconds: int
    ) -> set[int]:
        """Increments each id's sliding-window violation counter and returns
        the subset that has reached `threshold` (their counters are reset).
        With the default threshold of 1, every violation reaches it
        immediately — the DB round-trip is skipped entirely in that case.
        """
        if threshold <= 1:
            return set(remnawave_ids)
        reached: set[int] = set()
        for rid in remnawave_ids:
            count = await self._gateway.increment_violation_count(rid, now, window_seconds)
            if count >= threshold:
                reached.add(rid)
                await self._gateway.reset_violation_count(rid)
        return reached
