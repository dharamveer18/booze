"""
Views for the Booze admin panel.

Who can open what:
    @panel_required  -> admins AND retailers (retailers only see their own shops' data)
    @admin_required  -> admins only

Pages shared by both roles never use `Order.objects` / `RetailShop.objects` directly —
they start from visible_orders(user) / visible_shops(user) (see scope.py).

List pages all follow the same simple pattern:
    1. start with a queryset
    2. apply the filters that are present in request.GET
    3. sort it
    4. paginate it
"""

import math
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from delivery.models import Customer, DeliveryPartner, Order, RetailShop, ShopProduct, User

from .decorators import admin_required, panel_required
from .forms import AddUserForm, AdminLoginForm, AssignShopsForm, OrderUpdateForm, UserRoleForm
from .scope import visible_orders, visible_shops

PER_PAGE_OPTIONS = [10, 20, 50, 100]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def paginate(request, queryset):
    """Returns (page, page_numbers). Page size comes from ?per_page=, default 20."""
    per_page = request.GET.get("per_page", "20")
    per_page = int(per_page) if per_page.isdigit() and int(per_page) in PER_PAGE_OPTIONS else 20

    paginator = Paginator(queryset, per_page)
    page = paginator.get_page(request.GET.get("page"))
    page_numbers = paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    return page, page_numbers


def list_context(request, page, page_numbers, **extra):
    """Things every list template needs."""
    filter_keys = [key for key in request.GET if key not in ("page", "per_page", "sort") and request.GET[key]]
    return {
        "page": page,
        "page_numbers": page_numbers,
        "per_page_options": PER_PAGE_OPTIONS,
        "active_filter_count": len(filter_keys),
        "params": request.GET,
        **extra,
    }


def since(period):
    """'today' / '7d' / '30d' / '90d'  ->  the datetime that period starts at (or None)."""
    days = {"today": 0, "7d": 7, "30d": 30, "90d": 90}.get(period)
    if days is None:
        return None
    start_of_today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_today - timedelta(days=days)


