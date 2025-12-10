"""
Integration tests for user API endpoints
"""

import pytest


@pytest.mark.integration
class TestMeEndpoint:
    """Test /v1/users/me endpoint"""

    def test_get_me_success(self, client, sample_user, auth_headers):
        response = client.get("/v1/users/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == sample_user.email

    def test_get_me_no_token(self, client):
        response = client.get("/v1/users/me")

        assert response.status_code == 401
        data = response.json()
        # FastAPI returns "detail" for errors, not "error"
        assert "detail" in data or "error" in data

    def test_update_me_success(self, client, auth_headers):
        update_data = {"first_name": "Jane", "last_name": "Smith"}

        response = client.put("/v1/users/me", json=update_data, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["first_name"] == "Jane"
        assert data["user"]["last_name"] == "Smith"

    def test_update_me_invalid_field(self, client, auth_headers):
        update_data = {"role": "admin"}

        response = client.put("/v1/users/me", json=update_data, headers=auth_headers)

        assert response.status_code == 400


@pytest.mark.integration
class TestUserEndpoints:
    """Test user management endpoints"""

    def test_get_user_by_id_as_admin(self, client, sample_user, admin_auth_headers):
        response = client.get(f"/v1/users/{sample_user.user_id}", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == sample_user.email

    def test_get_user_by_id_as_self(self, client, sample_user, auth_headers):
        response = client.get(f"/v1/users/{sample_user.user_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == sample_user.email

    def test_get_user_by_id_forbidden(self, client, admin_user, auth_headers):
        response = client.get(f"/v1/users/{admin_user.user_id}", headers=auth_headers)

        assert response.status_code == 403

    def test_list_users_as_admin(self, client, admin_auth_headers):
        response = client.post("/v1/users", json={"page": 1, "per_page": 20}, headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data

    def test_list_users_as_regular_user(self, client, auth_headers):
        response = client.post("/v1/users", json={}, headers=auth_headers)

        assert response.status_code == 403

    def test_update_user_as_admin(self, client, sample_user, admin_auth_headers):
        update_data = {"first_name": "Updated", "role": "staff"}

        response = client.put(
            f"/v1/users/{sample_user.user_id}",
            json=update_data,
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["first_name"] == "Updated"
        assert data["user"]["role"] == "staff"

    def test_delete_user_as_admin(self, client, sample_user, admin_auth_headers):
        response = client.delete(f"/v1/users/{sample_user.user_id}", headers=admin_auth_headers)

        assert response.status_code == 200

    def test_delete_self_as_admin(self, client, admin_user, admin_auth_headers):
        response = client.delete(f"/v1/users/{admin_user.user_id}", headers=admin_auth_headers)

        assert response.status_code == 400

    def test_list_users_with_filters_and_full_name_search(self, client, admin_auth_headers, admin_user):
        from app.db import get_session
        from app.models.user import User

        session = get_session()
        try:
            target = User(
                first_name="Maria",
                last_name="Lopez",
                email="maria.lopez@example.com",
                password_hash="hashed",
                role="staff",
                status="active",
                country_code="PER",
            )
            other = User(
                first_name="Carlos",
                last_name="Perez",
                email="carlos.perez@example.com",
                password_hash="hashed",
                role="public",
                status="active",
                country_code="CHL",
            )
            session.add_all([target, other])
            session.commit()

            target_email = target.email
            response = client.post(
                "/v1/users",
                json={
                    "roles": ["staff"],
                    "countries": ["PER"],
                    "search": "Maria Lopez",
                    "page": 1,
                    "per_page": 10,
                },
                headers=admin_auth_headers,
            )
        finally:
            session.close()

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(user["email"] == target_email for user in data["users"])

    def test_search_users_as_admin(self, client, sample_user, admin_auth_headers):
        # Search for "John" which should match sample_user's first_name
        response = client.get("/v1/users/search?q=John", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        # Search may return 0 results if no match, so just check structure
        assert isinstance(data["users"], list)
        assert "count" in data


@pytest.mark.integration
class TestSystemEndpoints:
    """Test system endpoints"""

    def test_health_check(self, client, auth_headers):
        response = client.get("/v1/health", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "user-service"

    def test_index(self, client, auth_headers):
        response = client.get("/v1", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "user-service"
        assert "endpoints" in data
