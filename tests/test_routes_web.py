"""Tests for the web-UI support endpoints (list / tables / pdf / pages)."""

from __future__ import annotations

import json
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


def test_list_enriches_missing_metadata_from_pages(client: TestClient, tmp_path: Path) -> None:
    base = tmp_path / "data"
    _make_doc(base, "abc123")
    meta_path = base / "abc123" / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "doc_id": "abc123",
                "filename": "FY24_Q4_Consolidated_Financial_Statements.pdf",
                "company": None,
                "period_end": None,
                "report_type": None,
                "language": None,
                "created_at": "2026-05-21T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (base / "abc123" / "extracted" / "pages.json").write_text(
        json.dumps(
            [
                {
                    "page_number": 1,
                    "text": "Apple Inc.\nCONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS\nSeptember 28,\n2024",
                    "images": [],
                }
            ]
        ),
        encoding="utf-8",
    )

    r = client.get("/v1/documents")

    assert r.status_code == 200
    meta = r.json()["data"]["items"][0]["meta"]
    assert meta["company"] == "Apple Inc."
    assert meta["report_type"] == "Condensed Consolidated Financial Statements"
    assert meta["period_end"] == "2024-09-28"
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert saved["company"] == "Apple Inc."


def test_upload_endpoint_creates_doc_layout(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.routes as routes_mod

    def fake_start_analysis(meta: object, pdf_path: Path, background_tasks: object) -> dict[str, object]:
        return {
            "doc_id": getattr(meta, "doc_id"),
            "status": "running",
            "progress": 5,
            "current_node": None,
            "error_message": None,
        }

    monkeypatch.setattr(routes_mod, "_start_analysis", fake_start_analysis)

    r = client.post(
        "/v1/documents",
        files={"file": ("demo.pdf", b"%PDF-1.4\n%fake upload\n%%EOF\n", "application/pdf")},
        data={"language": "en"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "running"

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


def test_agent_capabilities_endpoint(client: TestClient) -> None:
    r = client.get("/v1/agent/capabilities")
    assert r.status_code == 200
    data = r.json()["data"]
    assert any(item["capability_id"] == "deep_analysis" for item in data)


def test_deep_analysis_and_agent_runs_endpoints(client: TestClient, tmp_path: Path) -> None:
    _make_doc(tmp_path / "data", "abc123")
    extracted = tmp_path / "data" / "abc123" / "extracted"
    (extracted / "deep_analysis.json").write_text(
        '{"doc_id":"abc123","provider":"mock","model":"mock","summary":"ok",'
        '"findings":[],"limitations":[],"invocations":[]}',
        encoding="utf-8",
    )
    (extracted / "agent_runs.json").write_text(
        '[{"run_id":"run-1","doc_id":"abc123","node_name":"run_deep_analysis",'
        '"provider":"mock","model":"mock","status":"succeeded"}]',
        encoding="utf-8",
    )

    deep = client.get("/v1/documents/abc123/deep-analysis")
    runs = client.get("/v1/documents/abc123/agent-runs")

    assert deep.status_code == 200
    assert deep.json()["data"]["summary"] == "ok"
    assert runs.status_code == 200
    assert runs.json()["data"][0]["run_id"] == "run-1"


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


def test_pdf_page_image_endpoint_renders_with_pdfium(client: TestClient, tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    fitz = pytest.importorskip("fitz")

    base = tmp_path / "data"
    _make_doc(base, "abc123")
    raw_pdf = base / "abc123" / "raw.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=240)
    page.insert_text((36, 72), "page one", fontsize=12)
    doc.save(str(raw_pdf))
    doc.close()

    r = client.get("/v1/documents/abc123/pages/1/image")

    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-pdf-engine"] == "pdfium"
    assert r.content.startswith(b"\x89PNG")
    assert (base / "abc123" / "pages" / "pdfium_preview" / "page_0001.png").exists()


def test_pdf_missing_returns_404(client: TestClient, tmp_path: Path) -> None:
    _make_doc(tmp_path / "data", "abc123", with_pdf=False)
    r = client.get("/v1/documents/abc123/pdf")
    assert r.status_code == 404


def test_pdf_operation_creates_derived_pdf(client: TestClient, tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    import fitz

    base = tmp_path / "data"
    _make_doc(base, "abc123")
    raw_pdf = base / "abc123" / "raw.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=240)
    page.insert_text((36, 72), "page one", fontsize=12)
    doc.new_page(width=300, height=240)
    doc.save(str(raw_pdf))
    doc.close()

    r = client.post(
        "/v1/documents/abc123/pdf/operations",
        json={"operation": "extract", "pages": [1]},
    )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["operation"] == "extract"
    assert data["page_count"] == 1
    assert (base / "abc123" / data["output_pdf"]).exists()
    assert (base / "abc123" / "derived" / f"{data['revision_id']}.json").exists()

    download = client.get(f"/v1/documents/abc123/pdf/derived/{data['revision_id']}")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")


def test_pdf_operation_invalid_page_returns_400(client: TestClient, tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    import fitz

    base = tmp_path / "data"
    _make_doc(base, "abc123")
    raw_pdf = base / "abc123" / "raw.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=240)
    doc.save(str(raw_pdf))
    doc.close()

    r = client.post(
        "/v1/documents/abc123/pdf/operations",
        json={"operation": "extract", "pages": [99]},
    )

    assert r.status_code == 400


def test_other_routes_still_deny_iframe(client: TestClient) -> None:
    """SAMEORIGIN on /pdf must not leak into the default DENY policy."""
    r = client.get("/health")
    assert r.headers.get("x-frame-options") == "DENY"