def redirect_back(request, fallback):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(fallback)


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated and request.user.can_use_panel:
        return redirect("panel:dashboard")

    form = AdminLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect_back(request, "panel:dashboard")

    return render(request, "panel/login.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("panel:login")


# ---------------------------------------------------------------------------
# Dashboard (one URL — admins and retailers get different pages)
# ---------------------------------------------------------------------------

def sales_summary(orders):
    """Sales & order count for today and yesterday (cancelled orders don't count)."""
    today = since("today")
    valid = orders.exclude(status=Order.Status.CANCELLED)

    def between(start, end):
        result = valid.filter(created_at__gte=start, created_at__lt=end).aggregate(revenue=Sum("grand_total"), count=Count("id"))
        return result["revenue"] or 0, result["count"]

    revenue_today, orders_today = between(today, today + timedelta(days=1))
    revenue_yesterday, orders_yesterday = between(today - timedelta(days=1), today)
    return {
        "revenue_today": revenue_today,
        "revenue_yesterday": revenue_yesterday,
        "revenue_change": percent_change(revenue_today, revenue_yesterday),
        "orders_today": orders_today,
        "orders_yesterday": orders_yesterday,
        "orders_change": percent_change(orders_today, orders_yesterday),
    }


def percent_change(now, before):
    if not before:
        return None
    return round((now - before) / before * 100)


def orders_chart(orders, days=14):
    """Orders per day for the last `days` days, for the column chart."""
    first_day = since("today") - timedelta(days=days - 1)
    per_day = dict(
        orders.filter(created_at__gte=first_day)
        .order_by()  # clear the default ordering so GROUP BY works
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .values_list("day", "total")
    )
    rows = [{"day": d, "count": per_day.get(d, 0)} for d in ((first_day + timedelta(days=i)).date() for i in range(days))]
    top = math.ceil(max([row["count"] for row in rows] + [1]) / 4) * 4  # a round number for the y-axis
    return {
        "rows": rows,
        "max": top,
        "ticks": [top, top * 3 // 4, top // 2, top // 4, 0],
        "total": sum(row["count"] for row in rows),
    }


def status_breakdown(orders):
    counts = dict(orders.order_by().values("status").annotate(total=Count("id")).values_list("status", "total"))
    statuses = [{"value": value, "label": label, "count": counts.get(value, 0)} for value, label in Order.Status.choices]
    return statuses, max([s["count"] for s in statuses] + [1])


@panel_required
def dashboard(request):
    if request.user.is_admin:
        return admin_dashboard(request)
    return retailer_dashboard(request)


def admin_dashboard(request):
    orders = Order.objects.all()
    statuses, status_max = status_breakdown(orders)
    soon = date.today() + timedelta(days=30)

    attention = [
        {
            "label": "Shops waiting for licence verification",
            "count": RetailShop.objects.filter(is_licence_verified=False).count(),
            "url": "?licence=pending", "page": "panel:shops",
        },
        {
            "label": "Licences expiring in 30 days",
            "count": RetailShop.objects.filter(licence_valid_till__gte=date.today(), licence_valid_till__lte=soon).count(),
            "url": "?licence=expiring", "page": "panel:shops",
        },
        {
            "label": "Delivery partners pending verification",
            "count": DeliveryPartner.objects.filter(is_verified=False).count(),
            "url": "?verification=pending", "page": "panel:partners",
        },
        {
            "label": "Customers without age verification",
            "count": Customer.objects.filter(is_age_verified=False).count(),
            "url": "?age=pending&role=customer", "page": "panel:users",
        },
    ]

    return render(request, "panel/dashboard.html", {
        "stats": {
            **sales_summary(orders),
            "customers": Customer.objects.count(),
            "new_customers_week": User.objects.filter(role=User.Role.CUSTOMER, date_joined__gte=since("7d")).count(),
            "shops_live": RetailShop.objects.filter(is_active=True, is_licence_verified=True, licence_valid_till__gte=date.today()).count(),
            "shops_total": RetailShop.objects.count(),
            "partners_online": DeliveryPartner.objects.filter(is_online=True, is_verified=True).count(),
            "partners_total": DeliveryPartner.objects.count(),
        },
        "chart": orders_chart(orders),
        "statuses": statuses,
        "status_max": status_max,
        "attention": attention,
        "recent_orders": orders.select_related("customer__user", "shop")[:7],
    })


def retailer_dashboard(request):
    shops = visible_shops(request.user)
    orders = visible_orders(request.user)
    inventory = ShopProduct.objects.filter(shop__in=shops)
    statuses, status_max = status_breakdown(orders)
    all_time = orders.exclude(status=Order.Status.CANCELLED).aggregate(revenue=Sum("grand_total"), count=Count("id"))

    return render(request, "panel/retailer_dashboard.html", {
        "shops": shops,
        "stats": {
            **sales_summary(orders),
            "orders_total": all_time["count"],
            "revenue_total": all_time["revenue"] or 0,
            "to_prepare": orders.filter(status__in=[Order.Status.PLACED, Order.Status.CONFIRMED]).count(),
            "products": inventory.count(),
            "out_of_stock": inventory.filter(stock=0).count(),
        },
        "chart": orders_chart(orders),
        "statuses": statuses,
        "status_max": status_max,
        "low_stock": inventory.select_related("product", "shop").filter(stock__lt=10).order_by("stock")[:6],
        "recent_orders": orders.select_related("customer__user", "shop")[:7],
        "expiring_before": date.today() + timedelta(days=30),
    })


# ---------------------------------------------------------------------------
# Users (admins only)
# ---------------------------------------------------------------------------

@admin_required
def user_list(request):
    users = User.objects.select_related("customer").annotate(order_count=Count("customer__orders"))
    params = request.GET

    if q := params.get("q", "").strip():
        users = users.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
            | Q(email__icontains=q) | Q(phone__icontains=q)
        )
    if role := params.get("role"):
        users = users.filter(role=role)
    if params.get("status") == "active":
        users = users.filter(is_active=True)
    elif params.get("status") == "inactive":
        users = users.filter(is_active=False)
    if params.get("age") == "verified":
        users = users.filter(customer__is_age_verified=True)
    elif params.get("age") == "pending":
        users = users.filter(customer__is_age_verified=False)
    if start := since(params.get("joined")):
        users = users.filter(date_joined__gte=start)

    sort_options = {
        "newest": ("Newest first", "-date_joined"),
        "oldest": ("Oldest first", "date_joined"),
        "name": ("Name A–Z", "first_name"),
        "orders": ("Most orders", "-order_count"),
    }
    sort = params.get("sort") if params.get("sort") in sort_options else "newest"
    users = users.order_by(sort_options[sort][1], "-id")

    page, page_numbers = paginate(request, users)
    return render(request, "panel/user_list.html", list_context(
        request, page, page_numbers,
        roles=User.Role.choices,
        sort_options={key: label for key, (label, _) in sort_options.items()},
        sort=sort,
        role_counts=dict(User.objects.order_by().values("role").annotate(n=Count("id")).values_list("role", "n")),
        total_users=User.objects.count(),
    ))


@admin_required
def user_add(request):
    initial_role = request.GET.get("role") if request.GET.get("role") in User.Role.values else User.Role.CUSTOMER
    form = AddUserForm(request.POST or None, initial={"role": initial_role})

    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"{user.get_role_display()} account created for {user.display_name}.")
        return redirect("panel:user_detail", pk=user.pk)

    return render(request, "panel/user_add.html", {
        "form": form,
        "selected_role": form["role"].value() or initial_role,
        "role_cards": [
            {"value": User.Role.CUSTOMER, "label": "Customer", "icon": "users", "text": "Orders drinks on the storefront"},
            {"value": User.Role.SHOP_OWNER, "label": "Retailer", "icon": "store", "text": "Owns shops · sees only their shops here"},
            {"value": User.Role.DELIVERY_PARTNER, "label": "Delivery partner", "icon": "bike", "text": "Picks up and delivers orders"},
            {"value": User.Role.ADMIN, "label": "Admin", "icon": "shield", "text": "Full access to this panel"},
        ],
    })


