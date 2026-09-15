from decimal import Decimal

from django import template

register = template.Library()

ORDER_TONES = {
    "placed": "blue",
    "confirmed": "violet",
    "packed": "amber",
    "picked_up": "amber",
    "delivered": "green",
    "cancelled": "red",
}
ROLE_TONES = {"customer": "gray", "shop_owner": "violet", "delivery_partner": "blue", "admin": "green"}
AVATAR_TONES = ["blue", "violet", "amber", "green", "rose", "teal"]


@register.filter
def order_tone(status):
    """Colour name for an order status pill:  {{ order.status|order_tone }}"""
    return ORDER_TONES.get(status, "gray")


@register.filter
def role_tone(role):
    return ROLE_TONES.get(role, "gray")


@register.filter
def initials(user):
    name = user.get_full_name() or user.username
    return "".join(part[0] for part in name.split()[:2]).upper()


@register.filter
def avatar_tone(user):
    return AVATAR_TONES[user.pk % len(AVATAR_TONES)] if user.pk else "gray"


@register.filter
def inr(value):
    """Indian number format without decimals: 1234567 -> ₹12,34,567"""
    if value in (None, ""):
        return "₹0"
    number = str(int(Decimal(value).quantize(Decimal("1"))))
    sign = "-" if number.startswith("-") else ""
    number = number.lstrip("-")
    if len(number) > 3:
        head, tail = number[:-3], number[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        number = ",".join(groups) + "," + tail
    return f"{sign}₹{number}"


@register.filter
def percent_of(value, total):
    """Width for a bar:  style="width: {{ count|percent_of:max }}%" """
    return round(value / total * 100, 1) if total else 0


@register.filter
def get_count(counts, key):
    """{{ role_counts|get_count:"customer" }} -> 0 when the key is missing"""
    return counts.get(key, 0)
