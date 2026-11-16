from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.reachability.adapters.gateway import PostgresReachabilityGateway
from src.apps.reachability.adapters.view import PostgresReachabilityView
from src.apps.reachability.application.interfaces.gateway import ReachabilityGateway
from src.apps.reachability.application.interfaces.view import ReachabilityView


class ReachabilityAdaptersProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def reachability_gateway(self, session: AsyncSession) -> ReachabilityGateway:
        return PostgresReachabilityGateway(session=session)

    @provide
    async def reachability_view(self, session: AsyncSession) -> ReachabilityView:
        return PostgresReachabilityView(session=session)
