from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("users/", views.user_list, name="users"),
    path("users/add/", views.user_add, name="user_add"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),

    path("retailers/", views.shop_list, name="shops"),
    path("retailers/<int:pk>/", views.shop_detail, name="shop_detail"),

    path("delivery-partners/", views.partner_list, name="partners"),
    path("delivery-partners/<int:pk>/", views.partner_detail, name="partner_detail"),

    path("orders/", views.order_list, name="orders"),
    path("orders/<str:order_number>/", views.order_detail, name="order_detail"),

    path("actions/<str:key>/<int:pk>/", views.toggle, name="toggle"),
]
