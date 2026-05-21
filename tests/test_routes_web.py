"""Tests for the web-UI support endpoints (list / tables / pdf / pages)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _make_doc(base: Path, doc_id: str, *, with_pdf: bool = True, with_tables: bool = True) -> None:
    d = base / doc_id
    (d / "extracted").mkdir(parents=True, exist_ok=True)
    (d / "report").mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(
        '{"doc_id":"%s","filename":"r.pdf","company":"ACME","period_end":null,'
        '"report_type":null,"language":null,"created_at":"2026-05-21T00:00:00Z"}' % doc_id,
        encoding="utf-8",
    )
    if with_pdf:
        (d / "raw.pdf").write_bytes(b"%PDF-1.4\n%fake test pdf\n%%EOF\n")
    if with_tables:
        (d / "extracted" / "tables.json").write_text(
            '[{"table_id":"p1_t1","page":1,"title":null,'
            '"cells":[{"row":0,"col":0,"text":"A"}]}]',
            encoding="utf-8",
        )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_KEYS", "")  # no auth

    # Reload routes module so the module-level `store` picks up the new cwd.
    import importlib

    import src.api.main as main_mod
    import src.api.routes as routes_mod

    importlib.reload(routes_mod)
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_list_empty(client: TestClient) -> None:
    r = client.get("/v1/documents")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"] == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_list_returns_docs_sorted_desc(client: TestClient, tmp_path: Path) -> None:
    base = tmp_path / "data"
    base.mkdir(exist_ok=True)
    # Two docs with different created_at timestamps embedded in meta
    (base / "aaa111").mkdir()
    (base / "aaa111" / "meta.json").write_text(
        '{"doc_id":"aaa111","filename":"a.pdf","company":"A","period_end":null,'
        '"report_type":null,"language":null,"created_at":"2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )
    (base / "bbb222").mkdir()
    (base / "bbb222" / "meta.json").write_text(
        '{"doc_id":"bbb222","filename":"b.pdf","company":"B","period_end":null,'
        '"report_type":null,"language":null,"created_at":"2026-05-01T00:00:00Z"}',
        encoding="utf-8",
    )

    r = client.get("/v1/documents")
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    assert [it["meta"]["doc_id"] for it in items] == ["bbb222", "aaa111"]


def test_list_pagination(client: TestClient, tmp_path: Path) -> None:
    base = tmp_path / "data"
    base.mkdir(exist_ok=True)
    for i in range(5):
        _make_doc(base, f"doc{i:03d}")

    r = client.get("/v1/documents?limit=2&offset=1")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert len(data["items"]) == 2


def test_upload_endpoint_creates_doc_layout(client: TestClient, tmp_path: Path) -> None:
    r = client.post(
        "/v1/documents",
        files={"file": ("demo.pdf", b"%PDF-1.4\n%fake upload\n%%EOF\n", "application/pdf")},
        data={"language": "en"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "queued"

    doc_id = body["data"]["doc_id"]
    doc_dir = tmp_path / "data" / doc_id
    assert (doc_dir / "raw.pdf").exists()
    assert (doc_dir / "meta.json").exists()


def test_delete_endpoint_removes_doc_and_task(client: TestClient, tmp_path: Path) -> None:
    upload = client.post(
        "/v1/documents",
        files={"file": ("demo.pdf", b"%PDF-1.4\n%fake upload\n%%EOF\n", "application/pdf")},
    )
    doc_id = upload.json()["data"]["doc_id"]

    r = client.delete(f"/v1/documents/{doc_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"] == {"doc_id": doc_id, "deleted": True}
    assert not (tmp_path / "data" / doc_id).exists()

    assert client.get(f"/v1/documents/{doc_id}").status_code == 404
    listed = client.get("/v1/documents").json()["data"]
    assert listed["total"] == 0


def test_delete_missing_returns_404(client: TestClient) -> None:
    r = client.delete("/v1/documents/missing-doc")
    assert r.status_code == 404


def test_tables_endpoint(client: TestClient, tmp_path: Path) -> None:
    _make_doc(tmp_path / "data", "abc123")
    r = client.get("/v1/documents/abc123/tables")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"][0]["table_id"] == "p1_t1"


def test_tables_missing_returns_404(client: TestClient, tmp_path: Path) -> None:
    _make_doc(tmp_path / "data", "abc123", with_tables=False)
    r = client.get("/v1/documents/abc123/tables")
    assert r.status_code == 404


def test_pdf_endpoint_streams_bytes(client: TestClient, tmp_path: Path) -> None:
    _make_doc(tmp_path / "data", "abc123")
    r = client.get("/v1/documents/abc123/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert "inline" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")


def test_pdf_missing_returns_404(client: TestClient, tmp_path: Path) -> None:
    _make_doc(tmp_path / "data", "abc123", with_pdf=False)
    r = client.get("/v1/documents/abc123/pdf")
    assert r.status_code == 404


def test_other_routes_still_deny_iframe(client: TestClient) -> None:
    """SAMEORIGIN on /pdf must not leak into the default DENY policy."""
    r = client.get("/health")
    assert r.headers.get("x-frame-options") == "DENY"
