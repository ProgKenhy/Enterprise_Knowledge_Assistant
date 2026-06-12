import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue, ScoredPoint

from eka.core.rag.retriever import HybridRetriever


@pytest.fixture
def mock_qdrant():
    qdrant = AsyncMock()
    qdrant.query_points.return_value = MagicMock(points=[])
    return qdrant


@pytest.fixture
def retriever():
    # Мокируем тяжелые ML-модели, чтобы тесты летали
    with (
        patch("eka.core.rag.retriever.TextEmbedding") as mock_dense,
        patch("eka.core.rag.retriever.SparseTextEmbedding") as mock_sparse,
    ):
        mock_dense = MagicMock()
        mock_dense.query_embed.return_value = [MagicMock(tolist=lambda: [0.1, 0.2])]

        mock_sparse = MagicMock()
        sparse_vec = MagicMock()
        sparse_vec.indices.tolist.return_value = [1]
        sparse_vec.values.tolist.return_value = [0.5]
        mock_sparse.query_embed.return_value = [sparse_vec]

        mock_dense.return_value = mock_dense
        mock_sparse.return_value = mock_sparse

        r = HybridRetriever()
        r._dense_model = mock_dense
        r._sparse_model = mock_sparse
        return r


@pytest.mark.asyncio
async def test_retriever_strict_tenant_filter_in_db(retriever, mock_qdrant):
    """
    Проверяем, что Retriever формирует жесткий Must-фильтр
    по tenant_id при обращении к Qdrant.
    """
    tenant_id = uuid.uuid4()

    with patch("eka.core.rag.retriever.get_qdrant", return_value=mock_qdrant):
        await retriever.retrieve("test query", tenant_id)

    # Qdrant вызывается дважды (dense и sparse)
    assert mock_qdrant.query_points.call_count == 2

    for call in mock_qdrant.query_points.call_args_list:
        query_filter = call.kwargs.get("query_filter")
        assert isinstance(query_filter, Filter), "Фильтр обязан быть передан в Qdrant!"

        must_conditions = query_filter.must or []

        # Ищем условие tenant_id в секции must (обязательные условия)
        tenant_conditions = [
            cond
            for cond in must_conditions
            if isinstance(cond, FieldCondition) and cond.key == "tenant_id"
        ]

        assert len(tenant_conditions) == 1, "Должно быть ровно одно жесткое условие по tenant_id"
        match_obj = tenant_conditions[0].match

        assert isinstance(match_obj, MatchValue), (
            "Для tenant_id должен использоваться точный матч (MatchValue), "
            "а не поиск по тексту (MatchText) или списку (MatchAny)."
        )
        assert match_obj.value == str(tenant_id), (
            "Обнаружена уязвимость: в фильтр ушел чужой tenant_id!"
        )


def test_rrf_fusion_math(retriever):
    """Проверяем, что RRF (Reciprocal Rank Fusion) повышает документы,
    найденные и в dense, и в sparse индексах."""
    p1 = ScoredPoint(id="1", version=1, score=0.9, payload={"text": "a"})
    p2 = ScoredPoint(id="2", version=1, score=0.8, payload={"text": "b"})

    dense_res = [p1, p2]
    sparse_res = [p2]  # p2 есть в обоих

    fused = retriever._rrf_fusion(dense_res, sparse_res, k=60)

    assert str(fused[0].id) == "2", "Элемент из обоих индексов должен быть первым"
