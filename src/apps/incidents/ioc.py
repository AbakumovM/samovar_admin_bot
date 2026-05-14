from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.incidents.adapters.gateway import PostgresIncidentGateway
from src.apps.incidents.adapters.view import PostgresIncidentView
from src.apps.incidents.application.interactor import IncidentInteractor
from src.apps.incidents.application.interfaces.gateway import IncidentGateway
from src.apps.incidents.application.interfaces.view import IncidentView


class IncidentAdaptersProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def incident_gateway(self, session: AsyncSession) -> IncidentGateway:
        return PostgresIncidentGateway(session=session)

    @provide
    async def incident_view(self, session: AsyncSession) -> IncidentView:
        return PostgresIncidentView(session=session)


class IncidentInteractorsProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def incident_interactor(
        self,
        gateway: IncidentGateway,
        view: IncidentView,
    ) -> IncidentInteractor:
        return IncidentInteractor(gateway=gateway, view=view)
