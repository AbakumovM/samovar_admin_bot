#!/usr/bin/env python3
"""TCP + TLS reachability probe.

Self-contained (stdlib only, Python 3.10+): the same file runs inside the
admin bot (the "outside" vantage point) and is copied to probe nodes in
Russia, where the admin bot invokes it over SSH through a key restricted by
`command=` in authorized_keys. Reads a JSON list of targets from stdin and
prints a JSON list of results to stdout.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

MAX_TARGETS = 200
MAX_INPUT_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 5.0


def validate_targets(raw: object, allow_local: bool = False) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("targets must be a list")
    if len(raw) > MAX_TARGETS:
        raise ValueError(f"too many targets (max {MAX_TARGETS})")
    targets: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("target must be an object")
        ip = item.get("ip")
        port = item.get("port")
        sni = item.get("sni")
        if not isinstance(ip, str):
            raise ValueError("ip must be a string")
        address = ipaddress.ip_address(ip)  # raises ValueError for hostnames
        if not allow_local and not address.is_global:
            # A leaked key must not turn into a scanner of the point's own/LAN ports.
            raise ValueError(f"non-global address: {ip}")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"bad port: {port!r}")
        if sni is not None and not isinstance(sni, str):
            raise ValueError("sni must be a string or null")
        targets.append({"ip": ip, "port": port, "sni": sni})
    return targets


def probe_one(ip: str, port: int, sni: str | None, timeout: float) -> dict[str, Any]:
    started = time.monotonic()

    def done(result: str) -> dict[str, Any]:
        return {
            "ip": ip,
            "port": port,
            "result": result,
            "ms": int((time.monotonic() - started) * 1000),
        }

    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
    except ConnectionRefusedError:
        return done("refused")
    except OSError:
        return done("timeout")

    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # Reality serves someone else's certificate
        # The handshake runs inside wrap_socket under the socket's connect timeout.
        with ctx.wrap_socket(sock, server_hostname=sni):
            pass
        return done("ok")
    except TimeoutError:
        return done("timeout")
    except (OSError, ssl.SSLError, ValueError):  # ValueError: SNI rejected by the idna codec
        return done("tls_fail")
    finally:
        sock.close()


def probe_targets(
    targets: list[dict[str, Any]], timeout: float, workers: int = 32
) -> list[dict[str, Any]]:
    if not targets:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as pool:
        return list(pool.map(lambda t: probe_one(t["ip"], t["port"], t["sni"], timeout), targets))


def main() -> int:
    raw = sys.stdin.read(MAX_INPUT_BYTES + 1)
    try:
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input too large")
        targets = validate_targets(json.loads(raw))
    except ValueError as e:  # json.JSONDecodeError is a ValueError
        print(json.dumps({"error": str(e)}))
        return 2
    print(json.dumps(probe_targets(targets, DEFAULT_TIMEOUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
