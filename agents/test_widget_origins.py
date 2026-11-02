from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from agents.models import Agent


class WidgetOriginConfigurationTests(APITestCase):
    def test_owner_can_configure_widget_origin(self):
        owner = get_user_model().objects.create_user(username="origin-owner")
        agent = Agent.objects.create(owner=owner, name="Widget", system_prompt="Help", is_public=True)
        origin = "https://widget.example"
        endpoint = "/api/chat/widget/sessions/"
        payload = {"agent_id": agent.pk}
        self.assertEqual(self.client.post(endpoint, payload, HTTP_ORIGIN=origin).status_code, 403)
        self.client.force_authenticate(owner)
        url = f"/api/agents/{agent.pk}/"
        response = self.client.patch(url, {"allowed_origins": [origin + "/", origin]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["allowed_origins"], [origin])
        for invalid in ["*", origin + "/page", "javascript:alert(1)"]:
            self.assertEqual(self.client.patch(url, {"allowed_origins": [invalid]}, format="json").status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(endpoint, payload, HTTP_ORIGIN=origin).status_code, 201)
        self.assertEqual(self.client.post(endpoint, payload, HTTP_ORIGIN="https://other.example").status_code, 403)

    def test_stored_origins_and_agent_specific_changes(self):
        owner = get_user_model().objects.create_user(username="changing-origins")
        first = Agent.objects.create(owner=owner, name="First", system_prompt="Help", is_public=True,
                                     allowed_origins=[" https://first.example/ "])
        second = Agent.objects.create(owner=owner, name="Second", system_prompt="Help", is_public=True,
                                      allowed_origins=["https://second.example"])
        endpoint = "/api/chat/widget/sessions/"
        self.assertEqual(self.client.post(endpoint, {"agent_id": first.pk}, HTTP_ORIGIN="https://first.example").status_code, 201)
        self.assertEqual(self.client.post(endpoint, {"agent_id": second.pk}, HTTP_ORIGIN="https://first.example").status_code, 403)
        self.client.force_authenticate(owner)
        response = self.client.patch(f"/api/agents/{first.pk}/", {"allowed_origins": ["https://new.example/"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f"/api/agents/{first.pk}/").data["allowed_origins"], ["https://new.example"])
        self.client.force_authenticate(None)
        rejected = self.client.post(endpoint, {"agent_id": first.pk}, HTTP_ORIGIN="https://first.example")
        self.assertEqual(rejected.status_code, 403)
        self.assertIn("https://first.example", str(rejected.data["detail"]))
        self.assertIn(f"agent {first.pk}", str(rejected.data["detail"]))
        self.assertEqual(self.client.post(endpoint, {"agent_id": first.pk}, HTTP_ORIGIN="https://new.example").status_code, 201)
