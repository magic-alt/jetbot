from __future__ import annotations

from pathlib import Path

from src.agent.graph import build_graph
from src.agent.state import AgentState
from src.schemas.models import DocumentMeta, Page


def test_pipeline_with_fake_pages(tmp_path: Path):
    meta = DocumentMeta(doc_id="test-doc", filename="fake.pdf")
    pages = [Page(page_number=1, text="资产负债表\n资产总计 100\n负债合计 40\n所有者权益合计 60", images=[])]
    state = AgentState(
        doc_meta=meta,
        pdf_path=None,
        data_dir=str(tmp_path),
        debug={"fake_pages": pages},
    )
    graph = build_graph()
    graph.invoke(state.model_dump())

    report_path = tmp_path / "test-doc" / "report" / "trader_report.md"
    assert report_path.exists()
