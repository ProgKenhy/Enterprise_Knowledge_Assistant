from tests.conftest import create_tenant, create_user


class TestLogin:
    async def test_success(self, client, db):
        tenant = await create_tenant(db, "Login Corp")
        await create_user(db, tenant, email="login@test.com", password="secret123")

        response = await client.post(
            "/api/v1/auth/token",
            data={"username": "login@test.com", "password": "secret123"},
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "Bearer"

    async def test_wrong_password(self, client, db):
        tenant = await create_tenant(db, "Wrong Pass Corp")
        await create_user(db, tenant, email="wp@test.com", password="correct")

        response = await client.post(
            "/api/v1/auth/token",
            data={"username": "wp@test.com", "password": "wrong"},
        )

        assert response.status_code == 401

    async def test_nonexistent_user(self, client):
        response = await client.post(
            "/api/v1/auth/token",
            data={"username": "nobody@test.com", "password": "pass"},
        )

        assert response.status_code == 401

    async def test_empty_password(self, client, db):
        tenant = await create_tenant(db, "Empty Pass Corp")
        await create_user(db, tenant, email="ep@test.com", password="secret")

        response = await client.post(
            "/api/v1/auth/token",
            data={"username": "ep@test.com", "password": ""},
        )

        assert response.status_code == 422


class TestRefresh:
    async def test_success(self, client, db):
        """Refresh-токен выдаёт новую пару токенов."""
        tenant = await create_tenant(db, "Refresh Corp")
        await create_user(db, tenant, email="refresh@test.com", password="pass123")

        # Получаем токены через логин
        login = await client.post(
            "/api/v1/auth/token",
            data={"username": "refresh@test.com", "password": "pass123"},
        )
        refresh_token = login.json()["refresh_token"]

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_invalid_token(self, client):
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.valid.token"},
        )

        assert response.status_code == 401

    async def test_access_token_rejected(self, client, regular_user):
        """
        Access-токен не должен работать как refresh.
        Это проверяет что токены не взаимозаменяемы.
        """
        from eka.services.token import create_token_pair

        tokens = create_token_pair(user_id=regular_user.id)

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens.access_token},  # намеренно шлём access
        )

        assert response.status_code == 401
