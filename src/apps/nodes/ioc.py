from dishka import Provider, Scope, provide
from remnawave import RemnawaveSDK
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.nodes.adapters.gateway import RemnaWaveNodeGateway
from src.apps.nodes.adapters.view import RemnaWaveNodeView
from src.apps.nodes.application.interactor import NodeInteractor
from src.apps.nodes.application.interfaces.gateway import NodeGateway
from src.apps.nodes.application.interfaces.view import NodeView


class NodeAdaptersProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def node_gateway(self, sdk: RemnawaveSDK, session: AsyncSession) -> NodeGateway:
        return RemnaWaveNodeGateway(sdk=sdk, session=session)

    @provide
    async def node_view(self, sdk: RemnawaveSDK, session: AsyncSession) -> NodeView:
        return RemnaWaveNodeView(sdk=sdk, session=session)


class NodeInteractorsProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def node_interactor(
        self, gateway: NodeGateway, view: NodeView
    ) -> NodeInteractor:
        return NodeInteractor(gateway=gateway, view=view)
