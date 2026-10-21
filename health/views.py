
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@require_GET
def health_check(request):
    return JsonResponse({
        "status": "ok",
        "service": "srm-chatbots-api",
        "message": "SRM Chatbots API is running",
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def protected_test(request):
    return Response({
        "status": "ok",
        "message": "JWT authentication successful",
        "username": request.user.username,
    })
