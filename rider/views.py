"""
The delivery partner app.

A delivery goes through these steps (each one saves a timestamp on the Order):

    accept  ->  reached shop  ->  picked up  ->  reached customer  ->  delivered
                                                   (or)  ->  cancelled (problem at the door)

Every view gets the logged-in DeliveryPartner as `partner` (see decorators.rider_required),
and riders can only ever open orders assigned to them.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from delivery.models import Order

from .decorators import rider_required
from .forms import DeliverForm, ReportIssueForm, RiderLoginForm

# Orders that riders can pick up from the "New orders" list
OPEN_STATUSES = [Order.Status.PLACED, Order.Status.CONFIRMED, Order.Status.PACKED]
FINISHED_STATUSES = [Order.Status.DELIVERED, Order.Status.CANCELLED]

WEEKLY_TARGET = 40            # deliveries per week for the bonus
WEEKLY_BONUS = Decimal("500")

# (key, label, timestamp field on Order)
TRIP_STEPS = [
    ("accepted", "Order accepted", "assigned_at"),
    ("reached_shop", "Reached shop", "reached_shop_at"),
    ("picked_up", "Picked up", "picked_up_at"),
    ("reached_customer", "Reached customer", "reached_customer_at"),
    ("delivered", "Delivered", "delivered_at"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def start_of_today():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


def start_of_week():
    today = start_of_today()
    return today - timedelta(days=today.weekday())  # Monday


def active_order_for(partner):
    return (
        partner.orders.exclude(status__in=FINISHED_STATUSES)
        .select_related("shop", "customer__user")
        .first()
    )


def earnings_since(partner, start):
    result = partner.orders.filter(status=Order.Status.DELIVERED, delivered_at__gte=start).aggregate(
        total=Sum("rider_earning"), count=Count("id"), km=Sum("distance_km")
    )
    return {"total": result["total"] or Decimal("0"), "count": result["count"], "km": result["km"] or Decimal("0")}


def trip_stage(order):
    """Which step the rider is on: index of the next step to complete (5 = done)."""
    for index, (_, _, field) in enumerate(TRIP_STEPS):
        if not getattr(order, field):
            return index
    return len(TRIP_STEPS)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated and hasattr(request.user, "delivery_partner"):
        return redirect("rider:home")

    form = RiderLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("rider:home")
    return render(request, "rider/login.html", {"form": form})


@require_POST
def logout_view(request):
    partner = getattr(request.user, "delivery_partner", None)
    if partner and partner.is_online and not active_order_for(partner):
        partner.is_online = False
        partner.save(update_fields=["is_online"])
    logout(request)
    return redirect("rider:login")


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@rider_required
def home(request, partner):
    active = active_order_for(partner)
    skipped = request.session.get("skipped_orders", [])

    new_orders = []
    if partner.can_take_orders and not active:
        new_orders = (
            Order.objects.filter(delivery_partner__isnull=True, status__in=OPEN_STATUSES)
            .exclude(pk__in=skipped)
            .select_related("shop")
            .annotate(item_qty=Sum("items__quantity"))
            .order_by("created_at")[:10]
        )

    week = earnings_since(partner, start_of_week())
    return render(request, "rider/home.html", {
        "partner": partner,
        "active": active,
        "active_stage": trip_stage(active) if active else None,
        "new_orders": new_orders,
        "today": earnings_since(partner, start_of_today()),
        "week": week,
        "target": WEEKLY_TARGET,
        "bonus": WEEKLY_BONUS,
        "target_left": max(WEEKLY_TARGET - week["count"], 0),
        "online_minutes": int((timezone.now() - partner.online_since).total_seconds() // 60) if partner.is_online and partner.online_since else 0,
        "tab": "home",
    })


@rider_required
@require_POST
def toggle_online(request, partner):
    if partner.is_online and active_order_for(partner):
        messages.error(request, "Finish your current delivery before going offline.")
        return redirect("rider:home")

    if not partner.is_online and not partner.is_verified:
        messages.error(request, "Your account is waiting for verification. You can go online once it's approved.")
        return redirect("rider:home")

    partner.is_online = not partner.is_online
    partner.online_since = timezone.now() if partner.is_online else None
    partner.save(update_fields=["is_online", "online_since"])
    messages.success(request, "You're online. New orders will show up here." if partner.is_online else "You're offline. Take a break!")
    return redirect("rider:home")


# ---------------------------------------------------------------------------
# Accepting orders
# ---------------------------------------------------------------------------

@rider_required
@require_POST
def accept_order(request, partner, order_number):
    if not partner.can_take_orders:
        messages.error(request, "Go online to accept orders.")
        return redirect("rider:home")
    if active_order_for(partner):
        messages.error(request, "Finish your current delivery first.")
        return redirect("rider:home")

    with transaction.atomic():
        # Lock the row so two riders can't grab the same order at the same moment
        order = (
            Order.objects.select_for_update()
            .filter(order_number=order_number, delivery_partner__isnull=True, status__in=OPEN_STATUSES)
            .first()
        )
        if not order:
            messages.error(request, "Sorry, this order was just taken by another partner.")
            return redirect("rider:home")
        order.delivery_partner = partner
        order.assigned_at = timezone.now()
        order.save(update_fields=["delivery_partner", "assigned_at"])

    messages.success(request, f"Order accepted. Head to {order.shop.name}.")
    return redirect("rider:order", order_number=order.order_number)


@rider_required
@require_POST
def skip_order(request, partner, order_number):
    skipped = request.session.get("skipped_orders", [])
    order = Order.objects.filter(order_number=order_number).first()
    if order:
        skipped.append(order.pk)
        request.session["skipped_orders"] = skipped[-50:]
    return redirect("rider:home")


# ---------------------------------------------------------------------------
# The trip
# ---------------------------------------------------------------------------

@rider_required
def order_detail(request, partner, order_number):
    order = get_object_or_404(
        partner.orders.select_related("shop", "customer__user"), order_number=order_number
    )
    stage = trip_stage(order)
    is_finished = order.status in FINISHED_STATUSES

    return render(request, "rider/order.html", {
        "partner": partner,
        "order": order,
        "items": order.items.all(),
        "stage": stage,
        "stage_key": TRIP_STEPS[stage][0] if stage < len(TRIP_STEPS) else "done",
        "steps": [
            {"key": key, "label": label, "time": getattr(order, field), "done": i < stage, "current": i == stage and not is_finished}
            for i, (key, label, field) in enumerate(TRIP_STEPS)
        ],
        "is_finished": is_finished,
        "deliver_form": DeliverForm(order=order),
        "issue_form": ReportIssueForm(),
        "is_cod": order.payment_method == Order.PaymentMethod.COD,
        "celebrate": request.session.pop("just_delivered", None) == order.order_number,
        "open_sheet": request.GET.get("sheet", ""),
        "tab": "home",
    })


@rider_required
@require_POST
def advance_trip(request, partner, order_number):
    """Complete the next step: reached shop -> picked up -> reached customer."""
    order = get_object_or_404(partner.orders.exclude(status__in=FINISHED_STATUSES), order_number=order_number)
    stage_key = TRIP_STEPS[trip_stage(order)][0]
    now = timezone.now()

    if stage_key == "reached_shop":
        order.reached_shop_at = now
        messages.success(request, "Marked as reached. Check the items and collect the sealed bag.")
    elif stage_key == "picked_up":
        order.picked_up_at = now
        order.status = Order.Status.PICKED_UP
        messages.success(request, "Order picked up. Drive safe!")
    elif stage_key == "reached_customer":
        order.reached_customer_at = now
        messages.success(request, "You've arrived. Verify ID and OTP to complete the delivery.")
    else:
        return redirect("rider:order", order_number=order.order_number)

    order.save()
    return redirect("rider:order", order_number=order.order_number)


@rider_required
@require_POST
def deliver(request, partner, order_number):
    order = get_object_or_404(
        partner.orders.exclude(status__in=FINISHED_STATUSES).select_related("shop", "customer__user"),
        order_number=order_number,
    )
    if not order.reached_customer_at:
        return redirect("rider:order", order_number=order.order_number)

    form = DeliverForm(request.POST, order=order)
    if form.is_valid():
        order.status = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.id_checked_at_delivery = True
        if order.payment_method == Order.PaymentMethod.COD:
            order.payment_status = Order.PaymentStatus.PAID
        order.save()
        request.session["just_delivered"] = order.order_number
        return redirect("rider:order", order_number=order.order_number)

    for errors in form.errors.values():
        messages.error(request, errors[0])
    return redirect(reverse("rider:order", args=[order.order_number]) + "?sheet=deliver")


@rider_required
@require_POST
def release_order(request, partner, order_number):
    """Before pickup the rider can hand the order back so another partner can take it."""
    order = get_object_or_404(partner.orders.filter(picked_up_at__isnull=True).exclude(status__in=FINISHED_STATUSES), order_number=order_number)
    order.delivery_partner = None
    order.assigned_at = None
    order.reached_shop_at = None
    order.save()
    skipped = request.session.get("skipped_orders", [])
    request.session["skipped_orders"] = (skipped + [order.pk])[-50:]
    messages.success(request, "Order released. It's been offered to other partners.")
    return redirect("rider:home")


@rider_required
@require_POST
def report_issue(request, partner, order_number):
    """After pickup: the delivery can't be completed, so the order is cancelled and returned to the shop."""
    order = get_object_or_404(partner.orders.filter(picked_up_at__isnull=False).exclude(status__in=FINISHED_STATUSES), order_number=order_number)
    form = ReportIssueForm(request.POST)
    if form.is_valid():
        order.cancel(form.cleaned_data["reason"])
        messages.success(request, "Issue reported. Please return the sealed order to the shop.")
    else:
        messages.error(request, "Please choose what went wrong.")
    return redirect("rider:order", order_number=order.order_number)


