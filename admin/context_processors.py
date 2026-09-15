from delivery.models import DeliveryPartner, RetailShop

from .scope import visible_orders


def panel(request):
    """Small counters shown as badges in the admin sidebar (only on admin pages)."""
    match = request.resolver_match
    user = request.user
    if not match or match.namespace != "panel" or not user.is_authenticated or not user.can_use_panel:
        return {}

    counts = {"active_orders": visible_orders(user).exclude(status__in=["delivered", "cancelled"]).count()}
    if user.is_admin:
        counts["pending_shops"] = RetailShop.objects.filter(is_licence_verified=False).count()
        counts["pending_partners"] = DeliveryPartner.objects.filter(is_verified=False).count()
    return {"nav_counts": counts}