@admin_required
def user_detail(request, pk):
    user = get_object_or_404(User.objects.select_related("customer", "delivery_partner", "shop_owner"), pk=pk)
    owner = getattr(user, "shop_owner", None)
    action = request.POST.get("action")

    role_form = UserRoleForm(request.POST if action == "role" else None, instance=user)
    shops_form = AssignShopsForm(
        request.POST if action == "shops" else None,
        initial={"shops": owner.shops.all() if owner else []},
    )

    if action == "role" and role_form.is_valid():
        if user == request.user and role_form.cleaned_data["role"] != User.Role.ADMIN:
            messages.error(request, "You can't remove your own admin role.")
        else:
            role_form.save()
            messages.success(request, f"{user.display_name} is now a {user.get_role_display().lower()}.")
        return redirect("panel:user_detail", pk=user.pk)

    if action == "shops" and owner and shops_form.is_valid():
        shops_form.save(owner)
        messages.success(request, f"Shops updated for {owner.business_name}.")
        return redirect("panel:user_detail", pk=user.pk)

    customer = getattr(user, "customer", None)
    return render(request, "panel/user_detail.html", {
        "profile_user": user,
        "customer": customer,
        "partner": getattr(user, "delivery_partner", None),
        "owner": owner,
        "orders": customer.orders.select_related("shop")[:10] if customer else [],
        "order_stats": customer.orders.exclude(status="cancelled").aggregate(total=Sum("grand_total"), count=Count("id")) if customer else None,
        "role_form": role_form,
        "shops_form": shops_form,
    })


# ---------------------------------------------------------------------------
# Retail shops (admins: all shops · retailers: their own shops)
# ---------------------------------------------------------------------------

@panel_required
def shop_list(request):
    shops = visible_shops(request.user).select_related("owner").annotate(
        order_count=Count("orders", distinct=True),
        product_count=Count("inventory", distinct=True),
    )
    params = request.GET
    today = date.today()

    if q := params.get("q", "").strip():
        shops = shops.filter(
            Q(name__icontains=q) | Q(licence_number__icontains=q) | Q(pincode__icontains=q) | Q(owner__business_name__icontains=q)
        )
    if city := params.get("city"):
        shops = shops.filter(city=city)

    licence = params.get("licence")
    if licence == "valid":
        shops = shops.filter(is_licence_verified=True, licence_valid_till__gte=today)
    elif licence == "pending":
        shops = shops.filter(is_licence_verified=False)
    elif licence == "expired":
        shops = shops.filter(licence_valid_till__lt=today)
    elif licence == "expiring":
        shops = shops.filter(licence_valid_till__gte=today, licence_valid_till__lte=today + timedelta(days=30))

    if params.get("status") == "active":
        shops = shops.filter(is_active=True)
    elif params.get("status") == "inactive":
        shops = shops.filter(is_active=False)

    sort_options = {
        "newest": ("Newest first", "-created_at"),
        "name": ("Name A–Z", "name"),
        "orders": ("Most orders", "-order_count"),
        "expiry": ("Licence expiry (soonest)", "licence_valid_till"),
    }
    sort = params.get("sort") if params.get("sort") in sort_options else "newest"
    shops = shops.order_by(sort_options[sort][1], "-id")

    page, page_numbers = paginate(request, shops)
    return render(request, "panel/shop_list.html", list_context(
        request, page, page_numbers,
        cities=visible_shops(request.user).order_by("city").values_list("city", flat=True).distinct(),
        sort_options={key: label for key, (label, _) in sort_options.items()},
        sort=sort,
        expiring_before=today + timedelta(days=30),
    ))


