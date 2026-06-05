from .conftest import create_tenant, create_user


class TestRegister:
    async def test_success(self, client):
        response = await client.post(
            "/api/v1/users/register",
            json={
                "email": "new@test.com",
                "password": "strongpass123",
                "company_name": "New Company",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new@test.com"
        assert "id" in body
        assert "hashed_password" not in body  # пароль никогда не возвращаем

    async def test_duplicate_email(self, client, db):
        tenant = await create_tenant(db, "Dupe Email Corp")
        await create_user(db, tenant, email="dupe@test.com")

        response = await client.post(
            "/api/v1/users/register",
            json={
                "email": "dupe@test.com",
                "password": "pass123",
                "company_name": "Another Corp",
            },
        )

        assert response.status_code == 409

    async def test_duplicate_company(self, client, db):
        await create_tenant(db, "Existing Company")

        response = await client.post(
            "/api/v1/users/register",
            json={
                "email": "unique@test.com",
                "password": "pass123",
                "company_name": "Existing Company",
            },
        )

        assert response.status_code == 409

    async def test_invalid_email(self, client):
        response = await client.post(
            "/api/v1/users/register",
            json={
                "email": "not-an-email",
                "password": "pass123",
                "company_name": "Test Corp",
            },
        )

        assert response.status_code == 422  # Pydantic validation error

    async def test_first_user_gets_admin_role(self, client, db):
        """Основатель компании должен стать admin своего тенанта."""
        response = await client.post(
            "/api/v1/users/register",
            json={
                "email": "founder@test.com",
                "password": "pass123",
                "company_name": "Founder Corp",
            },
        )

        assert response.status_code == 201
        assert response.json()["role"] == "admin"


class TestGetMe:
    async def test_returns_current_user(self, client, regular_user, user_headers):
        response = await client.get("/api/v1/users/me", headers=user_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == regular_user.email
        assert body["id"] == str(regular_user.id)

    async def test_no_token_returns_401(self, client):
        response = await client.get("/api/v1/users/me")

        assert response.status_code == 401

    async def test_invalid_token_returns_401(self, client):
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401

    async def test_response_has_no_password(self, client, user_headers):
        """Хэш пароля никогда не должен утекать в ответе."""
        response = await client.get("/api/v1/users/me", headers=user_headers)

        assert "hashed_password" not in response.json()
        assert "password" not in response.json()
