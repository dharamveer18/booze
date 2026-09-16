# Booze — Project Guide

A plain-English guide to how this project is built and how everything fits together.
If you are new to the code, read this file top to bottom once; after that use it as a map.

---

## 1. What this project is

**Booze is a quick-commerce platform for alcohol delivery.**

The important business rule, which shapes the whole codebase:

> Booze never buys, stores or sells alcohol. Every order is sold by a **licensed retail shop**.
> Booze only provides the website, the app and the delivery person.

That is why the code always keeps three things separate:

* the **shop** owns the stock, sets the price and is the legal seller,
* the **customer** places the order and must prove they are of legal drinking age,
* the **delivery partner** carries the sealed order and checks the ID at the door.

Four kinds of people use the system:

| Role | Where they log in | What they can do |
|---|---|---|
| Customer | the storefront `/` | browse drinks, order, track their order |
| Admin | the admin panel `/admin/` | see and manage everything |
| Retailer (shop owner) | the admin panel `/admin/` | see **only their own shops** and those orders |
| Delivery partner | the partner app `/rider/` | accept orders, deliver, see earnings |

---

## 2. Quick start

```bash
# 1. Run the server (uses the project's virtual environment)
/var/www/env/envbooze/bin/python manage.py runserver

# 2. First time only: create the database tables
/var/www/env/envbooze/bin/python manage.py migrate

# 3. Fill the database with demo data (safe to run again)
/var/www/env/envbooze/bin/python manage.py seed_data

# 4. Create your own admin login
/var/www/env/envbooze/bin/python manage.py createsuperuser
```

Then open:

| Address | What it is |
|---|---|
| http://localhost:8000/ | Storefront (customers) |
| http://localhost:8000/admin/ | Booze admin panel (admins + retailers) |
| http://localhost:8000/rider/ | Delivery partner app |
| http://localhost:8000/django-admin/ | Django's own built-in admin, for developers |

**Demo logins** (all created by `seed_data`, password `demo1234`):

| Role | Username |
|---|---|
| Customer | `9999999999` |
| Retailer | `9000000001`, `9000000011`, `9000000021` |
| Delivery partner (verified) | `9100000000` … `9100000008`, `9100000011` |
| Delivery partner (pending verification) | `9100000009`, `9100000010` |

Admins are not seeded — make one with `createsuperuser`.

---

## 3. The big picture

The project is one Django project (`booze`) with three apps. Each app is one "area" of the product:

```
                       ┌──────────────────────────────┐
  customer   ───────►  │  delivery/   →  /            │  storefront + ALL database models
                       └──────────────────────────────┘
                                     ▲
                       ┌─────────────┴────────────────┐
  admin / retailer ──► │  admin/      →  /admin/      │  admin panel (reads delivery's models)
                       └──────────────────────────────┘
                                     ▲
                       ┌─────────────┴────────────────┐
  delivery partner ──► │  rider/      →  /rider/      │  partner app (reads delivery's models)
                       └──────────────────────────────┘
```

**Only `delivery/` owns database tables.** `admin/` and `rider/` have no models of their own —
they are just screens on top of the same data. That keeps one source of truth for orders,
shops, products and users.

A note on folder names: the folder `admin/` would clash with Django's own admin, so inside
Django it is registered with the label **`panel`**. That's why its URLs are named `panel:...`
and its templates live in `templates/panel/`.

---

## 4. Folder structure

```
booze/
├── manage.py                  # the command you run everything with
├── db.sqlite3                 # the database (a single file)
├── PROJECT_GUIDE.md           # this file
│
├── booze/                     # project settings — the "wiring"
│   ├── settings.py            # apps, database, business rules (fees, legal age)
│   ├── urls.py                # top-level address map: which app handles which prefix
│   ├── wsgi.py / asgi.py      # used when deploying to a real server
│
├── delivery/                  # STOREFRONT + all database models
│   ├── models.py              # every database table lives here
│   ├── views.py               # the pages: home, cart, checkout, orders
│   ├── urls.py                # storefront addresses
│   ├── forms.py               # signup form, login form, address form
│   ├── cart.py                # the shopping cart (kept in the browser session)
│   ├── shops.py               # picks which licensed shop is serving the visitor
│   ├── context_processors.py  # values every storefront page needs (cart, shop, age gate)
│   ├── admin.py               # registers models in Django's built-in admin
│   ├── migrations/            # database change history
│   ├── management/commands/
│   │   └── seed_data.py       # the demo-data command
│   ├── templates/delivery/    # storefront HTML
│   └── static/delivery/       # storefront CSS, JS, logo, favicons
│
├── admin/                     # ADMIN PANEL (Django label: "panel")
│   ├── views.py               # dashboard, users, retailers, partners, orders
│   ├── urls.py                # admin panel addresses
│   ├── forms.py               # login, add-user, order-update forms
│   ├── decorators.py          # @admin_required / @panel_required access rules
│   ├── scope.py               # limits retailers to their own shops
│   ├── context_processors.py  # sidebar counters
│   ├── templatetags/panel_tags.py   # ₹ formatting, status colours, initials
│   ├── templates/panel/       # admin panel HTML
│   └── static/panel/          # admin panel CSS + JS
│
└── rider/                     # DELIVERY PARTNER APP
    ├── views.py               # home, trip steps, history, earnings, profile
    ├── urls.py                # partner app addresses
    ├── forms.py               # login form, delivery (OTP/ID) form, issue form
    ├── decorators.py          # @rider_required access rule
    ├── templatetags/rider_tags.py   # trip time, "5 min ago", dummy map points
    ├── templates/rider/       # partner app HTML
    └── static/rider/          # partner app CSS + JS
```