@panel_required
def shop_detail(request, pk):
    shop = get_object_or_404(visible_shops(request.user).select_related("owner__user"), pk=pk)
    inventory = shop.inventory.select_related("product__category").order_by("stock")
    sales = shop.orders.exclude(status="cancelled").aggregate(revenue=Sum("grand_total"), count=Count("id"))
    return render(request, "panel/shop_detail.html", {
        "shop": shop,
        "sales": sales,
        "inventory_count": inventory.count(),
        "out_of_stock": inventory.filter(stock=0).count(),
        "low_stock": inventory[:6],
        "orders": shop.orders.select_related("customer__user")[:8],
        "expiring_before": date.today() + timedelta(days=30),
    })


# ---------------------------------------------------------------------------
# Delivery partners (admins only)
# ---------------------------------------------------------------------------

@admin_required
def partner_list(request):
    partners = DeliveryPartner.objects.select_related("user").annotate(
        delivered_count=Count("orders", filter=Q(orders__status=Order.Status.DELIVERED)),
        active_count=Count("orders", filter=Q(orders__status__in=["packed", "picked_up"])),
    )
    params = request.GET

    if q := params.get("q", "").strip():
        partners = partners.filter(
            Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
            | Q(user__phone__icontains=q) | Q(vehicle_number__icontains=q)
        )
    if params.get("verification") == "verified":
        partners = partners.filter(is_verified=True)
    elif params.get("verification") == "pending":
        partners = partners.filter(is_verified=False)
    if params.get("availability") == "online":
        partners = partners.filter(is_online=True)
    elif params.get("availability") == "offline":
        partners = partners.filter(is_online=False)
    if vehicle := params.get("vehicle"):
        partners = partners.filter(vehicle_type=vehicle)
    if params.get("status") == "active":
        partners = partners.filter(user__is_active=True)
    elif params.get("status") == "inactive":
        partners = partners.filter(user__is_active=False)

    sort_options = {
        "newest": ("Newest first", "-created_at"),
        "rating": ("Highest rating", "-rating"),
        "deliveries": ("Most deliveries", "-delivered_count"),
        "name": ("Name A–Z", "user__first_name"),
    }
    sort = params.get("sort") if params.get("sort") in sort_options else "newest"
    partners = partners.order_by(sort_options[sort][1], "-id")

    page, page_numbers = paginate(request, partners)
    return render(request, "panel/partner_list.html", list_context(
        request, page, page_numbers,
        vehicles=DeliveryPartner.Vehicle.choices,
        sort_options={key: label for key, (label, _) in sort_options.items()},
        sort=sort,
    ))


@admin_required
def partner_detail(request, pk):
    partner = get_object_or_404(DeliveryPartner.objects.select_related("user"), pk=pk)
    return render(request, "panel/partner_detail.html", {
        "partner": partner,
        "delivered": partner.orders.filter(status=Order.Status.DELIVERED).count(),
        "in_progress": partner.orders.filter(status__in=["packed", "picked_up"]).count(),
        "orders": partner.orders.select_related("customer__user", "shop")[:10],
    })


# ---------------------------------------------------------------------------
# Orders (admins: all orders · retailers: orders from their shops, read-only)
# ---------------------------------------------------------------------------

