from __future__ import annotations

from src.schemas.models import Chunk, SourceRef, Table, TableCell
from src.storage.vector_index import LocalVectorIndex


def test_local_vector_index_search():
    source = SourceRef(ref_type="page_text", page=1, table_id=None, quote="revenue", confidence=0.8)
    chunk = Chunk(
        chunk_id="c1",
        page_start=1,
        page_end=1,
        section="Financials",
        text="Revenue increased and operating cash flow improved.",
        source_refs=[source],
    )
    table = Table(
        table_id="p1_t1",
        page=1,
        title="Income Statement",
        cells=[
            TableCell(row=0, col=0, text="Revenue"),
            TableCell(row=0, col=1, text="100"),
        ],
        n_rows=1,
        n_cols=2,
        source_refs=[SourceRef(ref_type="table", page=1, table_id="p1_t1", quote=None, confidence=0.7)],
    )

    index = LocalVectorIndex.from_chunks_and_tables([chunk], [table])
    docs = index.search("revenue cash flow", k=3)

    assert index.size >= 2
    assert docs
    assert any(doc.metadata.get("source_type") == "chunk" for doc in docs)
