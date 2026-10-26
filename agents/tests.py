
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Agent


User = get_user_model()


class AgentAPITests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username="agent_user1",
            email="agent_user1@example.com",
            password="TestPass!987654",
        )
        self.user2 = User.objects.create_user(
            username="agent_user2",
            email="agent_user2@example.com",
            password="TestPass!987654",
        )

        self.agent1 = Agent.objects.create(
            owner=self.user1,
            name="My First Agent",
            description="First user's agent",
            system_prompt="You are a helpful assistant.",
        )
        self.agent2 = Agent.objects.create(
            owner=self.user2,
            name="My First Agent",
            description="Second user's agent",
            system_prompt="You are another helpful assistant.",
        )

        self.list_url = "/api/agents/"
        self.detail_url = f"/api/agents/{self.agent1.id}/"

    def test_list_requires_authentication(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    
    def test_list_only_returns_current_users_agents(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.agent1.id)


    def test_user_cannot_retrieve_another_users_agent(self):
        self.client.force_authenticate(user=self.user1)
        url = f"/api/agents/{self.agent2.id}/"

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_user_cannot_update_another_users_agent(self):
        self.client.force_authenticate(user=self.user1)
        url = f"/api/agents/{self.agent2.id}/"

        response = self.client.patch(
            url,
            {"name": "Unauthorized change"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.agent2.refresh_from_db()
        self.assertEqual(self.agent2.name, "My First Agent")

    def test_user_cannot_delete_another_users_agent(self):
        self.client.force_authenticate(user=self.user1)
        url = f"/api/agents/{self.agent2.id}/"

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertTrue(Agent.objects.filter(pk=self.agent2.pk).exists())

    def test_create_assigns_owner_from_authenticated_user(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.list_url,
            {
                "name": "New Agent",
                "description": "Created through API",
                "system_prompt": "Be accurate and helpful.",
                "owner": self.user2.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        agent = Agent.objects.get(name="New Agent", owner=self.user1)
        self.assertEqual(response.data["owner"], self.user1.id)
        self.assertEqual(agent.owner, self.user1)
        self.assertNotEqual(agent.owner, self.user2)

    def test_create_uses_default_model_and_status(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.list_url,
            {
                "name": "Defaults Agent",
                "system_prompt": "Answer clearly.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(response.data["model_name"], "gemini-3.5-flash-lite")
        self.assertEqual(response.data["status"], Agent.Status.ACTIVE)

    def test_duplicate_name_is_rejected_for_same_user(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            self.list_url,
            {
                "name": "My First Agent",
                "system_prompt": "Another prompt.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_same_name_is_allowed_for_different_users(self):
        self.assertTrue(
            Agent.objects.filter(
                owner=self.user1,
                name="My First Agent",
            ).exists()
        )
        self.assertTrue(
            Agent.objects.filter(
                owner=self.user2,
                name="My First Agent",
            ).exists()
        )

    def test_owner_cannot_be_changed_through_update(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.patch(
            self.detail_url,
            {"owner": self.user2.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent1.refresh_from_db()
        self.assertEqual(self.agent1.owner, self.user1)

    def test_user_can_update_own_agent(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.patch(
            self.detail_url,
            {"description": "Updated description"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent1.refresh_from_db()
        self.assertEqual(self.agent1.description, "Updated description")

    def test_user_can_delete_own_agent(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.delete(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Agent.objects.filter(pk=self.agent1.pk).exists()
        )

    def test_new_agent_is_private_by_default(self):
        self.assertFalse(self.agent1.is_public)
        self.client.force_authenticate(user=self.user1)

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_public"])

    def test_owner_can_make_agent_public(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.patch(
            self.detail_url,
            {"is_public": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent1.refresh_from_db()
        self.assertTrue(self.agent1.is_public)
        self.assertTrue(response.data["is_public"])

    def test_owner_can_make_agent_private_again(self):
        self.agent1.is_public = True
        self.agent1.save(update_fields=["is_public"])
        self.client.force_authenticate(user=self.user1)

        response = self.client.patch(
            self.detail_url,
            {"is_public": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent1.refresh_from_db()
        self.assertFalse(self.agent1.is_public)

    def test_user_cannot_change_another_users_agent_visibility(self):
        self.client.force_authenticate(user=self.user1)
        url = f"/api/agents/{self.agent2.id}/"

        response = self.client.patch(
            url,
            {"is_public": True},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.agent2.refresh_from_db()
        self.assertFalse(self.agent2.is_public)
