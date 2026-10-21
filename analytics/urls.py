
from django.urls import path

from analytics.views import AnalyticsOverviewView

urlpatterns = [
    path("overview/", AnalyticsOverviewView.as_view(), name="analytics-overview"),
]
