"""
Database schema for Booze — a quick-commerce *marketplace* for alcoholic beverages.

Important business rule:
    Booze never buys, stores or sells alcohol itself. Every order is fulfilled
    by a LICENSED retail shop. We only provide the platform + delivery service.

That is why:
    * Products are listed per shop (ShopProduct) with the shop's own price & stock.
    * A shop can only sell while its liquor licence is verified and not expired.
    * Customers must be of legal drinking age, and ID is checked again at the door.

Every login is a `User` (our own auth user model, set as AUTH_USER_MODEL).
`User.role` says what kind of account it is, and each role has a profile with extra details:
    customer         -> Customer         (orders drinks)
    shop_owner       -> ShopOwner        (owns one or more licensed RetailShops)
    delivery_partner -> DeliveryPartner  (picks up from the shop, delivers to the customer)
    admin            -> no profile       (can log in to the admin panel)
"""

import random
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Adds created_at / updated_at to every model that inherits it."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Auth user
# ---------------------------------------------------------------------------

class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # `python manage.py createsuperuser` should always create an admin
        extra_fields.setdefault("role", User.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """The single login model for everyone on the platform."""

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        SHOP_OWNER = "shop_owner", "Retailer"
        DELIVERY_PARTNER = "delivery_partner", "Delivery partner"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)

    objects = UserManager()

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def is_admin(self):
        """Active admins (or superusers) see everything in the admin panel."""
        return self.is_active and (self.role == self.Role.ADMIN or self.is_superuser)

    @property
    def is_retailer(self):
        """Active retailers with a shop-owner profile see only their own shops in the admin panel."""
        return self.is_active and self.role == self.Role.SHOP_OWNER and hasattr(self, "shop_owner")

    @property
    def can_use_panel(self):
        return self.is_admin or self.is_retailer


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

class Customer(TimeStampedModel):
    """A person who orders drinks."""

    class IdType(models.TextChoices):
        AADHAAR = "aadhaar", "Aadhaar"
        PAN = "pan", "PAN Card"
        PASSPORT = "passport", "Passport"
        DRIVING_LICENCE = "driving_licence", "Driving Licence"
        VOTER_ID = "voter_id", "Voter ID"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer")
    date_of_birth = models.DateField()

    # Age verification (done by our team / KYC provider from an uploaded ID)
    id_type = models.CharField(max_length=20, choices=IdType.choices, blank=True)
    id_last_four = models.CharField(max_length=4, blank=True, help_text="Only store the last 4 digits, never the full ID.")
    is_age_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.display_name} ({self.user.phone})"

    @property
    def age(self):
        today = date.today()
        born = self.date_of_birth
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    @property
    def is_of_legal_age(self):
        return self.age >= settings.LEGAL_DRINKING_AGE


class Address(TimeStampedModel):
    """A saved delivery address of a customer."""

    class Label(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=10, choices=Label.choices, default=Label.HOME)
    house = models.CharField("Flat / House no.", max_length=100)
    street = models.CharField("Street / Area", max_length=200)
    landmark = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=60)
    pincode = models.CharField(max_length=6)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.get_label_display()}: {self.full_address}"

    @property
    def full_address(self):
        parts = [self.house, self.street, self.landmark, f"{self.city} - {self.pincode}"]
        return ", ".join(p for p in parts if p)


