from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.users.adapters.gateway import PostgresUserTrafficGateway
from src.apps.users.adapters.view import PostgresUserTrafficView
from src.apps.users.application.interfaces.gateway import UserTrafficGateway
from src.apps.users.application.interfaces.view import UserTrafficView


class UserTrafficAdaptersProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def user_traffic_gateway(self, session: AsyncSession) -> UserTrafficGateway:
        return PostgresUserTrafficGateway(session=session)

    @provide
    async def user_traffic_view(self, session: AsyncSession) -> UserTrafficView:
        return PostgresUserTrafficView(session=session)