---

## 5. How one page works (the request cycle)

Every page in Django follows the same four steps. Example: a customer opens `/orders/`.

1. **The address is matched.** `booze/urls.py` sees the address doesn't start with
   `admin/` or `rider/`, so it hands it to `delivery/urls.py`, which matches `orders/`
   and calls `views.order_list`.
2. **The view runs.** `order_list` in `delivery/views.py` fetches that customer's orders
   from the database.
3. **The template is filled in.** The view passes the orders to
   `delivery/templates/delivery/order_list.html`, which turns them into HTML.
4. **The page is sent back** to the browser, which then loads the CSS and JS from `static/`.

Two extra ideas used a lot in this project:

* **Context processors** put values into *every* page automatically, so you don't repeat
  yourself — the cart badge and the age gate on the storefront, the sidebar counters in
  the admin panel.
* **Decorators** sit above a view and decide who is allowed in, before the view runs:
  `@login_required`, `@admin_required`, `@panel_required`, `@rider_required`.

---

## 6. The URL map — what each address does

### 6.1 Top level (`booze/urls.py`)

| Address | Goes to |
|---|---|
| `/` | the storefront app (`delivery/urls.py`) |
| `/admin/` | the Booze admin panel (`admin/urls.py`) |
| `/rider/` | the delivery partner app (`rider/urls.py`) |
| `/django-admin/` | Django's built-in admin (developer tool) |
| `/favicon.ico` | redirects to the site icon |

### 6.2 Storefront — `delivery/urls.py` (prefix `/`)

| Address | Name in code | What it does | Who |
|---|---|---|---|
| `/` | `delivery:home` | Shop front: banners, categories, product rows, search (`?q=`) and category filter (`?category=`) | anyone |
| `/shop/choose/` | `delivery:choose_shop` | Switch which licensed shop you're buying from (empties the cart, because a cart belongs to one shop) | anyone · POST |
| `/age/confirm/` | `delivery:confirm_age` | Records "yes, I'm 21+" from the age popup | anyone · POST |
| `/cart/update/` | `delivery:cart_update` | Add/remove one item; returns the updated cart as JSON so the page doesn't reload | anyone · POST |
| `/checkout/` | `delivery:checkout` | Choose address + payment, tick the age confirmation, place the order | logged-in customer |
| `/orders/` | `delivery:order_list` | My past orders | logged-in customer |
| `/orders/<order_number>/` | `delivery:order_detail` | One order: progress tracker, **delivery OTP**, bill, shop licence | logged-in customer |
| `/signup/` | `delivery:signup` | Create a customer account (checks date of birth against the legal age) | visitors |
| `/login/` `/logout/` | `delivery:login` / `delivery:logout` | Sign in with mobile number, sign out | anyone |

### 6.3 Admin panel — `admin/urls.py` (prefix `/admin/`)

Names start with `panel:`. **A** = admins only, **A+R** = admins and retailers (retailers
see only their own shops).

