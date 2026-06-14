from unittest.mock import AsyncMock, MagicMock

import pytest

from eka.deps import get_rag_pipeline
from eka.main import app

from .conftest import auth_headers, create_tenant, create_user


@pytest.mark.asyncio
async def test_chat_endpoint_success(client, regular_user, user_headers):
    mock_pipeline = AsyncMock()
    mock_pipeline.chat.return_value = "Mocked RAG Answer"

    app.dependency_overrides[get_rag_pipeline] = lambda: mock_pipeline

    response = await client.post(
        "/api/v1/chat",
        params={"query": "Как дела?"},
        headers=user_headers,
    )

    assert response.status_code == 200

    data = response.json()
    assert data["answer"] == "Mocked RAG Answer"

    mock_pipeline.chat.assert_called_once_with(
        query="Как дела?",
        tenant_id=regular_user.tenant_id,
    )


@pytest.mark.asyncio
async def test_chat_stream_endpoint_sse_format(client, user_headers):
    mock_pipeline = MagicMock()

    async def mock_stream(*args, **kwargs):
        yield "Токен "
        yield "1"

    mock_pipeline.chat_stream = mock_stream

    app.dependency_overrides[get_rag_pipeline] = lambda: mock_pipeline

    response = await client.post(
        "/api/v1/chat/stream",
        params={"query": "Stream test"},
        headers=user_headers,
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    content = response.text

    assert "data: Токен \n\n" in content
    assert "data: 1\n\n" in content
    assert "data: [DONE]\n\n" in content


@pytest.mark.asyncio
async def test_chat_endpoint_strict_tenant_isolation(
    client,
    db,
    regular_user,
):
    tenant_b = await create_tenant(db, name="Competitor Corp")
    await create_user(db, tenant_b, email="spy@competitor.com")

    mock_pipeline = AsyncMock()
    mock_pipeline.chat.return_value = "Secret data"

    app.dependency_overrides[get_rag_pipeline] = lambda: mock_pipeline

    response = await client.post(
        "/api/v1/chat",
        params={"query": "Give me secrets"},
        headers=auth_headers(regular_user),
    )

    assert response.status_code == 200

    call_kwargs = mock_pipeline.chat.call_args.kwargs

    assert call_kwargs["tenant_id"] == regular_user.tenant_id
    assert call_kwargs["tenant_id"] != tenant_b.id
