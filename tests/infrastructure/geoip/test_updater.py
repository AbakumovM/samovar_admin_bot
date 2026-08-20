from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.geoip.updater import maxmind_update_task


async def test_no_credentials_skips_download_entirely() -> None:
    resolver = MagicMock()
    with (
        patch("src.infrastructure.geoip.updater.download_asn_database", AsyncMock()) as download,
        patch("os.path.exists", return_value=False),
    ):
        await maxmind_update_task(resolver, "", "", "/tmp/db.mmdb", update_interval_hours=168)

    download.assert_not_awaited()
    resolver.reload.assert_not_called()


async def test_missing_database_downloads_and_reloads_on_success() -> None:
    resolver = MagicMock()
    with (
        patch(
            "src.infrastructure.geoip.updater.download_asn_database", AsyncMock(return_value=True)
        ) as download,
        patch("os.path.exists", return_value=False),
        patch("asyncio.sleep", AsyncMock(side_effect=asyncio_stop())),
    ):
        try:
            await maxmind_update_task(resolver, "acc", "key", "/tmp/db.mmdb", 168)
        except _StopLoop:
            pass

    download.assert_awaited_once_with("acc", "key", "/tmp/db.mmdb")
    resolver.reload.assert_called_once()


async def test_missing_database_download_failure_skips_reload() -> None:
    resolver = MagicMock()
    with (
        patch(
            "src.infrastructure.geoip.updater.download_asn_database",
            AsyncMock(return_value=False),
        ),
        patch("os.path.exists", return_value=False),
        patch("asyncio.sleep", AsyncMock(side_effect=asyncio_stop())),
    ):
        try:
            await maxmind_update_task(resolver, "acc", "key", "/tmp/db.mmdb", 168)
        except _StopLoop:
            pass

    resolver.reload.assert_not_called()


async def test_existing_database_skips_immediate_download() -> None:
    resolver = MagicMock()
    with (
        patch(
            "src.infrastructure.geoip.updater.download_asn_database", AsyncMock()
        ) as download,
        patch("os.path.exists", return_value=True),
        patch("asyncio.sleep", AsyncMock(side_effect=asyncio_stop())),
    ):
        try:
            await maxmind_update_task(resolver, "acc", "key", "/tmp/db.mmdb", 168)
        except _StopLoop:
            pass

    download.assert_not_awaited()  # only the periodic branch would call it, which we never reach


class _StopLoop(Exception):
    pass


def asyncio_stop() -> _StopLoop:
    return _StopLoop()
