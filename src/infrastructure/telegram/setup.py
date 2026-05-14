from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import Config
from src.infrastructure.telegram.middleware import AdminAuthMiddleware


def create_bot(config: Config) -> Bot:
    return Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(config: Config) -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(AdminAuthMiddleware(admin_ids=config.admin_ids))
    return dp
