import html
from dataclasses import dataclass

from src.apps.reachability.domain.targets import IpTarget

OUTSIDE = "снаружи"
_HEADER = "🛰 Проверка блокировок: изменения"
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
    lines = [
        f"{_TITLES[change.current]}: {target.ip}",
        f"Плитки: {_format_tiles(target.tiles)}",
        f"Ноды: {html.escape(', '.join(target.node_names))}",
    ]
    if change.current != "ok":
        names = [*point_names, OUTSIDE]
        lines.append(" · ".join(f"{n} {_mark(change.point_results.get(n))}" for n in names))
    return "\n".join(lines)


def format_digest(changes: list[IpChange], point_names: list[str]) -> list[str]:
    ordered = sorted(changes, key=lambda c: _ORDER[c.current])
    messages: list[str] = []
    current = _HEADER
    for change in ordered:
        block = _format_block(change, point_names)
        if current != _HEADER and len(current) + 2 + len(block) > _MAX_MESSAGE:
            messages.append(current)
            current = _HEADER
        current += "\n\n" + block
    if current != _HEADER:
        messages.append(current)
    return messages


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
