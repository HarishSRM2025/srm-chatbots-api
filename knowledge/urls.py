
from rest_framework.routers import DefaultRouter

from .views import KnowledgeSourceViewSet

router = DefaultRouter()
router.register(
    r"",
    KnowledgeSourceViewSet,
    basename="knowledge-source",
)

urlpatterns = router.urls
