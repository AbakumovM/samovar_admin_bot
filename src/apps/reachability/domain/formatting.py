import html
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.apps.reachability.domain.targets import IpTarget

OUTSIDE = "снаружи"
_HEADER = "🛰 Проверка блокировок: изменения"
_REMINDER_HEADER = "🔁 Всё ещё заблокированы"
_MSK = timezone(timedelta(hours=3))
_MAX_MESSAGE = 4000
_MAX_TILES = 5
_ORDER = {"blocked": 0, "partial": 1, "ok": 2}
_TITLES = {
    "blocked": "🚫 Заблокирован",
    "partial": "⚠️ Частичная блокировка",
    "ok": "✅ Снова доступен",
}


@dataclass(frozen=True)
class IpChange:
    target: IpTarget
    previous: str | None
    current: str
    point_results: dict[str, str | None]  # None — point did not take part (⏸)


@dataclass(frozen=True)
class ReminderItem:
    target: IpTarget
    status: str  # partial | blocked
    since: datetime | None


def fmt_msk(moment: datetime) -> str:
    return moment.astimezone(_MSK).strftime("%d.%m %H:%M МСК")


def _hoster_line(target: IpTarget) -> list[str]:
    if not target.hosters:
        return []
    links = [
        f'<a href="{html.escape(url)}">{html.escape(name)}</a>' if url else html.escape(name)
        for name, url in target.hosters
    ]
    return [f"Хостер: {', '.join(links)}"]


def _target_lines(target: IpTarget) -> list[str]:
    lines = [f"Плитки: {_format_tiles(target.tiles)}"]
    if target.node_names:
        lines.append(f"Ноды: {html.escape(', '.join(target.node_names))}")
    return lines


def _join_blocks(header: str, blocks: list[str]) -> list[str]:
    messages: list[str] = []
    current = header
    for block in blocks:
        if current != header and len(current) + 2 + len(block) > _MAX_MESSAGE:
            messages.append(current)
            current = header
        current += "\n\n" + block
    if current != header:
        messages.append(current)
    return messages


def _mark(result: str | None) -> str:
    if result is None:
        return "⏸"
    return "✅" if result == "ok" else "❌"


def _format_tiles(tiles: tuple[str, ...]) -> str:
    shown = ", ".join(html.escape(t) for t in tiles[:_MAX_TILES])
    if len(tiles) > _MAX_TILES:
        shown += f" +{len(tiles) - _MAX_TILES}"
    return shown


def _format_block(change: IpChange, point_names: list[str]) -> str:
    target = change.target
    lines = [f"{_TITLES[change.current]}: {target.ip}", *_target_lines(target)]
    if change.current != "ok":
        names = [*point_names, OUTSIDE]
        lines.append(" · ".join(f"{n} {_mark(change.point_results.get(n))}" for n in names))
    lines.extend(_hoster_line(target))
    return "\n".join(lines)


def format_digest(changes: list[IpChange], point_names: list[str]) -> list[str]:
    ordered = sorted(changes, key=lambda c: _ORDER[c.current])
    return _join_blocks(_HEADER, [_format_block(c, point_names) for c in ordered])


def format_reminder(items: list[ReminderItem]) -> list[str]:
    blocks = []
    for item in sorted(items, key=lambda i: _ORDER[i.status]):
        icon = "🚫" if item.status == "blocked" else "⚠️"
        partial = " (частично)" if item.status == "partial" else ""
        since = f" — с {fmt_msk(item.since)}" if item.since else ""
        lines = [f"{icon} {item.target.ip}{partial}{since}", *_target_lines(item.target)]
        lines.extend(_hoster_line(item.target))
        blocks.append("\n".join(lines))
    return _join_blocks(_REMINDER_HEADER, blocks)


def reason_ssh() -> str:
    return "не отвечает по SSH"


def reason_control(ok: int, total: int) -> str:
    return f"не видит контрольные адреса (открыто {ok} из {total})"


def format_point_down(name: str, reason: str, remaining_ru: int, is_outside: bool) -> str:
    if is_outside:
        tail = "Проверка блокировок приостановлена."
    elif remaining_ru > 0:
        tail = "Проверка блокировок идёт по оставшимся точкам."
    else:
        tail = "Проверка блокировок приостановлена: нет работающих точек в РФ."
    return f"⚠️ Точка проверки {name} не работает: {reason}\n{tail}"


def format_point_up(name: str) -> str:
    return f"✅ Точка проверки {name} снова работает"