# ---------------------------------------------------------------------------
# History, earnings, profile
# ---------------------------------------------------------------------------

@rider_required
def history(request, partner):
    orders = partner.orders.filter(status__in=FINISHED_STATUSES).select_related("shop", "customer__user")

    period = request.GET.get("period", "all")
    starts = {"today": start_of_today(), "week": start_of_week(), "month": start_of_today().replace(day=1)}
    if period in starts:
        orders = orders.filter(created_at__gte=starts[period])

    summary = orders.aggregate(
        delivered=Count("id", filter=Q(status=Order.Status.DELIVERED)),
        cancelled=Count("id", filter=Q(status=Order.Status.CANCELLED)),
        earned=Sum("rider_earning", filter=Q(status=Order.Status.DELIVERED)),
        km=Sum("distance_km", filter=Q(status=Order.Status.DELIVERED)),
    )

    # Status filter comes after the summary so the chips always show both counts
    status = request.GET.get("status", "")
    if status in FINISHED_STATUSES:
        orders = orders.filter(status=status)

    page = Paginator(orders.order_by("-created_at"), 10).get_page(request.GET.get("page"))
    return render(request, "rider/history.html", {
        "partner": partner,
        "page": page,
        "period": period,
        "status": status,
        "summary": summary,
        "periods": [("today", "Today"), ("week", "This week"), ("month", "This month"), ("all", "All time")],
        "tab": "history",
    })


