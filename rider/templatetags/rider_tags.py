from django import template

register = template.Library()


@register.filter
def drop_area(address):
    """Hide the flat/house number until the rider accepts: 'Flat 12, Carter Rd, Bandra, Mumbai' -> 'Bandra, Mumbai'"""
    parts = [part.strip() for part in address.split(",") if part.strip()]
    return ", ".join(parts[-2:])


@register.filter
def ago(value):
    """Short relative time: '5 min ago', '3 h ago', '2 d ago'"""
    from django.utils import timezone
    if not value:
        return ""
    minutes = int((timezone.now() - value).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 60 * 24:
        return f"{minutes // 60} h ago"
    return f"{minutes // (60 * 24)} d ago"


@register.filter
def minutes_between(start, end):
    if not start or not end:
        return ""
    return max(int((end - start).total_seconds() // 60), 0)


@register.filter
def trip_minutes(distance_km):
    """Rough trip time for a city ride: ~3 min per km plus pickup time."""
    return int(float(distance_km or 0) * 3) + 4


@register.filter
def duration(minutes):
    """95 -> '1h 35m'"""
    minutes = int(minutes or 0)
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m" if hours else f"{mins}m"


@register.filter
def map_point(order, which):
    """
    Dummy map positions (in a 360x240 SVG) until real GPS/maps are connected.
    Stable per order, so the pins don't jump around between page loads.
    """
    seed = order.pk or 1
    if which == "shop":
        return (60 + seed * 37 % 60, 60 + seed * 53 % 120)
    return (240 + seed * 41 % 70, 50 + seed * 29 % 140)


@register.simple_tag
def route_path(order):
    """An SVG path from the shop to the customer that follows a street-like dogleg."""
    sx, sy = map_point(order, "shop")
    cx, cy = map_point(order, "customer")
    mid_x = (sx + cx) // 2
    return f"M{sx} {sy} H{mid_x} V{cy} H{cx}"
