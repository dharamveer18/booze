from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect


def panel_required(view):
    """Admins and retailers may open this page (retailers only ever see their own shops' data)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.can_use_panel:
            return view(request, *args, **kwargs)

        if request.user.is_authenticated:
            messages.error(request, "Your account doesn't have access to the admin panel.")
        return redirect_to_login(request.get_full_path(), login_url="panel:login")

    return wrapper


def admin_required(view):
    """Only admins may open this page."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_admin:
            return view(request, *args, **kwargs)

        # A retailer is allowed in the panel, just not on this page
        if request.user.is_authenticated and request.user.can_use_panel:
            messages.error(request, "Only admins can open that page.")
            return redirect("panel:dashboard")

        if request.user.is_authenticated:
            messages.error(request, "Your account doesn't have access to the admin panel.")
        return redirect_to_login(request.get_full_path(), login_url="panel:login")

    return wrapper
