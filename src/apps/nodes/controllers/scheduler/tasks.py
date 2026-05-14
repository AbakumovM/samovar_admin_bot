import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.apps.incidents.adapters.gateway import PostgresIncidentGateway
from src.apps.incidents.adapters.view import PostgresIncidentView
from src.apps.incidents.application.interactor import IncidentInteractor
from src.apps.nodes.adapters.gateway import RemnaWaveNodeGateway
from src.apps.nodes.adapters.view import RemnaWaveNodeView
from src.apps.nodes.controllers.scheduler.loop import MonitoringLoop
from src.config import Config

logger = logging.getLogger(__name__)

NotifyFn = Callable[[str], Coroutine[Any, Any, None]]


def _make_loop(sdk: Any, session: Any, notify: NotifyFn, config: Config) -> MonitoringLoop:
    return MonitoringLoop(
        node_view=RemnaWaveNodeView(sdk=sdk, session=session),
        node_gateway=RemnaWaveNodeGateway(sdk=sdk, session=session),
        incident_interactor=IncidentInteractor(
            gateway=PostgresIncidentGateway(session=session),
            view=PostgresIncidentView(session=session),
        ),
        incident_view=PostgresIncidentView(session=session),
        notify=notify,
        escalation_window_minutes=config.escalation_window_minutes,
        escalation_max_attempts=config.escalation_max_attempts,
    )


async def monitoring_task(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    sdk: Any,
    notify: NotifyFn,
) -> None:
    logger.info("Starting monitoring loop (interval=%ds)", config.poll_interval_seconds)
    while True:
        try:
            async with session_factory() as session:
                async with session.begin():
                    await _make_loop(sdk, session, notify, config).poll()
        except Exception as e:
            logger.error("Monitoring poll error: %s", e)
        await asyncio.sleep(config.poll_interval_seconds)


async def fast_monitoring_task(
    config: Config,
    session_factory: async_sessionmaker,  # type: ignore[type-arg]
    sdk: Any,
    notify: NotifyFn,
) -> None:
    logger.info("Starting fast monitoring loop (interval=%ds)", config.fast_poll_interval_seconds)
    while True:
        await asyncio.sleep(config.fast_poll_interval_seconds)
        try:
            async with session_factory() as session:
                async with session.begin():
                    await _make_loop(sdk, session, notify, config).poll_offline()
        except Exception as e:
            logger.error("Fast monitoring poll error: %s", e)
