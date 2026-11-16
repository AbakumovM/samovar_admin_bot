import io
import json
import shutil
import socket
import ssl
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.infrastructure.reachability import probe


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port: int = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def plain_tcp_server() -> Iterator[int]:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port: int = srv.getsockname()[1]

    def serve() -> None:
        try:
            conn, _ = srv.accept()
            conn.close()
        except OSError:
            pass

    threading.Thread(target=serve, daemon=True).start()
    yield port
    srv.close()


@pytest.fixture
def tls_server(tmp_path: Path) -> Iterator[int]:
    if shutil.which("openssl") is None:
        pytest.skip("openssl not available")
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=t",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert), str(key))
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port: int = srv.getsockname()[1]

    def serve() -> None:
        try:
            conn, _ = srv.accept()
            with ctx.wrap_socket(conn, server_side=True) as tls:
                tls.recv(1)
        except OSError:
            pass

    threading.Thread(target=serve, daemon=True).start()
    yield port
    srv.close()


def test_validate_rejects_hostname() -> None:
    with pytest.raises(ValueError):
        probe.validate_targets([{"ip": "example.com", "port": 443, "sni": None}])


def test_validate_rejects_too_many() -> None:
    with pytest.raises(ValueError):
        probe.validate_targets([{"ip": "1.1.1.1", "port": 443, "sni": None}] * 201)


@pytest.mark.parametrize("port", [0, 70000])
def test_validate_rejects_bad_port(port: int) -> None:
    with pytest.raises(ValueError):
        probe.validate_targets([{"ip": "1.1.1.1", "port": port, "sni": None}])


def test_probe_refused() -> None:
    result = probe.probe_one("127.0.0.1", _free_port(), None, 2.0)
    assert result["result"] == "refused"


def test_probe_tls_fail_on_plain_tcp(plain_tcp_server: int) -> None:
    result = probe.probe_one("127.0.0.1", plain_tcp_server, "t", 2.0)
    assert result["result"] == "tls_fail"


def test_probe_ok_on_tls_server(tls_server: int) -> None:
    result = probe.probe_one("127.0.0.1", tls_server, "t", 2.0)
    assert result["result"] == "ok"
    assert result["ms"] >= 0


def test_main_bad_json_exit_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("nope"))
    assert probe.main() == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_probe_targets_keeps_order(plain_tcp_server: int) -> None:
    refused_port = _free_port()
    results = probe.probe_targets(
        [
            {"ip": "127.0.0.1", "port": refused_port, "sni": None},
            {"ip": "127.0.0.1", "port": plain_tcp_server, "sni": "t"},
        ],
        timeout=2.0,
    )
    assert [r["port"] for r in results] == [refused_port, plain_tcp_server]
    assert [r["result"] for r in results] == ["refused", "tls_fail"]
