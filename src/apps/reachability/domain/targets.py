import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IpTarget:
    ip: str
    port: int
    sni: str | None
    tiles: tuple[str, ...]  # "remark (address)"
    node_names: tuple[str, ...]


def _is_ip_literal(address: str) -> bool:
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return False
    return True


def select_hosts(hosts: list[dict[str, Any]], tags: set[str]) -> list[dict[str, Any]]:
    return [h for h in hosts if not h.get("isDisabled") and tags & set(h.get("tags") or [])]


def build_targets(
    hosts: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    resolved: dict[str, list[str]],
) -> list[IpTarget]:
    """Group hosts by resolved IP: one target per IP, listing every tile and node on it."""
    node_names = {str(n["uuid"]): str(n["name"]) for n in nodes}
    by_ip: dict[str, dict[str, Any]] = {}
    for host in hosts:
        address = str(host["address"])
        for ip in resolved.get(address, []):
            entry = by_ip.setdefault(
                ip,
                {
                    "port": int(host["port"]),
                    "sni": host.get("sni") or (None if _is_ip_literal(address) else address),
                    "tiles": [],
                    "nodes": set(),
                },
            )
            tile = f"{host['remark']} ({address})"
            if tile not in entry["tiles"]:
                entry["tiles"].append(tile)
            for node_uuid in host.get("nodes") or []:
                if str(node_uuid) in node_names:
                    entry["nodes"].add(node_names[str(node_uuid)])
    return [
        IpTarget(
            ip=ip,
            port=entry["port"],
            sni=entry["sni"],
            tiles=tuple(entry["tiles"]),
            node_names=tuple(sorted(entry["nodes"])),
        )
        for ip, entry in by_ip.items()
    ]


async def resolve_addresses(addresses: set[str]) -> dict[str, list[str]]:
    loop = asyncio.get_running_loop()

    async def resolve(address: str) -> tuple[str, list[str]]:
        if _is_ip_literal(address):
            return address, [address]
        try:
            infos = await loop.getaddrinfo(address, None, family=socket.AF_INET)
        except OSError:
            return address, []
        return address, sorted({str(info[4][0]) for info in infos})

    pairs = await asyncio.gather(*(resolve(a) for a in addresses))
    return {address: ips for address, ips in pairs if ips}
