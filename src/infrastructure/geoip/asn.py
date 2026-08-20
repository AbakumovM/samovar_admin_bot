import logging
from dataclasses import dataclass
from typing import Protocol

import maxminddb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AsnInfo:
    number: int
    org: str


class AsnResolver(Protocol):
    def lookup(self, ip: str) -> AsnInfo | None: ...


class NopAsnResolver:
    """Used when ASN grouping is disabled — every lookup is a no-op miss."""

    def lookup(self, ip: str) -> AsnInfo | None:
        return None


class MaxMindAsnResolver:
    """Wraps a MaxMind GeoLite2-ASN .mmdb reader with hot-reload support.

    The updater task (see updater.py) replaces the file on disk atomically
    and then calls reload() — this swaps the in-process reader reference
    rather than mutating the open one, so a lookup() call is never torn
    mid-read (both run on the single asyncio thread with no await inside
    lookup(), so a reload() can only happen strictly before or after one,
    never during).
    """

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._reader: maxminddb.Reader | None = None
        self.reload()

    def reload(self) -> None:
        try:
            new_reader = maxminddb.open_database(self._database_path)
        except (FileNotFoundError, OSError, ValueError) as e:
            logger.warning(
                "Antifraud ASN: could not open database at %s: %s", self._database_path, e
            )
            return
        old_reader = self._reader
        self._reader = new_reader
        if old_reader is not None:
            old_reader.close()

    def lookup(self, ip: str) -> AsnInfo | None:
        if self._reader is None:
            return None
        try:
            result = self._reader.get(ip)
        except ValueError:
            return None
        if not isinstance(result, dict):
            return None
        number = result.get("autonomous_system_number")
        if not isinstance(number, int):
            return None
        org = result.get("autonomous_system_organization")
        return AsnInfo(number=number, org=str(org) if org else "")
