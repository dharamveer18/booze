"""
WSGI config for booze project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os
import sys

# Project root: localhost vs PythonAnywhere
LOCAL_PATH = "/var/www/Dharamveer/booze"
PYTHONANYWHERE_PATH = "/home/boozze/booze"

path = PYTHONANYWHERE_PATH if os.path.isdir(PYTHONANYWHERE_PATH) else LOCAL_PATH

if path not in sys.path:
    sys.path.insert(0, path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "booze.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
