from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class RegistrationAPITests(APITestCase):
    def test_successful_registration(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "registration_test_user",
                "email": "registration-test@example.com",
                "first_name": "Test",
                "last_name": "User",
                "password": "SafeTestPass!987654",
                "password_confirm": "SafeTestPass!987654",
            },
            format="json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username="registration_test_user")
        self.assertTrue(user.check_password("SafeTestPass!987654"))
        self.assertNotEqual(user.password, "SafeTestPass!987654")


class JWTLoginAPITests(APITestCase):
    def setUp(self):
        self.username = "jwt_test_user"
        self.password = "SafeLoginPass!987654"

        User.objects.create_user(
            username=self.username,
            email="jwt-test@example.com",
            password=self.password,
        )

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "username": self.username,
                "password": self.password,
            },
            format="json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_rejects_incorrect_password(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "username": self.username,
                "password": "WrongPassword!987654",
            },
            format="json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)



class ProtectedEndpointJWTTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="protected_test_user",
            email="protected-test@example.com",
            password="SafeProtectedPass!987654",
        )

    def test_protected_endpoint_rejects_unauthenticated_request(self):
        response = self.client.get(
            "/api/health/protected-test/",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_endpoint_accepts_valid_access_token(self):
        access_token = str(RefreshToken.for_user(self.user).access_token)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {access_token}"
        )

        response = self.client.get(
            "/api/health/protected-test/",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.user.username)
        self.assertEqual(
            response.data["message"],
            "JWT authentication successful",
        )



class JWTRefreshAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="refresh_test_user",
            email="refresh-test@example.com",
            password="SafeRefreshPass!987654",
        )

    def test_refresh_token_returns_new_access_token(self):
        refresh_token = str(RefreshToken.for_user(self.user))

        response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": refresh_token},
            format="json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertTrue(response.data["access"])

    
    def test_invalid_refresh_token_is_rejected(self):
        response = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": "not-a-valid-refresh-token"},
            format="json",
            HTTP_HOST="localhost",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
