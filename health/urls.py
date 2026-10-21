
from django.urls import path

from .views import health_check, protected_test

urlpatterns = [
    path("", health_check, name="health-check"),
    path("protected-test/", protected_test, name="protected-test"),
]
