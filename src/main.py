import asyncio
import logging

from aiogram import Bot, Dispatcher
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka

from src.apps.antifraud.controllers.scheduler.tasks import antifraud_scan_task
from src.apps.antifraud.controllers.telegram.handlers import router as antifraud_router
from src.apps.antifraud.ioc import AntifraudAdaptersProvider, AntifraudInteractorsProvider
from src.apps.billing.controllers.scheduler.tasks import billing_alert_task
from src.apps.billing.controllers.telegram.handlers import router as billing_router
from src.apps.billing.ioc import BillingAdaptersProvider
from src.apps.incidents.controllers.scheduler.tasks import daily_report_task
from src.apps.incidents.controllers.telegram.handlers import router as incidents_router
from src.apps.incidents.ioc import IncidentAdaptersProvider, IncidentInteractorsProvider
from src.apps.nodes.controllers.scheduler.tasks import fast_monitoring_task, monitoring_task
from src.apps.nodes.controllers.telegram.handlers import router as nodes_router
from src.apps.nodes.ioc import NodeAdaptersProvider, NodeInteractorsProvider
from src.apps.users.controllers.scheduler.tasks import traffic_monitoring_task
from src.apps.users.controllers.telegram.handlers import router as users_router
from src.apps.users.ioc import UserTrafficAdaptersProvider
from src.config import Config
from src.infrastructure.db.engine import create_engine
from src.infrastructure.db.session import create_session_factory
from src.infrastructure.geoip.asn import AsnResolver, MaxMindAsnResolver, NopAsnResolver
from src.infrastructure.geoip.updater import maxmind_update_task
from src.infrastructure.remnawave.client import create_remnawave_client
from src.infrastructure.remnawave.raw_client import create_remnawave_raw_client
from src.infrastructure.remnawave.user_cache import UserLookupCache
from src.infrastructure.samovarbot.client import SamovarbotClient, create_samovarbot_client
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
    raw_client = create_remnawave_raw_client(config)
    samovarbot_client = create_samovarbot_client(config)
    bot = create_bot(config)
    dp: Dispatcher = create_dispatcher(config)

    user_cache = UserLookupCache(ttl_seconds=config.antifraud_user_cache_ttl_seconds)
    asn_resolver: AsnResolver
    if config.antifraud_asn_grouping:
        asn_resolver = MaxMindAsnResolver(config.antifraud_asn_database_path)
    else:
        asn_resolver = NopAsnResolver()

    from collections.abc import AsyncIterable

    import httpx
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

        @dishka_provide
        async def get_raw_client(self) -> httpx.AsyncClient:
            return raw_client

        @dishka_provide
        async def get_samovarbot_client(self) -> SamovarbotClient:
            return samovarbot_client

        @dishka_provide
        async def get_config(self) -> Config:
            return config

        @dishka_provide
        async def get_user_cache(self) -> UserLookupCache:
            return user_cache

        @dishka_provide
        async def get_asn_resolver(self) -> AsnResolver:
            return asn_resolver

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
        UserTrafficAdaptersProvider(),
        BillingAdaptersProvider(),
        AntifraudAdaptersProvider(),
        AntifraudInteractorsProvider(),
    )
    setup_dishka(container=container, router=dp)

    dp.include_router(nodes_router)
    dp.include_router(incidents_router)
    dp.include_router(users_router)
    dp.include_router(billing_router)
    dp.include_router(antifraud_router)

    notify = await _make_notify_fn(bot, config.admin_ids)

    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [
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
            BotCommand(
                command="top_traffic", description="Топ потребителей: /top_traffic day|week|month"
            ),  # noqa: E501
            BotCommand(command="anomalies", description="Аномалии трафика сегодня"),
            BotCommand(
                command="user_traffic", description="Трафик пользователя: /user_traffic <имя>"
            ),
            BotCommand(command="billing", description="Предстоящие платежи нод"),
            BotCommand(command="billing_history", description="История платежей"),
            BotCommand(command="antifraud_check", description="Разовая проверка антифрода"),
        ]
    )

    logger.info("Starting bot and monitoring loop")
    tasks = [
        dp.start_polling(bot),
        monitoring_task(config, session_factory, sdk, raw_client, notify),
        fast_monitoring_task(config, session_factory, sdk, raw_client, notify),
        daily_report_task(config, session_factory, notify),
        traffic_monitoring_task(config, session_factory, raw_client, notify),
        billing_alert_task(config, sdk, raw_client, bot),
        antifraud_scan_task(
            config,
            session_factory,
            sdk,
            raw_client,
            bot,
            user_cache,
            asn_resolver,
            samovarbot_client,
        ),
    ]
    if isinstance(asn_resolver, MaxMindAsnResolver):
        tasks.append(
            maxmind_update_task(
                asn_resolver,
                config.antifraud_maxmind_account_id,
                config.antifraud_maxmind_license_key,
                config.antifraud_asn_database_path,
                config.antifraud_maxmind_update_interval_hours,
            )
        )
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
