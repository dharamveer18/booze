from django.conf import settings

from .cart import Cart
from .shops import get_current_shop, licensed_shops


def storefront(request):
    """Values every page needs: header shop, cart badge, age gate."""
    summary = Cart(request).summary()
    return {
        "current_shop": get_current_shop(request),
        "all_shops": licensed_shops(),
        "cart": summary,
        "delivery_minutes": settings.ESTIMATED_DELIVERY_MINUTES,
        "legal_age": settings.LEGAL_DRINKING_AGE,
        "age_gate_passed": request.session.get("age_gate_passed", False),
    }
