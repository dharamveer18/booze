from functools import wraps

from django.contrib.auth.views import redirect_to_login

from delivery.models import User


def rider_required(view):
    """Only logged-in users with the delivery partner role (and a rider profile) can open the page.
    The view receives the DeliveryPartner as `partner`."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and user.role == User.Role.DELIVERY_PARTNER and hasattr(user, "delivery_partner"):
            return view(request, request.user.delivery_partner, *args, **kwargs)
        return redirect_to_login(request.get_full_path(), login_url="rider:login")

    return wrapper
