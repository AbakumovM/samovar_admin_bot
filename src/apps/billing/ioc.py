from dishka import Provider, Scope, provide
from remnawave import RemnawaveSDK

from src.apps.billing.adapters.view import RemnawaveBillingView
from src.apps.billing.application.interfaces.view import BillingView


class BillingAdaptersProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def billing_view(self, sdk: RemnawaveSDK) -> BillingView:
        return RemnawaveBillingView(sdk=sdk)
