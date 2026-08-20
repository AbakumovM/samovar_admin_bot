import asyncio
import logging
import os

from src.infrastructure.geoip.asn import MaxMindAsnResolver
from src.infrastructure.geoip.downloader import download_asn_database

logger = logging.getLogger(__name__)


async def maxmind_update_task(
    resolver: MaxMindAsnResolver,
    account_id: str,
    license_key: str,
    database_path: str,
    update_interval_hours: int,
) -> None:
    if not account_id or not license_key:
        logger.info("Antifraud ASN: MaxMind credentials not configured, skipping auto-update")
        return

    if not os.path.exists(database_path):
        logger.info("Antifraud ASN: database not found locally, downloading now")
        if await download_asn_database(account_id, license_key, database_path):
            resolver.reload()

    while True:
        await asyncio.sleep(update_interval_hours * 3600)
        if await download_asn_database(account_id, license_key, database_path):
            resolver.reload()
