import io
import logging
import os
import tarfile

import httpx

logger = logging.getLogger(__name__)

_DOWNLOAD_URL = "https://download.maxmind.com/geoip/databases/GeoLite2-ASN/download?suffix=tar.gz"


async def download_asn_database(account_id: str, license_key: str, target_path: str) -> bool:
    """Download and extract the current GeoLite2-ASN.mmdb to target_path.

    Returns True on success. Never raises — network/parse failures are
    logged and reported as a plain False so the caller (a periodic updater)
    can just retry next cycle without crashing.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            response = await client.get(_DOWNLOAD_URL, auth=(account_id, license_key))
            response.raise_for_status()
    except Exception as e:
        logger.error("Antifraud ASN: failed to download MaxMind database: %s", e)
        return False

    try:
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
            member = next((m for m in tar.getmembers() if m.name.endswith(".mmdb")), None)
            if member is None:
                logger.error("Antifraud ASN: no .mmdb file found in downloaded archive")
                return False
            extracted = tar.extractfile(member)
            if extracted is None:
                logger.error("Antifraud ASN: could not read .mmdb member from archive")
                return False
            data = extracted.read()
    except Exception as e:
        logger.error("Antifraud ASN: failed to extract MaxMind database: %s", e)
        return False

    target_dir = os.path.dirname(target_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)
    tmp_path = target_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.replace(tmp_path, target_path)  # atomic swap — a concurrent reader never sees a partial file

    logger.info("Antifraud ASN: database updated at %s (%d bytes)", target_path, len(data))
    return True
