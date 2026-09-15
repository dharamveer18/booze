"""
Fill the database with demo data:  python manage.py seed_data

Creates categories, a catalogue of drinks, licensed shops with inventory, shop owners,
delivery partners, customers and a month of orders (so the admin panel has something to show).

Demo customer login (storefront) → phone 9999999999 / password demo1234
Admin panel login → create your own with:  python manage.py createsuperuser

Safe to run more than once (it only adds the random customers/orders the first time).
"""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from delivery.models import (
    Address, Category, Customer, DeliveryPartner, Order, OrderItem, Product, RetailShop, ShopOwner, ShopProduct, User,
)

DEMO_PASSWORD = "demo1234"

CATEGORIES = [
    # name, emoji, bottle shape
    ("Whisky", "🥃", "spirit"),
    ("Beer", "🍺", "can"),
    ("Wine", "🍷", "wine"),
    ("Vodka", "🍸", "spirit"),
    ("Rum", "🥥", "spirit"),
    ("Gin", "🫒", "spirit"),
    ("Breezers", "🍹", "can"),
]

PRODUCTS = [
    # category, name, brand, ml, abv, mrp, colour
    ("Whisky", "Blenders Pride Rare Premium Whisky", "Blenders", 750, 42.8, 1150, "#8a4b16"),
    ("Whisky", "Royal Stag Deluxe Whisky", "Royal Stag", 750, 42.8, 820, "#b7791f"),
    ("Whisky", "Johnnie Walker Black Label", "Johnnie", 750, 40, 3900, "#2b2b2b"),
    ("Whisky", "Amrut Fusion Single Malt", "Amrut", 700, 50, 4600, "#6b3a12"),
    ("Whisky", "Jameson Irish Whiskey", "Jameson", 750, 40, 2700, "#1f5f3a"),
    ("Beer", "Kingfisher Premium Lager Can", "Kingfisher", 500, 4.8, 140, "#c8102e"),
    ("Beer", "Budweiser Magnum Strong Beer", "Budweiser", 500, 7.5, 180, "#b5121b"),
    ("Beer", "Bira 91 White Wheat Beer", "Bira", 500, 4.7, 190, "#f2b705"),
    ("Beer", "Heineken Lager Can", "Heineken", 500, 5, 200, "#0b7a3b"),
    ("Beer", "Simba Stout", "Simba", 650, 7.5, 230, "#3a2a1a"),
    ("Wine", "Sula Dindori Reserve Shiraz", "Sula", 750, 13.5, 1250, "#5b0f24"),
    ("Wine", "Fratelli Sette Red", "Fratelli", 750, 14, 1900, "#7b1e3a"),
    ("Wine", "Grover Zampa Sauvignon Blanc", "Grover", 750, 12.5, 1100, "#8a9a3b"),
    ("Wine", "Sula Brut Tropicale Rosé", "Sula", 750, 12, 1450, "#d4677f"),
    ("Vodka", "Smirnoff No. 21 Vodka", "Smirnoff", 750, 42.8, 1100, "#b3202a"),
    ("Vodka", "Absolut Vodka", "Absolut", 750, 40, 1800, "#2c5aa0"),
    ("Vodka", "Magic Moments Green Apple", "Magic", 750, 37.5, 750, "#3f9b3a"),
    ("Rum", "Old Monk XXX Rum", "Old Monk", 750, 42.8, 520, "#3b1f0e"),
    ("Rum", "Bacardi Carta Blanca", "Bacardi", 750, 37.5, 1050, "#9aa5ad"),
    ("Rum", "Captain Morgan Dark Rum", "Captain", 750, 42.8, 850, "#5a2d0c"),
    ("Gin", "Bombay Sapphire London Dry Gin", "Bombay", 750, 40, 2300, "#2a7bbf"),
    ("Gin", "Greater Than London Dry Gin", "Greater", 750, 42.8, 1200, "#0f766e"),
    ("Gin", "Hapusa Himalayan Dry Gin", "Hapusa", 700, 43, 3500, "#4c5b2b"),
    ("Breezers", "Bacardi Breezer Cranberry", "Breezer", 275, 4.8, 110, "#b0124c"),
    ("Breezers", "Bacardi Breezer Blackberry", "Breezer", 275, 4.8, 110, "#4b1d6b"),
]

