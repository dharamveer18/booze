from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm

app_name = "delivery"

urlpatterns = [
    path("", views.home, name="home"),
    path("shop/choose/", views.choose_shop, name="choose_shop"),
    path("age/confirm/", views.confirm_age, name="confirm_age"),

    path("cart/update/", views.cart_update, name="cart_update"),
    path("checkout/", views.checkout, name="checkout"),

    path("orders/", views.order_list, name="order_list"),
    path("orders/<str:order_number>/", views.order_detail, name="order_detail"),

    path("signup/", views.signup, name="signup"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="delivery/login.html",
            authentication_form=LoginForm,
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
