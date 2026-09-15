from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from .cart import Cart
from .forms import AddressForm, SignupForm
from .models import Category, Order, OrderItem, ShopProduct
from .shops import SHOP_SESSION_KEY, get_current_shop, licensed_shops


# ---------------------------------------------------------------------------
# Storefront
# ---------------------------------------------------------------------------

def home(request):
    shop = get_current_shop(request)
    categories = Category.objects.all()
    selected_slug = request.GET.get("category", "")
    query = request.GET.get("q", "").strip()

    listings = ShopProduct.objects.none()
    if shop:
        listings = (
            shop.inventory.filter(is_available=True, product__is_active=True)
            .select_related("product__category")
            .order_by("-stock")
        )

    selected_category = None
    if selected_slug:
        selected_category = categories.filter(slug=selected_slug).first()
        listings = listings.filter(product__category=selected_category)
    if query:
        listings = listings.filter(
            Q(product__name__icontains=query) | Q(product__brand__icontains=query) | Q(product__category__name__icontains=query)
        )

    # Home page (no filter): one horizontal row per category, like Blinkit.
    sections = []
    if not selected_category and not query:
        for category in categories:
            items = [sp for sp in listings if sp.product.category_id == category.id]
            if items:
                sections.append({"category": category, "items": items})

    cart = Cart(request)
    return render(request, "delivery/home.html", {
        "categories": categories,
        "selected_category": selected_category,
        "query": query,
        "listings": listings,
        "sections": sections,
        "cart_quantities": {int(k): v for k, v in cart.data.items()},
    })


@require_POST
def choose_shop(request):
    shop = get_object_or_404(licensed_shops(), id=request.POST.get("shop_id"))
    if request.session.get(SHOP_SESSION_KEY) != shop.id:
        request.session[SHOP_SESSION_KEY] = shop.id
        Cart(request).clear()  # a cart can only contain items from one shop
    return redirect("delivery:home")


@require_POST
def confirm_age(request):
    request.session["age_gate_passed"] = True
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

@require_POST
def cart_update(request):
    """Called by JavaScript when + / − / ADD is clicked. Returns fresh cart HTML."""
    shop = get_current_shop(request)
    shop_product = get_object_or_404(ShopProduct, id=request.POST.get("id"), shop=shop, is_available=True)
    delta = 1 if request.POST.get("delta") == "1" else -1

    cart = Cart(request)
    cart.change(shop_product, delta)
    summary = cart.summary()

    return JsonResponse({
        "id": shop_product.id,
        "quantity": cart.get_quantity(shop_product.id),
        "count": summary["count"],
        "grand_total": str(summary["grand_total"]),
        "drawer_html": render_to_string("delivery/partials/cart_drawer_body.html", {"cart": summary}, request),
    })


# ---------------------------------------------------------------------------
# Checkout & orders
# ---------------------------------------------------------------------------

@login_required
def checkout(request):
    customer = getattr(request.user, "customer", None)
    if customer is None:
        messages.error(request, "Only customer accounts can place orders.")
        return redirect("delivery:home")

    cart = Cart(request)
    summary = cart.summary()
    if not summary["items"]:
        messages.info(request, "Your cart is empty.")
        return redirect("delivery:home")

    shop = get_current_shop(request)
    addresses = customer.addresses.order_by("-is_default", "-created_at")
    address_form = AddressForm()

    if request.method == "POST" and request.POST.get("action") == "add_address":
        address_form = AddressForm(request.POST)
        if address_form.is_valid():
            address = address_form.save(commit=False)
            address.customer = customer
            address.is_default = not addresses.exists()
            address.save()
            messages.success(request, "Address saved.")
            return redirect("delivery:checkout")

    elif request.method == "POST" and request.POST.get("action") == "place_order":
        error = _place_order_error(request, customer, shop, summary)
        if error:
            messages.error(request, error)
        else:
            address = addresses.get(id=request.POST["address_id"])
            order = _create_order(request, customer, shop, address, summary)
            cart.clear()
            return redirect("delivery:order_detail", order_number=order.order_number)

    return render(request, "delivery/checkout.html", {
        "shop": shop,
        "addresses": addresses,
        "address_form": address_form,
        "payment_methods": Order.PaymentMethod.choices,
    })


def _place_order_error(request, customer, shop, summary):
    """Returns a message if the order is not allowed, otherwise None."""
    if not customer.is_of_legal_age:
        return f"You must be {settings.LEGAL_DRINKING_AGE}+ to order."
    if request.POST.get("age_confirmed") != "on":
        return "Please confirm you are of legal drinking age."
    if not shop or not shop.can_accept_orders:
        return "This store is closed right now. Please try again during opening hours."
    if not customer.addresses.filter(id=request.POST.get("address_id") or 0).exists():
        return "Please select a delivery address."
    for row in summary["items"]:
        if row["quantity"] > row["shop_product"].stock:
            return f"Only {row['shop_product'].stock} left of {row['shop_product'].product.name}."
    return None


@transaction.atomic
def _create_order(request, customer, shop, address, summary):
    order = Order.objects.create(
        customer=customer,
        shop=shop,
        delivery_address=address.full_address,
        item_total=summary["item_total"],
        delivery_fee=summary["delivery_fee"],
        platform_fee=summary["platform_fee"],
        grand_total=summary["grand_total"],
        payment_method=request.POST.get("payment_method", Order.PaymentMethod.UPI),
        age_confirmed_by_customer=True,
    )
    for row in summary["items"]:
        sp = row["shop_product"]
        OrderItem.objects.create(
            order=order,
            shop_product=sp,
            product_name=sp.product.name,
            volume_ml=sp.product.volume_ml,
            price=sp.price,
            quantity=row["quantity"],
        )
        sp.stock -= row["quantity"]
        sp.save(update_fields=["stock"])
    return order


@login_required
def order_list(request):
    customer = getattr(request.user, "customer", None)
    orders = customer.orders.prefetch_related("items").select_related("shop") if customer else []
    return render(request, "delivery/order_list.html", {"orders": orders})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.select_related("shop", "delivery_partner__user"),
        order_number=order_number,
        customer__user=request.user,
    )
    steps = [Order.Status.PLACED, Order.Status.CONFIRMED, Order.Status.PACKED, Order.Status.PICKED_UP, Order.Status.DELIVERED]
    current = steps.index(order.status) if order.status in steps else -1
    timeline = [{"label": step.label, "done": i <= current, "active": i == current} for i, step in enumerate(steps)]
    return render(request, "delivery/order_detail.html", {"order": order, "timeline": timeline})


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def signup(request):
    if request.user.is_authenticated:
        return redirect("delivery:home")

    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        request.session["age_gate_passed"] = True
        messages.success(request, f"Welcome to Booze, {user.first_name}!")
        return redirect(request.GET.get("next") or "delivery:home")

    return render(request, "delivery/signup.html", {"form": form})