# licence_status: "valid", "expiring" (in 20 days), "expired", "pending" (not verified yet)
SHOPS = [
    ("Paradise Wines & Spirits", "FL2/MH/2024/00871", "Shop 4, Hill Road, Bandra West", "Mumbai", "400050", "valid"),
    ("The Liquor Cellar", "FL2/MH/2023/01344", "Linking Road, Khar West", "Mumbai", "400052", "valid"),
    ("Cheers Wine Shop", "FL2/MH/2022/00419", "Lokhandwala Market, Andheri West", "Mumbai", "400053", "expiring"),
    ("Spirit Square", "L1/KA/2024/02210", "100 Feet Road, Indiranagar", "Bengaluru", "560038", "valid"),
    ("Bottle Barn", "L1/KA/2021/00987", "Koramangala 5th Block", "Bengaluru", "560095", "expired"),
    ("Hops & Grapes", "L1/DL/2025/00133", "Khan Market", "New Delhi", "110003", "pending"),
]

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Ishaan", "Kabir", "Rohan", "Arjun", "Karan", "Nikhil", "Siddharth",
    "Ananya", "Diya", "Priya", "Sneha", "Riya", "Kavya", "Meera", "Neha", "Pooja", "Tanvi",
]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Patel", "Shah", "Mehta", "Kapoor", "Gupta", "Das", "Rao"]


