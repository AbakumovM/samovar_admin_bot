import asyncio
import logging

from aiogram import Bot, Dispatcher
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka

from src.apps.incidents.controllers.scheduler.tasks import daily_report_task
from src.apps.incidents.controllers.telegram.handlers import router as incidents_router
from src.apps.incidents.ioc import IncidentAdaptersProvider, IncidentInteractorsProvider
from src.apps.nodes.controllers.scheduler.tasks import fast_monitoring_task, monitoring_task
from src.apps.nodes.controllers.telegram.handlers import router as nodes_router
from src.apps.nodes.ioc import NodeAdaptersProvider, NodeInteractorsProvider
from src.config import Config
from src.infrastructure.db.engine import create_engine
from src.infrastructure.db.session import create_session_factory
from src.infrastructure.remnawave.client import create_remnawave_client
from src.infrastructure.telegram.setup import create_bot, create_dispatcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _make_notify_fn(bot: Bot, admin_ids: list[int]):  # type: ignore[no-untyped-def]
    async def notify(text: str) -> None:
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error("Failed to notify admin %s: %s", admin_id, e)

    return notify


async def main() -> None:
    config = Config()
    engine = create_engine(config)
    session_factory = create_session_factory(engine)
    sdk = create_remnawave_client(config)
    bot = create_bot(config)
    dp: Dispatcher = create_dispatcher(config)

    from collections.abc import AsyncIterable

    from dishka import Provider, Scope
    from dishka import provide as dishka_provide
    from remnawave import RemnawaveSDK
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    class InfraProvider(Provider):
        scope = Scope.APP

        @dishka_provide
        async def get_engine(self) -> AsyncEngine:
            return engine

        @dishka_provide
        async def get_sdk(self) -> RemnawaveSDK:
            return sdk

    class SessionProvider(Provider):
        @dishka_provide(scope=Scope.APP)
        async def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
            return session_factory

        @dishka_provide(scope=Scope.REQUEST)
        async def get_session(
            self, session_fac: async_sessionmaker[AsyncSession]
        ) -> AsyncIterable[AsyncSession]:
            async with session_fac() as session:
                async with session.begin():
                    yield session

    container = make_async_container(
        InfraProvider(),
        SessionProvider(),
        NodeAdaptersProvider(),
        NodeInteractorsProvider(),
        IncidentAdaptersProvider(),
        IncidentInteractorsProvider(),
    )
    setup_dishka(container=container, router=dp)

    dp.include_router(nodes_router)
    dp.include_router(incidents_router)

    notify = await _make_notify_fn(bot, config.admin_ids)

    from aiogram.types import BotCommand

    await bot.set_my_commands([
        BotCommand(command="status", description="Состояние всех нод"),
        BotCommand(command="node", description="Детали по ноде: /node <имя>"),
        BotCommand(command="incidents", description="Последние инциденты"),
        BotCommand(command="stats", description="Статистика: /stats day|week|month"),
        BotCommand(command="worst", description="Топ проблемных нод"),
        BotCommand(command="providers", description="Инциденты по регионам"),
        BotCommand(command="restart", description="Рестарт ноды: /restart <имя>"),
        BotCommand(command="restart_all", description="Рестарт всех нод"),
        BotCommand(command="mute", description="Заглушить алерты: /mute <имя> 30m|1h|24h"),
        BotCommand(command="unmute", description="Снять мут: /unmute <имя>"),
        BotCommand(command="report", description="Отчёт за последние 24 часа"),
    ])

    logger.info("Starting bot and monitoring loop")
    await asyncio.gather(
        dp.start_polling(bot),
        monitoring_task(config, session_factory, sdk, notify),
        fast_monitoring_task(config, session_factory, sdk, notify),
        daily_report_task(config, session_factory, notify),
    )


if __name__ == "__main__":
    asyncio.run(main())
