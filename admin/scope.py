"""
What each panel user is allowed to see.

    admin    -> every shop and every order
    retailer -> only the shops they own, and orders placed at those shops

Views always start from these querysets, so a retailer can never open
another shop's page or order, even by typing the URL.
"""

from delivery.models import Order, RetailShop


def visible_shops(user):
    if user.is_admin:
        return RetailShop.objects.all()
    return RetailShop.objects.filter(owner__user=user)


def visible_orders(user):
    if user.is_admin:
        return Order.objects.all()
    return Order.objects.filter(shop__owner__user=user)