| Address | Name | What it does | Who |
|---|---|---|---|
| `/admin/` | `panel:dashboard` | Admin: sales today, orders chart, "needs attention", recent orders. Retailer: their own sales, shops, stock | A+R |
| `/admin/login/` `/admin/logout/` | `panel:login` / `panel:logout` | Sign in / out. Customers are refused; delivery partners are pointed to `/rider/` | anyone |
| `/admin/users/` | `panel:users` | All accounts, with role tabs, search, filters, sorting, paging | A |
| `/admin/users/add/` | `panel:user_add` | Create any account and pick its type (customer / retailer / partner / admin) | A |
| `/admin/users/<id>/` | `panel:user_detail` | One account: details, change role, assign shops to a retailer, customer's orders | A |
| `/admin/retailers/` | `panel:shops` | Shops with licence tabs (valid / pending / expiring / expired) and filters | A+R |
| `/admin/retailers/<id>/` | `panel:shop_detail` | One shop: licence card, sales, lowest stock, recent orders | A+R |
| `/admin/delivery-partners/` | `panel:partners` | Riders with verification, availability and vehicle filters | A |
| `/admin/delivery-partners/<id>/` | `panel:partner_detail` | One rider: documents, stats, recent deliveries | A |
| `/admin/orders/` | `panel:orders` | All orders: status tabs, search, date range, retailer and payment filters | A+R |
| `/admin/orders/<order_number>/` | `panel:order_detail` | One order: items, bill, people, and (admins only) change status / assign rider | A+R |
| `/admin/actions/<key>/<id>/` | `panel:toggle` | The on/off buttons: verify licence, list/unlist shop, verify rider, verify age, activate/deactivate account | A · POST |

### 6.4 Delivery partner app — `rider/urls.py` (prefix `/rider/`)

Every page needs a logged-in delivery partner, and a partner can only open **their own** orders.

| Address | Name | What it does |
|---|---|---|
| `/rider/` | `rider:home` | Online switch, today's earnings, ongoing delivery, new order requests, weekly bonus |
| `/rider/login/` `/rider/logout/` | `rider:login` / `rider:logout` | Sign in / out (going offline on the way out) |
| `/rider/online/` | `rider:toggle_online` | Go online or offline (blocked mid-delivery, and until the account is verified) · POST |
| `/rider/orders/<order_number>/` | `rider:order` | The live trip: map, current step, items, pay, timeline |
| `/rider/orders/<order_number>/accept/` | `rider:accept` | Take the order · POST |
| `/rider/orders/<order_number>/skip/` | `rider:skip` | Hide this request for now · POST |
| `/rider/orders/<order_number>/next/` | `rider:advance` | Finish the current step: reached shop → picked up → reached customer · POST |
| `/rider/orders/<order_number>/deliver/` | `rider:deliver` | Final handover: OTP + ID check + cash · POST |
| `/rider/orders/<order_number>/release/` | `rider:release` | Give the order back to the pool (only before pickup) · POST |
| `/rider/orders/<order_number>/issue/` | `rider:issue` | Problem at the door → cancel and return to shop · POST |
| `/rider/history/` | `rider:history` | Past trips, with period and status filters |
| `/rider/earnings/` | `rider:earnings` | Week total, 7-day chart, bonus, cash in hand, payouts |
| `/rider/profile/` | `rider:profile` | Documents, verification, ratings, support, log out |

**Why names matter:** templates never hard-code addresses. They write
`{% url 'rider:home' %}` instead of `/rider/`. Change the address in one place and every
link follows.

---

## 7. The database

All tables are in `delivery/models.py`.

### People

| Model | In plain words |
|---|---|
| **User** | One login for everybody. Has a `role` (customer / shop_owner / delivery_partner / admin) and a `phone`. The role decides which app lets them in. |
| **Customer** | Extra details for a customer: date of birth, age-verification status, ID type and last 4 digits. |
| **Address** | A customer's saved delivery addresses. |
| **ShopOwner** | Extra details for a retailer: business name, GST, KYC. One owner can own several shops. |
| **DeliveryPartner** | Extra details for a rider: vehicle, driving licence, verified?, online?, rating. |

A `User` plus a profile is deliberate: the login is one thing, and what that person *is*
on the platform is another.

### Shops and products

| Model | In plain words |
|---|---|
| **RetailShop** | A licensed shop: licence number, type, expiry date, verified flag, address, opening hours. `can_accept_orders` is true only when the shop is active, the licence is verified and not expired, and the shop is open now. |
| **Category** | Whisky, Beer, Wine… used for the chips on the home page. |
| **Product** | A drink in the shared catalogue: brand, volume, alcohol %, MRP. No price here. |
| **ShopProduct** | The same product **in one shop**, with that shop's price and stock. This is what customers actually add to the cart. |

### Orders

| Model | In plain words |
|---|---|
| **Order** | One order from one shop, delivered by one rider. Holds the money split, the payment method and status, the delivery OTP, the compliance flags, the trip timestamps, the distance and the rider's pay. |
| **OrderItem** | One line of the order. It copies the product name, size and price, so an old order still reads correctly even if the product or price changes later. |

**Order statuses:** `placed` → `confirmed` → `packed` → `picked_up` → `delivered`,
with `cancelled` possible along the way.

---

## 8. How the main flows work

### 8.1 A customer orders a drink

1. The visitor opens `/`. `shops.py` picks a licensed shop that can serve them; the header
   shows "Delivering from …". The 21+ popup appears on the first visit.
