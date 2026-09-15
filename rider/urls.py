from django.urls import path

from . import views

app_name = "rider"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("online/", views.toggle_online, name="toggle_online"),

    path("orders/<str:order_number>/", views.order_detail, name="order"),
    path("orders/<str:order_number>/accept/", views.accept_order, name="accept"),
    path("orders/<str:order_number>/skip/", views.skip_order, name="skip"),
    path("orders/<str:order_number>/next/", views.advance_trip, name="advance"),
    path("orders/<str:order_number>/deliver/", views.deliver, name="deliver"),
    path("orders/<str:order_number>/release/", views.release_order, name="release"),
    path("orders/<str:order_number>/issue/", views.report_issue, name="issue"),

    path("history/", views.history, name="history"),
    path("earnings/", views.earnings, name="earnings"),
    path("profile/", views.profile, name="profile"),
]
