from datetime import date

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm

from .models import Address, Customer, User


class SignupForm(forms.Form):
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"placeholder": "Your full name"}))
    phone = forms.RegexField(
        regex=r"^[6-9]\d{9}$",
        error_messages={"invalid": "Enter a valid 10-digit mobile number."},
        widget=forms.TextInput(attrs={"placeholder": "10-digit mobile number", "inputmode": "numeric"}),
    )
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    password = forms.CharField(min_length=8, widget=forms.PasswordInput(attrs={"placeholder": "At least 8 characters"}))

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if User.objects.filter(username=phone).exists() or User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("An account with this number already exists. Please log in.")
        return phone

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < settings.LEGAL_DRINKING_AGE:
            raise forms.ValidationError(
                f"You must be at least {settings.LEGAL_DRINKING_AGE} years old to use Booze."
            )
        return dob

    def save(self):
        data = self.cleaned_data
        first_name, _, last_name = data["full_name"].strip().partition(" ")
        user = User.objects.create_user(
            username=data["phone"],
            phone=data["phone"],
            role=User.Role.CUSTOMER,
            password=data["password"],
            first_name=first_name,
            last_name=last_name,
        )
        Customer.objects.create(user=user, date_of_birth=data["date_of_birth"])
        return user


class LoginForm(AuthenticationForm):
    """Django's login form, with the username relabelled as phone number."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Mobile number"
        self.fields["username"].widget.attrs.update({"placeholder": "10-digit mobile number", "inputmode": "numeric"})
        self.fields["password"].widget.attrs.update({"placeholder": "Your password"})


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["label", "house", "street", "landmark", "city", "pincode"]
        widgets = {
            "label": forms.RadioSelect,
            "house": forms.TextInput(attrs={"placeholder": "Flat / House no. / Building"}),
            "street": forms.TextInput(attrs={"placeholder": "Street, area, locality"}),
            "landmark": forms.TextInput(attrs={"placeholder": "Nearby landmark (optional)"}),
            "city": forms.TextInput(attrs={"placeholder": "City"}),
            "pincode": forms.TextInput(attrs={"placeholder": "6-digit pincode", "inputmode": "numeric"}),
        }