class Command(BaseCommand):
    help = "Load demo data for the Booze storefront and admin panel."

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(7)
        products = self.create_catalogue()
        shops = self.create_shops(products)
        partners = self.create_delivery_partners()
        customers = self.create_customers()

        if not Order.objects.exists():
            self.create_orders(customers, shops, partners)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Product.objects.count()} products, {RetailShop.objects.count()} shops, "
            f"{DeliveryPartner.objects.count()} delivery partners, {Customer.objects.count()} customers, "
            f"{Order.objects.count()} orders.\n"
            f"Demo customer → phone 9999999999 / password {DEMO_PASSWORD}\n"
            "Admin panel → run `python manage.py createsuperuser`, then open /admin/"
        ))

    # -- helpers -------------------------------------------------------------

    def make_user(self, phone, first, last, role):
        user, created = User.objects.get_or_create(
            username=phone, defaults={"first_name": first, "last_name": last, "phone": phone, "role": role}
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user

    def create_catalogue(self):
        categories = {}
        for order, (name, emoji, shape) in enumerate(CATEGORIES):
            categories[name], _ = Category.objects.update_or_create(
                slug=name.lower(), defaults={"name": name, "emoji": emoji, "bottle_shape": shape, "sort_order": order}
            )

        products = []
        for cat, name, brand, ml, abv, mrp, color in PRODUCTS:
            product, _ = Product.objects.update_or_create(
                name=name,
                defaults={
                    "category": categories[cat], "brand": brand, "volume_ml": ml,
                    "abv": Decimal(str(abv)), "mrp": Decimal(mrp), "color": color,
                },
            )
            products.append(product)
        return products

    def create_shops(self, products):
        owners = [
            ShopOwner.objects.get_or_create(
                user=self.make_user(f"90000000{i}1", first, last, User.Role.SHOP_OWNER),
                defaults={"business_name": business, "is_kyc_verified": i != 2},
            )[0]
            for i, (first, last, business) in enumerate([
                ("Rohit", "Mehta", "Mehta Retail Pvt Ltd"),
                ("Suresh", "Gowda", "Gowda Beverages"),
                ("Anita", "Khanna", "Khanna Traders"),
            ])
        ]

        valid_till = {
            "valid": date.today() + timedelta(days=365),
            "expiring": date.today() + timedelta(days=20),
            "expired": date.today() - timedelta(days=15),
            "pending": date.today() + timedelta(days=300),
        }

        shops = []
        for i, (name, licence, address, city, pincode, status) in enumerate(SHOPS):
            shop, _ = RetailShop.objects.update_or_create(
                licence_number=licence,
                defaults={
                    "name": name, "phone": f"0221234{i:04d}", "owner": owners[min(i // 2, 2)],
                    "licence_type": licence.split("/")[0], "licence_valid_till": valid_till[status],
                    "is_licence_verified": status != "pending",
                    "address": address, "city": city, "pincode": pincode,
                    # open all day so the demo always works
                    "opens_at": time(0, 0), "closes_at": time(23, 59, 59),
                },
            )
            for product in products:
                discount = Decimal(random.choice([0, 0, 5, 8, 10, 12, 15])) / 100
                ShopProduct.objects.update_or_create(
                    shop=shop, product=product,
                    defaults={
                        "price": (product.mrp * (1 - discount)).quantize(Decimal("1")),
                        "stock": random.choice([0, 8, 15, 24, 40]) if product.id % 9 == 0 else random.choice([12, 24, 40]),
                    },
                )
            shops.append(shop)
        return shops

    def create_delivery_partners(self):
        partners = []
        vehicles = list(DeliveryPartner.Vehicle.values)
        for i in range(12):
            first, last = FIRST_NAMES[i % 10], LAST_NAMES[(i * 5) % len(LAST_NAMES)]
            user = self.make_user(f"91000000{i:02d}", first, last, User.Role.DELIVERY_PARTNER)
            partner, _ = DeliveryPartner.objects.get_or_create(
                user=user,
                defaults={
                    "date_of_birth": date(1990 + i % 10, (i % 12) + 1, 10),
                    "vehicle_type": vehicles[i % len(vehicles)],
                    "vehicle_number": f"MH0{i % 9 + 1}AB{1000 + i * 37}",
                    "driving_licence_number": f"MH{i:02d}2019000{i:04d}",
                    "is_verified": i < 9,
                    "is_online": i < 9 and i % 3 != 0,
                    "rating": Decimal(str(round(random.uniform(4.1, 5.0), 1))),
                },
            )
            partners.append(partner)
        return partners

    def create_customers(self):
        customers = []
        demo = self.make_user("9999999999", "Demo", "Customer", User.Role.CUSTOMER)
        people = [(demo, date(1994, 1, 1))]
        for i in range(44):
            first, last = FIRST_NAMES[(i * 7) % 20], LAST_NAMES[(i * 3) % len(LAST_NAMES)]
            user = self.make_user(f"98{random.randint(10000000, 99999999)}", first, last, User.Role.CUSTOMER)
            people.append((user, date(random.randint(1975, 2003), random.randint(1, 12), random.randint(1, 28))))

        for index, (user, dob) in enumerate(people):
            customer, _ = Customer.objects.get_or_create(
                user=user, defaults={"date_of_birth": dob, "is_age_verified": index % 5 != 3}
            )
            if not customer.addresses.exists():
                Address.objects.create(
                    customer=customer, house=f"Flat {100 + index * 3}, Sea Breeze Apts",
                    street="Carter Road, Bandra West", city="Mumbai", pincode="400050", is_default=True,
                )
            customers.append(customer)

        # Spread sign-up dates over the last 3 months
        for customer in customers[1:]:
            joined = timezone.now() - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23))
            User.objects.filter(id=customer.user_id).update(date_joined=joined)
        return customers

    def create_orders(self, customers, shops, partners):
        open_shops = [s for s in shops if s.is_licence_valid]
        verified_partners = [p for p in partners if p.is_verified]
        active_statuses = ["placed", "confirmed", "packed", "picked_up"]

        for i in range(140):
            days_ago = random.choices(range(30), weights=[6 if d < 14 else 2 for d in range(30)])[0]
            placed_at = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=days_ago), time(random.randint(11, 22), random.randint(0, 59)))
            )
            if placed_at > timezone.now():
                placed_at = timezone.now() - timedelta(minutes=random.randint(5, 50))

            if days_ago == 0:
                status = random.choice(active_statuses + ["delivered"])
            else:
                status = random.choices(["delivered", "cancelled"], weights=[9, 1])[0]

            shop = random.choice(open_shops)
            listings = random.sample(list(shop.inventory.select_related("product")), k=random.randint(1, 4))
            lines = [(sp, random.randint(1, 3)) for sp in listings]
            item_total = sum(sp.price * qty for sp, qty in lines)
            delivery_fee = Decimal("0") if item_total >= 999 else Decimal("30")

            order = Order.objects.create(
                customer=random.choice(customers),
                shop=shop,
                delivery_partner=random.choice(verified_partners) if status not in ("placed", "confirmed") else None,
                delivery_address="Flat 1202, Sea Breeze Apts, Carter Road, Bandra West, Mumbai - 400050",
                status=status,
                item_total=item_total,
                delivery_fee=delivery_fee,
                platform_fee=Decimal("9"),
                grand_total=item_total + delivery_fee + Decimal("9"),
                payment_method=random.choice(["upi", "upi", "card", "cod"]),
                payment_status={"delivered": "paid", "cancelled": "refunded"}.get(status, "pending"),
                age_confirmed_by_customer=True,
                id_checked_at_delivery=status == "delivered",
                delivered_at=placed_at + timedelta(minutes=random.randint(9, 25)) if status == "delivered" else None,
                cancel_reason="Customer could not show a valid ID" if status == "cancelled" else "",
            )
            for sp, qty in lines:
                OrderItem.objects.create(
                    order=order, shop_product=sp, product_name=sp.product.name,
                    volume_ml=sp.product.volume_ml, price=sp.price, quantity=qty,
                )
            trip = {"created_at": placed_at}
            if order.delivery_partner_id:
                trip["assigned_at"] = placed_at + timedelta(minutes=1)
            if status in ("picked_up", "delivered"):
                trip["reached_shop_at"] = placed_at + timedelta(minutes=4)
                trip["picked_up_at"] = placed_at + timedelta(minutes=6)
            if status == "delivered":
                trip["reached_customer_at"] = order.delivered_at - timedelta(minutes=1)
            Order.objects.filter(id=order.id).update(**trip)
