import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import asyncssh

from src.infrastructure.reachability.probe import probe_targets

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProbePoint:
    name: str
    host: str


def _parse_results(raw: object, expected: int) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list) or len(raw) != expected:
        return None
    if not all(isinstance(item, dict) and "result" in item for item in raw):
        return None
    return raw


async def run_remote_probe(
    point: ProbePoint,
    targets: list[dict[str, Any]],
    user: str,
    key_path: str,
    known_hosts_path: str,
    timeout: float,
) -> list[dict[str, Any]] | None:
    """Run probe.py on a point over SSH. None means the point gave no usable answer.

    The key is restricted by `command=` in the point's authorized_keys, so the
    command sent here is ignored and probe.py always runs.
    """

    async def run() -> asyncssh.SSHCompletedProcess:
        async with asyncssh.connect(
            point.host,
            username=user,
            client_keys=[key_path],
            known_hosts=known_hosts_path,
        ) as conn:
            return await conn.run("probe", input=json.dumps(targets), check=False)

    try:
        completed = await asyncio.wait_for(run(), timeout)
    except Exception as e:  # incl. KeyImportError (a ValueError) for a bad/locked key file
        logger.warning("Probe point %s unreachable: %r", point.name, e)
        return None

    if completed.exit_status != 0:
        logger.warning("Probe point %s exited with %s", point.name, completed.exit_status)
        return None
    try:
        raw = json.loads(str(completed.stdout))
    except ValueError:
        logger.warning("Probe point %s returned invalid JSON", point.name)
        return None
    results = _parse_results(raw, len(targets))
    if results is None:
        logger.warning("Probe point %s returned malformed results", point.name)
    return results


async def run_local_probe(
    targets: list[dict[str, Any]], timeout_per_target: float
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(probe_targets, targets, timeout_per_target)
