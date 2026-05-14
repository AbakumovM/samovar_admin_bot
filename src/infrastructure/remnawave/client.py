from remnawave import RemnawaveSDK

from src.config import Config


def create_remnawave_client(config: Config) -> RemnawaveSDK:
    return RemnawaveSDK(
        base_url=config.remnawave_base_url,
        token=config.remnawave_token,
    )
