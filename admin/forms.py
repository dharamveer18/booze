from datetime import date

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.utils import timezone

from delivery.models import Customer, DeliveryPartner, Order, RetailShop, ShopOwner, User


def age_on(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class AdminLoginForm(AuthenticationForm):
    """Normal Django login, but only admins and retailers are let in."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "no_access": "This account doesn't have access to the admin panel.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Username or phone"
        self.fields["username"].widget.attrs.update({"placeholder": "e.g. admin or 9000000001", "autofocus": True})
        self.fields["password"].widget.attrs.update({"placeholder": "••••••••"})

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)  # blocks inactive users
        if user.role == User.Role.DELIVERY_PARTNER:
            raise forms.ValidationError("Delivery partners sign in to the partner app at /rider/.", code="no_access")
        if not user.can_use_panel:
            raise forms.ValidationError(self.error_messages["no_access"], code="no_access")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class AddUserForm(forms.Form):
    """
    Create any kind of account from the admin panel.
    Some fields are only needed for one role — see ROLE_REQUIRED_FIELDS.
    """

    ROLE_REQUIRED_FIELDS = {
        User.Role.CUSTOMER: ["date_of_birth"],
        User.Role.SHOP_OWNER: ["business_name"],
        User.Role.DELIVERY_PARTNER: ["date_of_birth", "vehicle_type"],
        User.Role.ADMIN: [],
    }
    MIN_RIDER_AGE = 18

    role = forms.ChoiceField(choices=User.Role.choices, initial=User.Role.CUSTOMER, widget=forms.RadioSelect)

    # Basic details
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    phone = forms.RegexField(
        regex=r"^[6-9]\d{9}$", error_messages={"invalid": "Enter a valid 10-digit mobile number."},
        widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "10-digit mobile number"}),
    )
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"placeholder": "name@example.com"}))

    # Sign in
    username = forms.CharField(
        max_length=150, required=False,
        help_text="Leave blank to use the phone number.",
        widget=forms.TextInput(attrs={"placeholder": "Same as phone"}),
    )
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    # Customer + delivery partner
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    # Retailer
    business_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"placeholder": "Registered business name"}))
    gst_number = forms.CharField(label="GST number", max_length=15, required=False)
    shops = forms.ModelMultipleChoiceField(
        queryset=RetailShop.objects.select_related("owner").order_by("name"),
        required=False, widget=forms.CheckboxSelectMultiple,
        help_text="The retailer will be able to see these shops in the admin panel.",
    )

    # Delivery partner
    vehicle_type = forms.ChoiceField(choices=DeliveryPartner.Vehicle.choices, required=False)
    vehicle_number = forms.CharField(max_length=15, required=False, widget=forms.TextInput(attrs={"placeholder": "MH01AB1234"}))
    driving_licence_number = forms.CharField(max_length=20, required=False)

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if User.objects.filter(phone=phone).exists() or User.objects.filter(username=phone).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
        return phone

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if username and User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is taken.")
        return username

    def clean(self):
        data = super().clean()
        role = data.get("role")

        # Fields that this role needs
        for field in self.ROLE_REQUIRED_FIELDS.get(role, []):
            if not data.get(field):
                self.add_error(field, "This field is required for this account type.")

        dob = data.get("date_of_birth")
        if dob and role == User.Role.CUSTOMER and age_on(dob) < settings.LEGAL_DRINKING_AGE:
            self.add_error("date_of_birth", f"Customers must be at least {settings.LEGAL_DRINKING_AGE} years old.")
        if dob and role == User.Role.DELIVERY_PARTNER and age_on(dob) < self.MIN_RIDER_AGE:
            self.add_error("date_of_birth", f"Delivery partners must be at least {self.MIN_RIDER_AGE} years old.")

        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        elif p1:
            try:
                password_validation.validate_password(p1)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return data

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        role = data["role"]
        user = User.objects.create_user(
            username=data["username"] or data["phone"],
            password=data["password1"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            phone=data["phone"],
            role=role,
        )

        if role == User.Role.CUSTOMER:
            Customer.objects.create(user=user, date_of_birth=data["date_of_birth"])

        elif role == User.Role.SHOP_OWNER:
            owner = ShopOwner.objects.create(user=user, business_name=data["business_name"], gst_number=data["gst_number"])
            data["shops"].update(owner=owner)

        elif role == User.Role.DELIVERY_PARTNER:
            DeliveryPartner.objects.create(
                user=user,
                date_of_birth=data["date_of_birth"],
                vehicle_type=data["vehicle_type"],
                vehicle_number=data["vehicle_number"],
                driving_licence_number=data["driving_licence_number"],
            )
        return user


class UserRoleForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["role"]

    def clean_role(self):
        role = self.cleaned_data["role"]
        user = self.instance
        # Customers and riders need details (date of birth, vehicle…) we don't have here
        if role == User.Role.CUSTOMER and not hasattr(user, "customer"):
            raise forms.ValidationError("This account has no customer profile. Use “Add user” to create a customer.")
        if role == User.Role.DELIVERY_PARTNER and not hasattr(user, "delivery_partner"):
            raise forms.ValidationError("This account has no rider profile. Use “Add user” to create a delivery partner.")
        return role

    def save(self, commit=True):
        user = super().save(commit)
        # A new retailer gets an empty shop-owner profile; shops can be assigned right after
        if user.role == User.Role.SHOP_OWNER and not hasattr(user, "shop_owner"):
            ShopOwner.objects.create(user=user, business_name=user.display_name)
        return user


class AssignShopsForm(forms.Form):
    shops = forms.ModelMultipleChoiceField(
        queryset=RetailShop.objects.select_related("owner").order_by("name"),
        required=False, widget=forms.CheckboxSelectMultiple,
    )

    @transaction.atomic
    def save(self, owner):
        chosen = self.cleaned_data["shops"]
        owner.shops.exclude(pk__in=chosen).update(owner=None)
        chosen.update(owner=owner)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class OrderUpdateForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["status", "delivery_partner", "payment_status", "id_checked_at_delivery", "cancel_reason"]
        widgets = {"cancel_reason": forms.TextInput(attrs={"placeholder": "Required when cancelling"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only verified riders with an active account can be assigned
        self.fields["delivery_partner"].queryset = DeliveryPartner.objects.filter(
            is_verified=True, user__is_active=True
        ).select_related("user")
        self.fields["delivery_partner"].empty_label = "Not assigned"

    def clean(self):
        data = super().clean()
        status = data.get("status")
        if status == Order.Status.CANCELLED and not data.get("cancel_reason"):
            self.add_error("cancel_reason", "Please give a reason for cancelling.")
        if status == Order.Status.DELIVERED and not data.get("id_checked_at_delivery"):
            self.add_error("id_checked_at_delivery", "An order can't be delivered without checking the customer's ID.")
        if status in (Order.Status.PICKED_UP, Order.Status.DELIVERED) and not data.get("delivery_partner"):
            self.add_error("delivery_partner", "Assign a delivery partner first.")
        return data

    def save(self, commit=True):
        order = super().save(commit=False)
        previous_status = Order.objects.get(pk=order.pk).status

        if order.status == Order.Status.DELIVERED and not order.delivered_at:
            order.delivered_at = timezone.now()

        # Put the stock back at the shop when an order gets cancelled
        if order.status == Order.Status.CANCELLED and previous_status != Order.Status.CANCELLED:
            for item in order.items.select_related("shop_product"):
                if item.shop_product:
                    item.shop_product.stock += item.quantity
                    item.shop_product.save(update_fields=["stock"])

        if commit:
            order.save()
        return order