2. Clicking **ADD** calls `/cart/update/` in the background. The cart is stored in the
   browser session as `{shop_product_id: quantity}` — nothing is written to the database yet.
3. **Checkout** (`/checkout/`) requires a login. Before the order is created the code checks:
   the customer is old enough, the age box is ticked, an address is selected, the shop is
   open with a valid licence, and there is enough stock.
4. The order is created with its items, the shop's stock goes down, the cart is emptied,
   and a 4-digit **delivery OTP** is generated.
5. The customer lands on `/orders/<order_number>/`, which shows the progress tracker and the OTP.

### 8.2 Admin and retailer

* Admins see everything and can change orders, verify licences and riders, and create users.
* Retailers sign in to the same panel but `scope.py` filters every page down to their own
  shops, so another shop's order simply doesn't exist for them ("not found").
* Retailers can't change orders and never see the customer's phone number, address or OTP.

### 8.3 A delivery partner delivers

1. The partner signs in at `/rider/` and switches **Online** (only possible once an admin
   has verified the account).
2. Unassigned orders appear as requests showing pay, distance, pickup shop and drop area.
   **Accept** locks the order to them, so two riders can't take the same one.
3. They then slide through the steps: reached shop → picked up (order becomes
   "Out for delivery") → reached customer.
4. At the door they must tick **ID checked** and **not intoxicated**, collect cash for
   cash-on-delivery orders, and enter the customer's **OTP**. Only then does the order
   become `delivered`.
5. If something goes wrong they release the order (before pickup) or report an issue
   (after pickup), which cancels it and puts the stock back in the shop.

### 8.4 The money

| Who | What they get |
|---|---|
| Customer pays | items + delivery fee (free above ₹999) + ₹9 platform fee |
| Shop receives | the item money (it is the legal seller) |
| Delivery partner earns | ₹25 base + ₹7 per km, minimum ₹30, plus a ₹500 weekly bonus at 40 trips |

---

## 9. Settings you can change

In `booze/settings.py`:

```python
AUTH_USER_MODEL = 'delivery.User'   # our own user model instead of Django's default

LEGAL_DRINKING_AGE = 21             # differs by Indian state (18 / 21 / 25)
ESTIMATED_DELIVERY_MINUTES = 15     # the "delivery in X minutes" promise
DELIVERY_FEE = Decimal('30')
FREE_DELIVERY_ABOVE = Decimal('999')
PLATFORM_FEE = Decimal('9')
```

Rider pay lives on the `Order` model (`RIDER_BASE_PAY`, `RIDER_PAY_PER_KM`, `RIDER_MIN_PAY`),
and the weekly bonus in `rider/views.py` (`WEEKLY_TARGET`, `WEEKLY_BONUS`).

---

## 10. How the look and feel is built

* **No CSS framework.** Each app has one hand-written stylesheet with colour, spacing and
  radius values set at the top, so the whole app stays consistent.
* **Templates inherit.** Each app has a `base.html` with the shared shell; every page
  extends it and fills in blocks. Small repeated pieces live in `partials/`.
* **Icons** are inline SVG in a partial — `{% include "…/icon.html" with name="store" %}`.
* **Plain JavaScript**, no libraries: cart updates, the admin filters, and the rider's
  slide-to-confirm and bottom sheets.
* **Product images** are drawn as SVG bottles from the product's colour, because the image
  library (Pillow) isn't installed. Set `Product.image_url` to use a real photo.
* **The rider map is a drawing**, not a real map. The pins and the moving rider come from
  `rider_tags.py`, which makes stable fake positions from the order id.

---

## 11. Common tasks

| I want to… | Do this |
|---|---|
| Add a product or shop | `/django-admin/`, or the seed file for demo data |
| Let a new rider work | `/admin/delivery-partners/` → **Verify** |
| Create any account | `/admin/users/add/` |
| See a customer's OTP | `/admin/orders/<order number>/` → Payment & compliance |
| Reload demo data | `python manage.py seed_data` |
| Change the database structure | edit `delivery/models.py`, then `makemigrations` and `migrate` |

---

## 12. Known gaps (deliberate, for later)

* **Maps, distance and travel time are fake.** Real ones need a maps API and GPS from the rider.
* **Payments are not real.** Choosing UPI or card only records the choice.
* **Age verification is manual** — an admin ticks it. A real KYC provider should do it.
* **Retailers can't confirm or pack orders yet**, so riders can pick up an order the shop
  hasn't confirmed.
* **Delivery law differs by state**, and some states don't allow home delivery at all. The
  legal drinking age is a single setting and should become per-state.
* **`.gitignore` currently ignores `migrations/` and `static/`.** Both usually *should* be
  committed — migrations are the database history, and `static/` holds the CSS, JS and logo.
  Worth removing those two lines.
