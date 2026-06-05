from datetime import datetime


class TestHealth:
    async def test_returns_200(self, client):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    async def test_response_structure(self, client):
        response = await client.get("/api/v1/health")
        data = response.json()

        assert set(data.keys()) == {"status", "timestamp", "services"}

        assert isinstance(data["status"], str)
        assert isinstance(data["services"], dict)

    async def test_healthy_status_with_db(self, client):
        response = await client.get("/api/v1/health")
        data = response.json()

        assert data["status"] == "healthy"
        assert data["services"]["postgresql"]["status"] == "healthy"

    async def test_timestamp_is_valid_isoformat(self, client):
        response = await client.get("/api/v1/health")
        data = response.json()

        # проверка, что timestamp реально парсится
        parsed = datetime.fromisoformat(data["timestamp"])
        assert parsed is not None

    async def test_app_service_is_healthy(self, client):
        response = await client.get("/api/v1/health")
        data = response.json()

        assert data["services"]["app"]["status"] == "healthy"
