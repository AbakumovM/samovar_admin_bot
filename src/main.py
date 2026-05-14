import asyncio
import logging

from aiogram import Bot, Dispatcher
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka

from src.apps.incidents.adapters.gateway import PostgresIncidentGateway
from src.apps.incidents.adapters.view import PostgresIncidentView
from src.apps.incidents.application.interactor import IncidentInteractor
from src.apps.incidents.controllers.telegram.handlers import router as incidents_router
from src.apps.incidents.ioc import IncidentAdaptersProvider, IncidentInteractorsProvider
from src.apps.nodes.adapters.gateway import RemnaWaveNodeGateway
from src.apps.nodes.adapters.view import RemnaWaveNodeView
from src.apps.nodes.controllers.scheduler.loop import MonitoringLoop
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


async def _monitoring_task(
    config: Config,
    session_factory,  # type: ignore[no-untyped-def]
    sdk,  # type: ignore[no-untyped-def]
    notify,  # type: ignore[no-untyped-def]
) -> None:
    logger.info("Starting monitoring loop (interval=%ds)", config.poll_interval_seconds)
    while True:
        try:
            async with session_factory() as session:
                async with session.begin():
                    node_gw = RemnaWaveNodeGateway(sdk=sdk, session=session)
                    node_vw = RemnaWaveNodeView(sdk=sdk, session=session)
                    inc_gw = PostgresIncidentGateway(session=session)
                    inc_vw = PostgresIncidentView(session=session)
                    inc_interactor = IncidentInteractor(gateway=inc_gw, view=inc_vw)
                    loop = MonitoringLoop(
                        node_view=node_vw,
                        node_gateway=node_gw,
                        incident_interactor=inc_interactor,
                        incident_view=inc_vw,
                        notify=notify,
                        escalation_window_minutes=config.escalation_window_minutes,
                        escalation_max_attempts=config.escalation_max_attempts,
                    )
                    await loop.poll()
        except Exception as e:
            logger.error("Monitoring poll error: %s", e)
        await asyncio.sleep(config.poll_interval_seconds)


async def main() -> None:
    config = Config()
    engine = create_engine(config)
    session_factory = create_session_factory(engine)
    sdk = create_remnawave_client(config)
    bot = create_bot(config)
    dp: Dispatcher = create_dispatcher(config)

    dp.include_router(nodes_router)
    dp.include_router(incidents_router)

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
        async def get_session_factory(
            self, eng: AsyncEngine
        ) -> async_sessionmaker[AsyncSession]:
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

    notify = await _make_notify_fn(bot, config.admin_ids)

    logger.info("Starting bot and monitoring loop")
    await asyncio.gather(
        dp.start_polling(bot),
        _monitoring_task(config, session_factory, sdk, notify),
    )


if __name__ == "__main__":
    asyncio.run(main())