@panel_required
def order_list(request):
    orders = visible_orders(request.user)
    params = request.GET

    if q := params.get("q", "").strip():
        search = Q(order_number__icontains=q) | Q(customer__user__first_name__icontains=q) | Q(customer__user__last_name__icontains=q)
        if request.user.is_admin:
            search |= Q(customer__user__phone__icontains=q)  # retailers don't get customers' phone numbers
        orders = orders.filter(search)
    # Status filter is applied after the tab counts are calculated (see below)
    if payment := params.get("payment"):
        orders = orders.filter(payment_status=payment)
    if method := params.get("method"):
        orders = orders.filter(payment_method=method)
    if shop := params.get("shop"):
        orders = orders.filter(shop_id=shop)
    if start := since(params.get("period")):
        orders = orders.filter(created_at__gte=start)
    if date_from := params.get("from"):
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to := params.get("to"):
        orders = orders.filter(created_at__date__lte=date_to)

    # Counts for the status tabs respect every other filter
    tab_counts = dict(orders.order_by().values("status").annotate(n=Count("id")).values_list("status", "n"))
    status_tabs = [{"value": "", "label": "All", "count": sum(tab_counts.values())}] + [
        {"value": value, "label": label, "count": tab_counts.get(value, 0)} for value, label in Order.Status.choices
    ]

    if status := params.get("status"):
        orders = orders.filter(status=status)

    sort_options = {
        "newest": ("Newest first", "-created_at"),
        "oldest": ("Oldest first", "created_at"),
        "amount_high": ("Amount: high to low", "-grand_total"),
        "amount_low": ("Amount: low to high", "grand_total"),
    }
    sort = params.get("sort") if params.get("sort") in sort_options else "newest"
    orders = orders.order_by(sort_options[sort][1], "-id")

    summary = orders.aggregate(revenue=Sum("grand_total"))

    # Join related rows and count items only for the rows we display
    # (annotating earlier would multiply the counts above by the number of items)
    orders = orders.select_related("customer__user", "shop", "delivery_partner__user").annotate(item_qty=Sum("items__quantity"))
    page, page_numbers = paginate(request, orders)
    return render(request, "panel/order_list.html", list_context(
        request, page, page_numbers,
        status_tabs=status_tabs,
        payment_statuses=Order.PaymentStatus.choices,
        payment_methods=Order.PaymentMethod.choices,
        shops=visible_shops(request.user).order_by("name"),
        sort_options={key: label for key, (label, _) in sort_options.items()},
        sort=sort,
        filtered_revenue=summary["revenue"] or 0,
    ))


@panel_required
def order_detail(request, order_number):
    order = get_object_or_404(
        visible_orders(request.user).select_related("customer__user", "shop", "delivery_partner__user"),
        order_number=order_number,
    )

    # Only admins can change an order
    form = None
    if request.user.is_admin:
        form = OrderUpdateForm(request.POST or None, instance=order)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, f"Order #{order.order_number} updated.")
            return redirect("panel:order_detail", order_number=order.order_number)

    steps = [Order.Status.PLACED, Order.Status.CONFIRMED, Order.Status.PACKED, Order.Status.PICKED_UP, Order.Status.DELIVERED]
    current = steps.index(order.status) if order.status in steps else -1
    return render(request, "panel/order_detail.html", {
        "order": order,
        "items": order.items.all(),
        "form": form,
        "timeline": [{"label": s.label, "done": i <= current} for i, s in enumerate(steps)],
    })


# ---------------------------------------------------------------------------
# Quick actions (on/off switches, admins only)
# ---------------------------------------------------------------------------

# key in the URL  ->  (model, field to flip, what to call it in the message)
TOGGLES = {
    "user-active": (User, "is_active", "Account"),
    "customer-age": (Customer, "is_age_verified", "Age verification"),
    "shop-licence": (RetailShop, "is_licence_verified", "Licence verification"),
    "shop-active": (RetailShop, "is_active", "Shop listing"),
    "partner-verified": (DeliveryPartner, "is_verified", "Partner verification"),
}


@admin_required
@require_POST
def toggle(request, key, pk):
    if key not in TOGGLES:
        return redirect("panel:dashboard")

    model, field, label = TOGGLES[key]
    obj = get_object_or_404(model, pk=pk)

    if key == "user-active" and obj == request.user:
        messages.error(request, "You can't deactivate your own account.")
        return redirect_back(request, "panel:dashboard")

    new_value = not getattr(obj, field)
    setattr(obj, field, new_value)
    obj.save(update_fields=[field])

    # A rider who is no longer verified shouldn't stay online
    if key == "partner-verified" and not new_value and obj.is_online:
        obj.is_online = False
        obj.save(update_fields=["is_online"])

    messages.success(request, f"{label} {'turned on' if new_value else 'turned off'} for {obj}.")
    return redirect_back(request, "panel:dashboard")
