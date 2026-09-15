from django.apps import AppConfig


class AdminPanelConfig(AppConfig):
    """
    The Booze admin panel.

    The folder is called `admin`, but Django's own admin already uses the label "admin",
    so this app uses the label "panel" (URL namespace, templates and static files use it too).
    """

    name = "admin"
    label = "panel"
    verbose_name = "Booze admin panel"
