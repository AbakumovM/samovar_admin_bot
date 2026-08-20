import io
import tarfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.infrastructure.geoip.downloader import download_asn_database


def _make_tar_gz(*, member_name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=member_name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _make_client(response: MagicMock) -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


async def test_download_asn_database_success_extracts_mmdb(tmp_path: Path) -> None:
    archive = _make_tar_gz(
        member_name="GeoLite2-ASN_20260101/GeoLite2-ASN.mmdb", content=b"fake-mmdb-bytes"
    )
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.content = archive
    target = tmp_path / "GeoLite2-ASN.mmdb"

    with patch("httpx.AsyncClient", return_value=_make_client(response)):
        ok = await download_asn_database("acc", "key", str(target))

    assert ok is True
    assert target.read_bytes() == b"fake-mmdb-bytes"


async def test_download_asn_database_creates_target_directory(tmp_path: Path) -> None:
    archive = _make_tar_gz(member_name="dir/GeoLite2-ASN.mmdb", content=b"data")
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.content = archive
    target = tmp_path / "nested" / "geoip" / "GeoLite2-ASN.mmdb"

    with patch("httpx.AsyncClient", return_value=_make_client(response)):
        ok = await download_asn_database("acc", "key", str(target))

    assert ok is True
    assert target.exists()


async def test_download_asn_database_http_error_returns_false(tmp_path: Path) -> None:
    client = MagicMock()
    client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError("401", request=MagicMock(), response=MagicMock())
    )
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=client):
        ok = await download_asn_database("acc", "key", str(tmp_path / "out.mmdb"))

    assert ok is False
    assert not (tmp_path / "out.mmdb").exists()


async def test_download_asn_database_missing_mmdb_in_archive_returns_false(tmp_path: Path) -> None:
    archive = _make_tar_gz(member_name="dir/readme.txt", content=b"not a database")
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.content = archive

    with patch("httpx.AsyncClient", return_value=_make_client(response)):
        ok = await download_asn_database("acc", "key", str(tmp_path / "out.mmdb"))

    assert ok is False


async def test_download_asn_database_corrupt_archive_returns_false(tmp_path: Path) -> None:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.content = b"not a valid tar.gz"

    with patch("httpx.AsyncClient", return_value=_make_client(response)):
        ok = await download_asn_database("acc", "key", str(tmp_path / "out.mmdb"))

    assert ok is False
