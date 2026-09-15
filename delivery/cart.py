"""
A tiny session-based cart.

The cart is stored in the user's session as:  {"<shop_product_id>": quantity}
Because every product on the page comes from the currently selected shop,
a cart always belongs to a single licensed shop.
"""

from decimal import Decimal

from django.conf import settings

from .models import ShopProduct

CART_SESSION_KEY = "cart"
MAX_QTY_PER_ITEM = 6


class Cart:
    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(CART_SESSION_KEY, {})

    def save(self):
        self.session[CART_SESSION_KEY] = self.data
        self.session.modified = True

    def get_quantity(self, shop_product_id):
        return self.data.get(str(shop_product_id), 0)

    def change(self, shop_product, delta):
        """Add (delta=+1) or remove (delta=-1) one unit."""
        key = str(shop_product.id)
        new_qty = self.data.get(key, 0) + delta
        new_qty = min(new_qty, MAX_QTY_PER_ITEM, shop_product.stock)

        if new_qty <= 0:
            self.data.pop(key, None)
        else:
            self.data[key] = new_qty
        self.save()

    def clear(self):
        self.data = {}
        self.save()

    def items(self):
        """Returns a list of dicts with the ShopProduct, quantity and line total."""
        shop_products = ShopProduct.objects.filter(id__in=self.data.keys()).select_related("product__category", "shop")
        rows = []
        for sp in shop_products:
            qty = self.data[str(sp.id)]
            rows.append({"shop_product": sp, "quantity": qty, "line_total": sp.price * qty})
        return rows

    @property
    def count(self):
        return sum(self.data.values())

    def summary(self):
        items = self.items()
        item_total = sum((row["line_total"] for row in items), Decimal("0"))
        mrp_total = sum((row["shop_product"].product.mrp * row["quantity"] for row in items), Decimal("0"))

        if not items or item_total >= settings.FREE_DELIVERY_ABOVE:
            delivery_fee = Decimal("0")
        else:
            delivery_fee = settings.DELIVERY_FEE
        platform_fee = settings.PLATFORM_FEE if items else Decimal("0")

        return {
            "items": items,
            "count": self.count,
            "item_total": item_total,
            "mrp_total": mrp_total,
            "savings": max(mrp_total - item_total, Decimal("0")),
            "delivery_fee": delivery_fee,
            "standard_delivery_fee": settings.DELIVERY_FEE,
            "platform_fee": platform_fee,
            "grand_total": item_total + delivery_fee + platform_fee,
            "free_delivery_above": settings.FREE_DELIVERY_ABOVE,
            "amount_for_free_delivery": max(settings.FREE_DELIVERY_ABOVE - item_total, Decimal("0")),
        }
