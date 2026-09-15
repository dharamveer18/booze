from django import forms
from django.contrib.auth.forms import AuthenticationForm

from delivery.models import User


class RiderLoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "not_rider": "This app is only for Booze delivery partners.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Mobile number"
        self.fields["username"].widget.attrs.update({"placeholder": "10-digit mobile number", "inputmode": "numeric", "autocomplete": "username"})
        self.fields["password"].widget.attrs.update({"placeholder": "Password", "autocomplete": "current-password"})

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)  # blocks deactivated accounts
        if user.role != User.Role.DELIVERY_PARTNER or not hasattr(user, "delivery_partner"):
            raise forms.ValidationError(self.error_messages["not_rider"], code="not_rider")


class DeliverForm(forms.Form):
    """Everything the rider must confirm at the customer's door."""

    otp = forms.CharField(min_length=4, max_length=4, widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "placeholder": "••••"}))
    id_checked = forms.BooleanField(error_messages={"required": "Check the customer's government ID before handing over the order."})
    customer_sober = forms.BooleanField(error_messages={"required": "Don't deliver to a customer who appears intoxicated."})
    cash_collected = forms.BooleanField(required=False)

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order

    def clean_otp(self):
        otp = self.cleaned_data["otp"]
        if otp != self.order.delivery_otp:
            raise forms.ValidationError("Wrong OTP. Ask the customer to read it from their order screen.")
        return otp

    def clean(self):
        data = super().clean()
        if self.order.payment_method == self.order.PaymentMethod.COD and not data.get("cash_collected"):
            self.add_error("cash_collected", "Collect the cash amount before completing the delivery.")
        return data


class ReportIssueForm(forms.Form):
    REASONS = [
        ("Customer not reachable at the address", "Customer not reachable"),
        ("Customer could not show a valid ID", "Customer couldn't show valid ID"),
        ("Customer appeared underage", "Customer looks underage"),
        ("Customer appeared intoxicated", "Customer appears intoxicated"),
        ("Customer refused the order", "Customer refused the order"),
    ]
    reason = forms.ChoiceField(choices=REASONS, widget=forms.RadioSelect)