class ShopOwner(TimeStampedModel):
    """Owner of one or more licensed retail shops (for future self-onboarding)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop_owner")
    business_name = models.CharField(max_length=150)
    pan_number = models.CharField(max_length=10, blank=True)
    gst_number = models.CharField(max_length=15, blank=True)
    is_kyc_verified = models.BooleanField(default=False)

    # Bank details for payouts (store only what's needed)
    bank_account_name = models.CharField(max_length=100, blank=True)
    bank_account_last_four = models.CharField(max_length=4, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True)

    def __str__(self):
        return self.business_name


class DeliveryPartner(TimeStampedModel):
    """A rider who picks orders up from shops and delivers them."""

    class Vehicle(models.TextChoices):
        BICYCLE = "bicycle", "Bicycle"
        SCOOTER = "scooter", "Scooter"
        MOTORCYCLE = "motorcycle", "Motorcycle"
        EV = "ev", "Electric Scooter"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delivery_partner")
    date_of_birth = models.DateField()
    vehicle_type = models.CharField(max_length=20, choices=Vehicle.choices, default=Vehicle.SCOOTER)
    vehicle_number = models.CharField(max_length=15, blank=True)
    driving_licence_number = models.CharField(max_length=20, blank=True)

    is_verified = models.BooleanField(default=False, help_text="Background check + documents approved.")
    is_online = models.BooleanField(default=False, help_text="Currently accepting orders.")
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, default=Decimal("5.0"))
    online_since = models.DateTimeField(null=True, blank=True, help_text="When the rider last went online.")

    def __str__(self):
        return f"{self.user.display_name} ({self.get_vehicle_type_display()})"

    @property
    def can_take_orders(self):
        return self.is_verified and self.is_online and self.user.is_active


# ---------------------------------------------------------------------------
# Shops
# ---------------------------------------------------------------------------

class RetailShop(TimeStampedModel):
    """A licensed liquor retail shop. All orders are fulfilled from here."""

    # Nullable: we can list a shop ourselves before the owner creates an account.
    owner = models.ForeignKey(ShopOwner, on_delete=models.SET_NULL, null=True, blank=True, related_name="shops")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)

    # Licence — the most important part
    licence_number = models.CharField(max_length=50, unique=True)
    licence_type = models.CharField(max_length=50, help_text="e.g. FL-2, L-1, CL-2 (varies by state).")
    licence_valid_till = models.DateField()
    is_licence_verified = models.BooleanField(default=False)

    # Location
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=60)
    pincode = models.CharField(max_length=6)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_radius_km = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("3.0"))

    # Operations
    opens_at = models.TimeField(default="10:00")
    closes_at = models.TimeField(default="22:00")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}, {self.city}"

    @property
    def is_licence_valid(self):
        return self.is_licence_verified and self.licence_valid_till >= date.today()

    @property
    def is_open_now(self):
        now = timezone.localtime().time()
        return self.opens_at <= now <= self.closes_at

    @property
    def can_accept_orders(self):
        return self.is_active and self.is_licence_valid and self.is_open_now


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

class Category(models.Model):
    """Whisky, Beer, Wine, Vodka ... (shown as chips on the home page)."""

    class BottleShape(models.TextChoices):
        SPIRIT = "spirit", "Spirit bottle"
        WINE = "wine", "Wine bottle"
        CAN = "can", "Can"

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True)
    emoji = models.CharField(max_length=4, blank=True)
    bottle_shape = models.CharField(max_length=10, choices=BottleShape.choices, default=BottleShape.SPIRIT)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    """
    A drink in the master catalogue (same for every shop).
    Price and stock live on ShopProduct because each shop sets its own.
    """

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=150)
    brand = models.CharField(max_length=100)
    volume_ml = models.PositiveIntegerField()
    abv = models.DecimalField("Alcohol %", max_digits=4, decimal_places=1)
    mrp = models.DecimalField(max_digits=9, decimal_places=2)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    color = models.CharField(max_length=7, default="#B7791F", help_text="Bottle colour used when there is no image.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.volume_ml} ml)"

    @property
    def volume_label(self):
        if self.volume_ml >= 1000:
            return f"{self.volume_ml / 1000:g} L"
        return f"{self.volume_ml} ml"


class ShopProduct(TimeStampedModel):
    """A product as sold by a particular shop — its price and stock."""

    shop = models.ForeignKey(RetailShop, on_delete=models.CASCADE, related_name="inventory")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="shop_listings")
    price = models.DecimalField(max_digits=9, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "product"], name="unique_product_per_shop"),
        ]

    def __str__(self):
        return f"{self.product} @ {self.shop.name}"

    @property
    def in_stock(self):
        return self.is_available and self.stock > 0

    @property
    def discount_percent(self):
        mrp = self.product.mrp
        if mrp and self.price < mrp:
            return int((mrp - self.price) / mrp * 100)
        return 0


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def generate_otp():
    return f"{random.randint(0, 9999):04d}"


class Order(TimeStampedModel):
    """One order = items from ONE licensed shop, delivered by ONE partner."""

    class Status(models.TextChoices):
        PLACED = "placed", "Order placed"
        CONFIRMED = "confirmed", "Confirmed by shop"
        PACKED = "packed", "Packed"
        PICKED_UP = "picked_up", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        UPI = "upi", "UPI"
        CARD = "card", "Card"
        COD = "cod", "Cash on delivery"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    shop = models.ForeignKey(RetailShop, on_delete=models.PROTECT, related_name="orders")
    delivery_partner = models.ForeignKey(
        DeliveryPartner, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )

    # Copy of the address at order time (the saved address may change later)
    delivery_address = models.TextField()

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)

    # Money
    item_total = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    platform_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0"))
    grand_total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.UPI)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    # Compliance at the doorstep
    delivery_otp = models.CharField(max_length=4, default=generate_otp)
    age_confirmed_by_customer = models.BooleanField(default=False)
    id_checked_at_delivery = models.BooleanField(default=False)

    # Delivery trip (filled in step by step from the delivery partner app)
    assigned_at = models.DateTimeField(null=True, blank=True)
    reached_shop_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    reached_customer_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    distance_km = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal("0"), help_text="Shop to customer.")
    rider_earning = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0"), help_text="Paid to the delivery partner.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_number

    # Rider pay: ₹25 base + ₹7 per km, at least ₹30
    RIDER_BASE_PAY = Decimal("25")
    RIDER_PAY_PER_KM = Decimal("7")
    RIDER_MIN_PAY = Decimal("30")

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = "BZ" + timezone.now().strftime("%y%m%d") + f"{random.randint(0, 99999):05d}"
        if not self.distance_km:
            # No maps integration yet, so use a believable dummy distance (0.8 – 4.5 km)
            self.distance_km = Decimal(str(round(random.uniform(0.8, 4.5), 1)))
        if not self.rider_earning:
            self.rider_earning = max(self.RIDER_BASE_PAY + self.RIDER_PAY_PER_KM * self.distance_km, self.RIDER_MIN_PAY).quantize(Decimal("1"))
        super().save(*args, **kwargs)

    def cancel(self, reason):
        """Cancel the order and put the items back in the shop's stock."""
        if self.status != self.Status.CANCELLED:
            for item in self.items.select_related("shop_product"):
                if item.shop_product:
                    item.shop_product.stock += item.quantity
                    item.shop_product.save(update_fields=["stock"])
        self.status = self.Status.CANCELLED
        self.cancel_reason = reason
        if self.payment_status == self.PaymentStatus.PAID:
            self.payment_status = self.PaymentStatus.REFUNDED
        self.save()

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    shop_product = models.ForeignKey(ShopProduct, on_delete=models.SET_NULL, null=True)

    # Copies so the order history stays correct even if the product changes
    product_name = models.CharField(max_length=150)
    volume_ml = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=9, decimal_places=2)
    quantity = models.PositiveSmallIntegerField()

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    @property
    def line_total(self):
        return self.price * self.quantity
