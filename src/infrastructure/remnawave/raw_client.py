import httpx

from src.config import Config


def create_remnawave_raw_client(config: Config) -> httpx.AsyncClient:
    """HTTP client bypassing the remnawave SDK's Pydantic response models.

    The installed SDK targets panel API v2.8.0; the panel itself runs
    v3.2.3. For a few endpoints the response shape has diverged enough
    (e.g. users dropped `uuid` in favor of numeric `id`; infra-billing
    history records dropped `nodeUuid`) that the SDK's models raise
    ValidationError on every call. Use this client for those endpoints
    until an SDK release catches up.
    """
    base_url = config.remnawave_base_url.rstrip("/")
    if not base_url.endswith("/api"):
        base_url += "/api"
    return httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {config.remnawave_token}"},
        timeout=30,
    )
