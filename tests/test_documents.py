import io
from uuid import uuid4

from eka.db.models import UserRole
from tests.conftest import auth_headers, create_tenant, create_user

# Минимальный валидный PDF-заголовок (не настоящий PDF, но с нужным magic bytes)
FAKE_PDF = b"%PDF-1.4 fake content for testing"
FAKE_DOCX = b"PK\x03\x04fake docx content"  # DOCX — это ZIP, начинается с PK


def pdf_file(content: bytes = FAKE_PDF, filename: str = "test.pdf"):
    return ("file", (filename, io.BytesIO(content), "application/pdf"))


def docx_file(content: bytes = FAKE_DOCX):
    return (
        "file",
        (
            "test.docx",
            io.BytesIO(content),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    )


class TestUploadDocument:
    async def test_admin_can_upload_pdf(self, client, admin_headers, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        response = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("doc.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"title": "Test Document"},
            headers=admin_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "Test Document"
        assert body["source_type"] == "pdf"
        assert body["status"] == "pending"

    async def test_admin_can_upload_docx(self, client, admin_headers, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        response = await client.post(
            "/api/v1/docs/documents",
            files={"file": docx_file()[1]},
            data={"title": "Word Doc"},
            headers=admin_headers,
        )

        assert response.status_code == 201
        assert response.json()["source_type"] == "docx"

    async def test_regular_user_cannot_upload(self, client, user_headers, tmp_path, monkeypatch):
        """Загрузка документов — только для admin и выше."""
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        response = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("doc.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"title": "Test"},
            headers=user_headers,
        )

        assert response.status_code == 403

    async def test_unsupported_format_rejected(self, client, admin_headers, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        response = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("image.png", io.BytesIO(b"fake png"), "image/png")},
            data={"title": "Image"},
            headers=admin_headers,
        )

        assert response.status_code == 415

    async def test_duplicate_file_rejected(self, client, admin_headers, tmp_path, monkeypatch):
        """Одинаковый файл нельзя загрузить дважды в один тенант."""
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
        file_data = {"file": ("doc.pdf", io.BytesIO(FAKE_PDF), "application/pdf")}
        data = {"title": "Same File"}

        # Первый запрос: успешное создание
        first_response = await client.post(
            "/api/v1/docs/documents", files=file_data, data=data, headers=admin_headers
        )
        assert first_response.status_code == 201

        # Второй запрос: дубликат
        second_response = await client.post(
            "/api/v1/docs/documents", files=file_data, data=data, headers=admin_headers
        )
        assert second_response.status_code == 409

    async def test_no_auth_returns_401(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        response = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("doc.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"title": "Test"},
        )

        assert response.status_code == 401


class TestListDocuments:
    async def test_returns_own_tenant_documents(
        self, client, db, admin_user, admin_headers, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        # Загружаем 2 документа
        for i in range(2):
            await client.post(
                "/api/v1/docs/documents",
                files={
                    "file": (f"doc{i}.pdf", io.BytesIO(FAKE_PDF + bytes([i])), "application/pdf")
                },
                data={"title": f"Doc {i}"},
                headers=admin_headers,
            )

        response = await client.get("/api/v1/docs/documents", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    async def test_tenant_isolation(self, client, db, tmp_path, monkeypatch):
        """
        Пользователь видит только документы своего тенанта.
        Это один из самых важных тестов в мультитенантной системе.
        """
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        # Тенант A: загружает документ
        tenant_a = await create_tenant(db, "Tenant A")
        admin_a = await create_user(db, tenant_a, email="a@test.com", role=UserRole.admin)

        await client.post(
            "/api/v1/docs/documents",
            files={"file": ("a.pdf", io.BytesIO(FAKE_PDF + b"A"), "application/pdf")},
            data={"title": "Tenant A Doc"},
            headers=auth_headers(admin_a),
        )

        # Тенант B: смотрит список
        tenant_b = await create_tenant(db, "Tenant B")
        admin_b = await create_user(db, tenant_b, email="b@test.com", role=UserRole.admin)

        response = await client.get("/api/v1/docs/documents", headers=auth_headers(admin_b))

        assert response.status_code == 200
        assert response.json()["total"] == 0  # документы тенанта A не видны

    async def test_pagination(self, client, db, admin_user, admin_headers, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        for i in range(5):
            await client.post(
                "/api/v1/docs/documents",
                files={"file": (f"d{i}.pdf", io.BytesIO(FAKE_PDF + bytes([i])), "application/pdf")},
                data={"title": f"Doc {i}"},
                headers=admin_headers,
            )

        response = await client.get(
            "/api/v1/docs/documents?limit=2&offset=0", headers=admin_headers
        )

        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2

    async def test_filter_by_status(self, client, admin_headers, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        await client.post(
            "/api/v1/docs/documents",
            files={"file": ("f.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"title": "Pending Doc"},
            headers=admin_headers,
        )

        response = await client.get("/api/v1/docs/documents?status=pending", headers=admin_headers)

        assert response.status_code == 200
        items = response.json()["items"]
        assert all(d["status"] == "pending" for d in items)


class TestGetDocument:
    async def test_get_existing(self, client, admin_headers, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        upload = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("doc.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"title": "My Doc"},
            headers=admin_headers,
        )
        doc_id = upload.json()["id"]

        response = await client.get(f"/api/v1/docs/documents/{doc_id}", headers=admin_headers)

        assert response.status_code == 200
        assert response.json()["id"] == doc_id

    async def test_not_found(self, client, admin_headers):
        response = await client.get(
            f"/api/v1/docs/documents/{uuid4()}",
            headers=admin_headers,
        )

        assert response.status_code == 404

    async def test_cannot_get_other_tenants_document(self, client, db, tmp_path, monkeypatch):
        """
        Документ другого тенанта должен возвращать 404,
        а не 403 — не раскрываем что документ существует.
        """
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        # Тенант A создаёт документ
        tenant_a = await create_tenant(db, "A Corp")
        admin_a = await create_user(db, tenant_a, email="adma@test.com", role=UserRole.admin)
        upload = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("private.pdf", io.BytesIO(FAKE_PDF + b"X"), "application/pdf")},
            data={"title": "Private"},
            headers=auth_headers(admin_a),
        )
        doc_id = upload.json()["id"]

        # Тенант B пытается получить его
        tenant_b = await create_tenant(db, "B Corp")
        admin_b = await create_user(db, tenant_b, email="admb@test.com", role=UserRole.admin)
        response = await client.get(
            f"/api/v1/docs/documents/{doc_id}",
            headers=auth_headers(admin_b),
        )

        assert response.status_code == 404


class TestDeleteDocument:
    async def test_admin_can_delete(self, client, admin_headers, tmp_path, monkeypatch):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        upload = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("del.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"title": "To Delete"},
            headers=admin_headers,
        )
        doc_id = upload.json()["id"]

        response = await client.delete(f"/api/v1/docs/documents/{doc_id}", headers=admin_headers)
        assert response.status_code == 204

        # Проверяем что документа больше нет
        get_response = await client.get(f"/api/v1/docs/documents/{doc_id}", headers=admin_headers)
        assert get_response.status_code == 404

    async def test_regular_user_cannot_delete(
        self, client, db, admin_user, admin_headers, user_headers, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        upload = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("nd.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"title": "No Delete"},
            headers=admin_headers,
        )
        doc_id = upload.json()["id"]

        response = await client.delete(f"/api/v1/docs/documents/{doc_id}", headers=user_headers)
        assert response.status_code == 403

    async def test_cannot_delete_processing_document(
        self, client, db, admin_user, admin_headers, tmp_path, monkeypatch
    ):
        """Нельзя удалять документ пока идёт индексирование."""
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))

        from sqlalchemy import select

        from eka.db.models import Document, DocumentStatus

        upload = await client.post(
            "/api/v1/docs/documents",
            files={"file": ("proc.pdf", io.BytesIO(FAKE_PDF), "application/pdf")},
            data={"title": "Processing"},
            headers=admin_headers,
        )
        doc_id = upload.json()["id"]

        # Вручную меняем статус на processing
        from uuid import UUID

        doc = await db.scalar(select(Document).where(Document.id == UUID(doc_id)))
        doc.status = DocumentStatus.processing
        await db.flush()

        response = await client.delete(f"/api/v1/docs/documents/{doc_id}", headers=admin_headers)
        assert response.status_code == 409
