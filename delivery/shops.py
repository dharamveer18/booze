"""Helpers to find which licensed shop is serving the current visitor."""

from datetime import date

from .models import RetailShop

SHOP_SESSION_KEY = "shop_id"


def licensed_shops():
    """Only shops that are active, verified and whose licence has not expired."""
    return RetailShop.objects.filter(
        is_active=True,
        is_licence_verified=True,
        licence_valid_till__gte=date.today(),
    ).order_by("name")


def get_current_shop(request):
    """
    The shop the visitor is currently browsing.
    Later this can be replaced by "nearest shop to the customer's location".
    """
    shops = licensed_shops()
    shop_id = request.session.get(SHOP_SESSION_KEY)
    shop = shops.filter(id=shop_id).first() if shop_id else None
    return shop or shops.first()
