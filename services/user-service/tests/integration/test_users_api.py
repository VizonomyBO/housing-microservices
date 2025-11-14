"""
Integration tests for user API endpoints
"""
import pytest
import json


@pytest.mark.integration
class TestMeEndpoint:
    """Test /users/me endpoint"""

    def test_get_me_success(self, client, sample_user, auth_headers, mock_auth_service):
        """Test getting current user profile"""
        response = client.get("/users/me", headers=auth_headers)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert "user" in data
        assert data["user"]["email"] == sample_user.email

    def test_get_me_no_token(self, client):
        """Test getting current user without token"""
        response = client.get("/users/me")

        assert response.status_code == 401
        data = json.loads(response.data)
        assert "error" in data

    def test_update_me_success(self, client, sample_user, auth_headers, mock_auth_service):
        """Test updating current user profile"""
        update_data = {"first_name": "Jane", "last_name": "Smith"}

        response = client.put(
            "/users/me",
            data=json.dumps(update_data),
            content_type="application/json",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["user"]["first_name"] == "Jane"
        assert data["user"]["last_name"] == "Smith"

    def test_update_me_invalid_field(self, client, sample_user, auth_headers, mock_auth_service):
        """Test updating current user with invalid field"""
        # Users can't change their own role
        update_data = {"role": "admin"}

        response = client.put(
            "/users/me",
            data=json.dumps(update_data),
            content_type="application/json",
            headers=auth_headers,
        )

        assert response.status_code == 400


@pytest.mark.integration
class TestUserEndpoints:
    """Test user management endpoints"""

    def test_get_user_by_id_as_admin(
        self, client, sample_user, admin_auth_headers, mock_auth_service
    ):
        """Test admin getting user by ID"""
        response = client.get(f"/users/{sample_user.user_id}", headers=admin_auth_headers)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["user"]["email"] == sample_user.email

    def test_get_user_by_id_as_self(self, client, sample_user, auth_headers, mock_auth_service):
        """Test user getting their own profile by ID"""
        response = client.get(f"/users/{sample_user.user_id}", headers=auth_headers)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["user"]["email"] == sample_user.email

    def test_get_user_by_id_forbidden(
        self, client, sample_user, admin_user, auth_headers, mock_auth_service
    ):
        """Test regular user trying to get another user's profile"""
        response = client.get(f"/users/{admin_user.user_id}", headers=auth_headers)

        assert response.status_code == 403

    def test_list_users_as_admin(self, client, admin_auth_headers, mock_auth_service):
        """Test listing all users as admin"""
        response = client.get("/users", headers=admin_auth_headers)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert "users" in data
        assert "total" in data

    def test_list_users_as_regular_user(self, client, auth_headers, mock_auth_service):
        """Test regular user trying to list all users"""
        response = client.get("/users", headers=auth_headers)

        assert response.status_code == 403

    def test_update_user_as_admin(self, client, sample_user, admin_auth_headers, mock_auth_service):
        """Test admin updating a user"""
        update_data = {"first_name": "Updated", "role": "staff"}

        response = client.put(
            f"/users/{sample_user.user_id}",
            data=json.dumps(update_data),
            content_type="application/json",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["user"]["first_name"] == "Updated"
        assert data["user"]["role"] == "staff"

    def test_delete_user_as_admin(self, client, sample_user, admin_auth_headers, mock_auth_service):
        """Test admin deleting a user"""
        response = client.delete(f"/users/{sample_user.user_id}", headers=admin_auth_headers)

        assert response.status_code == 200

    def test_delete_self_as_admin(self, client, admin_user, admin_auth_headers, mock_auth_service):
        """Test admin trying to delete themselves"""
        response = client.delete(f"/users/{admin_user.user_id}", headers=admin_auth_headers)

        assert response.status_code == 400

    def test_search_users_as_admin(
        self, client, sample_user, admin_auth_headers, mock_auth_service
    ):
        """Test searching users as admin"""
        response = client.get("/users/search?q=john", headers=admin_auth_headers)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert "users" in data
        assert len(data["users"]) > 0


@pytest.mark.integration
class TestSystemEndpoints:
    """Test system endpoints"""

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert data["service"] == "user-service"

    def test_index(self, client):
        """Test index endpoint"""
        response = client.get("/")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["service"] == "user-service"
        assert "endpoints" in data