@rider_required
def earnings(request, partner):
    today = start_of_today()
    week = earnings_since(partner, start_of_week())

    # Earnings per day for the last 7 days
    first_day = today - timedelta(days=6)
    per_day = dict(
        partner.orders.filter(status=Order.Status.DELIVERED, delivered_at__gte=first_day)
        .order_by()
        .annotate(day=TruncDate("delivered_at"))
        .values("day")
        .annotate(total=Sum("rider_earning"))
        .values_list("day", "total")
    )
    days = [(first_day + timedelta(days=i)).date() for i in range(7)]
    chart = [{"day": d, "amount": per_day.get(d, Decimal("0"))} for d in days]
    chart_max = max([row["amount"] for row in chart] + [Decimal("1")])

    # Weekly payouts (paid every Monday for the previous week)
    payouts = []
    for weeks_back in range(1, 5):
        start = start_of_week() - timedelta(weeks=weeks_back)
        result = partner.orders.filter(
            status=Order.Status.DELIVERED, delivered_at__gte=start, delivered_at__lt=start + timedelta(weeks=1)
        ).aggregate(total=Sum("rider_earning"), count=Count("id"))
        bonus = WEEKLY_BONUS if result["count"] >= WEEKLY_TARGET else Decimal("0")
        payouts.append({
            "start": start, "end": start + timedelta(days=6),
            "count": result["count"], "total": (result["total"] or Decimal("0")) + bonus, "bonus": bonus,
        })

    cash_in_hand = partner.orders.filter(
        status=Order.Status.DELIVERED, payment_method=Order.PaymentMethod.COD, delivered_at__gte=today
    ).aggregate(total=Sum("grand_total"))["total"] or Decimal("0")

    return render(request, "rider/earnings.html", {
        "partner": partner,
        "today": earnings_since(partner, today),
        "week": week,
        "month": earnings_since(partner, today.replace(day=1)),
        "lifetime": earnings_since(partner, today - timedelta(days=3650)),
        "chart": chart,
        "chart_max": chart_max,
        "target": WEEKLY_TARGET,
        "bonus": WEEKLY_BONUS,
        "target_left": max(WEEKLY_TARGET - week["count"], 0),
        "payouts": payouts,
        "cash_in_hand": cash_in_hand,
        "tab": "earnings",
    })


@rider_required
def profile(request, partner):
    stats = partner.orders.aggregate(
        delivered=Count("id", filter=Q(status=Order.Status.DELIVERED)),
        cancelled=Count("id", filter=Q(status=Order.Status.CANCELLED)),
        km=Sum("distance_km", filter=Q(status=Order.Status.DELIVERED)),
    )
    total = stats["delivered"] + stats["cancelled"]
    return render(request, "rider/profile.html", {
        "partner": partner,
        "stats": stats,
        "completion_rate": round(stats["delivered"] / total * 100) if total else 100,
        "tab": "profile",
    })
