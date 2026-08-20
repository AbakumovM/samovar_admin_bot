from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.antifraud.adapters.gateway import PostgresAntifraudGateway
from src.apps.antifraud.adapters.view import PostgresAntifraudCooldownView
from src.apps.antifraud.application.interactor import AntifraudInteractor
from src.apps.antifraud.application.interfaces.gateway import AntifraudGateway
from src.apps.antifraud.application.interfaces.view import AntifraudCooldownView


class AntifraudAdaptersProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def antifraud_gateway(self, session: AsyncSession) -> AntifraudGateway:
        return PostgresAntifraudGateway(session=session)

    @provide
    async def antifraud_view(self, session: AsyncSession) -> AntifraudCooldownView:
        return PostgresAntifraudCooldownView(session=session)


class AntifraudInteractorsProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def antifraud_interactor(
        self, gateway: AntifraudGateway, view: AntifraudCooldownView
    ) -> AntifraudInteractor:
        return AntifraudInteractor(gateway=gateway, view=view)
