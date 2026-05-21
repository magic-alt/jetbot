# PDF Engine Evaluation: Stirling-PDF vs PDFium

## Summary

This repository is a financial-report PDF analysis agent. Its highest-value PDF
capability is not generic editing; it is reliable extraction, source evidence,
and review of financial statements, notes, and risk signals.

Implemented direction:

- Keep the current PyMuPDF + pdfplumber pipeline as the default MVP path.
- Add PDFium, via `pypdfium2`, as an optional low-level PDF engine for rendering,
  document inspection, extraction, and page-level derived-PDF operations.
- Do not place Stirling-PDF in the core analysis path. Treat it as a possible
  external sidecar only if the product later needs a broad PDF toolbox.
- For "edit PDF" in this product, prioritize page-level operations and
  annotations over direct original-text rewriting.

## Current Architecture Fit

Current PDF responsibilities are already separated under `src/pdf/`:

- `engine.py`: PDF engine abstraction. PyMuPDF remains the default, while
  PDFium can be enabled with `PDF_ENGINE=pdfium`.
- `extractor.py`: configured-engine text extraction, PDF header validation, scanned-page
  detection, and optional debug rendering.
- `tables.py`: pdfplumber table extraction into the repository's `Table`
  schema.
- `render.py`: PyMuPDF page rendering for OCR and preview images.
- `ocr.py`: PaddleOCR/Tesseract OCR abstraction.

The agent workflow consumes these outputs through LangGraph nodes in
`src/agent/nodes.py`:

- `ingest_pdf` creates `Page` records and OCR text.
- `extract_tables` creates `Table` records.
- downstream nodes create financial statements, notes, risk signals, and reports
  with `SourceRef` evidence.

The web UI currently displays the original PDF through `PdfViewer.vue`, which
loads `/v1/documents/{doc_id}/pdf` into a browser iframe. This is sufficient for
basic review but weak for application-owned page navigation, highlights, and
annotations.

## Option A: Stirling-PDF

Stirling-PDF is a self-hosted PDF application and API with a large tool surface:
merge, split, rotate, remove pages, OCR, compress, convert, annotate, add text,
add images, compare, sanitize, metadata editing, and more.

### Strengths

- Broad toolbox coverage with many features already implemented.
- Useful for user-facing utility operations outside the analysis workflow:
  compression, page extraction, conversion, searchable OCR PDFs, and repair.
- Dockerized deployment model is straightforward when the product already runs
  multiple services.
- Official docs describe REST API usage for OCR and conversion endpoints.

### Weaknesses

- It is an external Java/Docker service, not a Python library that naturally
  composes with this codebase's `src/pdf/` modules.
- It does not directly produce the repository's evidence model:
  `SourceRef(page, table_id, quote, confidence)`.
- Routing uploaded financial reports through another service increases
  operational and security review surface.
- It would duplicate some existing capabilities: OCR, rendering, upload
  validation, and storage lifecycle.
- Its broad feature set is larger than the MVP requirement of parsing,
  reviewing, and page-level PDF changes.

### Best Use

Keep Stirling-PDF out of the LangGraph analysis pipeline. If needed later,
integrate it as a separately configured sidecar for explicit user-triggered
tools:

- `POST /v1/documents/{doc_id}/tools/compress`
- `POST /v1/documents/{doc_id}/tools/ocr-searchable`
- `POST /v1/documents/{doc_id}/tools/split`
- `POST /v1/documents/{doc_id}/tools/merge`

The sidecar client should be feature-flagged, isolated from analysis state, and
write derived PDFs as new artifacts instead of replacing `raw.pdf` in place.

## Option B: PDFium / pypdfium2

PDFium is the PDF engine used by Chromium. `pypdfium2` exposes PDFium to Python
with support-model helpers plus access to the raw PDFium API.

### Strengths

- Fits the Python backend better than a separate PDF service.
- Good candidate for low-level rendering, page inspection, document metadata,
  text access, and future preview fallback images.
- More compatible with this repository's modular `src/pdf/` architecture.
- Licensing is generally easier to reason about than strong copyleft PDF
  renderers, though the exact binary distribution must still be reviewed.
- Can be introduced as an optional backend without disrupting current tests.

### Weaknesses

- It is not a high-level financial table extraction solution.
- It should not replace pdfplumber for table extraction without a dedicated
  quality benchmark.
- pypdfium2 helper APIs cover a subset of PDFium and require careful memory
  management.
- Expensive PDFium tasks should be parallelized with processes rather than
  threads, which matters for worker design.
- Direct original-text editing is still complex and should not be promised as an
  MVP feature.

### Best Use

Introduce PDFium only behind a small engine abstraction. Keep PyMuPDF as the
default implementation until a benchmark proves a better outcome.

Candidate interface:

```python
class PdfEngine(Protocol):
    def page_count(self, pdf_path: str) -> int: ...
    def metadata(self, pdf_path: str) -> dict[str, str | int | float | None]: ...
    def extract_text(self, pdf_path: str, page_index: int) -> str: ...
    def render_page(
        self,
        pdf_path: str,
        page_number: int,
        out_dir: str,
        *,
        dpi: int = 200,
    ) -> str: ...
```

Do not include table extraction or PDF editing in this first abstraction. Those
are separate product capabilities with different acceptance criteria.

## Display And Editing Recommendation

### Display

Replace the iframe-only viewer with an application-owned viewer when product
work resumes. PDF.js or an equivalent viewer layer is the best fit for:

- reliable page navigation from `SourceRef.page`;
- highlights based on future bounding boxes;
- search within the PDF;
- annotation overlays;
- side-by-side extracted evidence review.

Backend PDFium can still be useful for thumbnails or server-rendered fallback
images, but it should not be the first choice for interactive web viewing.

### Page-Level Editing

For the confirmed MVP editing scope, implement page-level and annotation
operations before original-text rewriting:

- rotate pages;
- delete pages;
- reorder pages;
- split/extract pages;
- merge PDFs;
- add watermark or page numbers;
- add highlights, notes, rectangles, and simple text/image annotations.

The current backend implementation covers extract, delete, reorder, rotate, and
merge at the `src/pdf/operations.py` level. The API exposes extract, delete,
reorder, and rotate through:

- `POST /v1/documents/{doc_id}/pdf/operations`
- `GET /v1/documents/{doc_id}/pdf/derived/{revision_id}`

These operations can be implemented with PyMuPDF and/or front-end PDF libraries
while preserving a clear audit trail. Store edited PDFs as derived artifacts:

```text
data/{doc_id}/
  raw.pdf
  derived/
    edited-{revision_id}.pdf
    manifest-{revision_id}.json
```

The manifest should record operation type, target pages, actor if available,
timestamp, source `doc_id`, source revision, and output artifact path.

### Original Text Editing

Do not include direct PDF text replacement in MVP. Real-world PDFs often encode
text as positioned glyph runs, subset fonts, XObjects, scanned images, or mixed
content streams. Replacing original text while preserving layout is materially
harder than page-level edits and can damage the evidence chain.

If required later, treat original-text editing as a separate research track with
explicit constraints and a sample corpus.

## Decision Matrix

| Criterion | Stirling-PDF | PDFium / pypdfium2 |
| --- | --- | --- |
| Fit with current Python modules | Low to medium; service boundary | High; library-style backend |
| Fit with LangGraph analysis path | Low | Medium to high |
| SourceRef evidence compatibility | Weak without custom mapping | Better, but still needs bbox work |
| Table extraction improvement | Low for current schemas | Low until benchmarked |
| Rendering fidelity | Good through its stack | Strong PDF engine candidate |
| Web viewer ownership | It has its own UI | Backend only; pair with PDF.js |
| Page-level editing | Strong toolbox | Possible, but not the main reason |
| Original text editing | Available in tooling, still product-risky | Low-level and complex |
| Deployment cost | Higher: extra Docker/Java service | Lower: Python dependency plus binary wheel |
| Operational risk | Higher: external service, file handoff | Medium: native library, memory handling |
| Best role | Optional sidecar toolbox | Optional backend engine |

## Recommended Roadmap

1. Document this decision and keep the production path unchanged.
2. Add a PDFium PoC only if we need evidence that rendering or text extraction
   is better than PyMuPDF on real financial PDFs.
3. Add a web viewer PoC before backend editing work, because evidence review
   depends on controlled page navigation and highlights.
4. Implement page-level editing as derived artifacts with operation manifests.
5. Revisit Stirling-PDF only for broad utility features that are explicitly
   outside the agent analysis path.

## PoC Tasks

### PDFium Backend PoC

- Add optional dependency group, for example `pdfium = ["pypdfium2>=4"]`.
- Implement `PdfiumEngine` in a new module under `src/pdf/`.
- Mirror existing `render_page` behavior for one page at 72 DPI and 200 DPI.
- Compare output image dimensions and basic text extraction on 3-5 real
  financial PDFs.
- Keep PyMuPDF as default.

Acceptance criteria:

- Existing tests continue to pass without installing PDFium.
- PDFium tests are skipped when `pypdfium2` is unavailable.
- Output artifacts are written to the same `pages/` layout as current rendering.

### Viewer PoC

- Replace iframe-only preview with an app-owned PDF viewer component.
- Preserve lazy loading so the document list does not fetch PDFs automatically.
- Support `jumpToPage(page)` from tables, statements, notes, and risk signals.
- Add a visual page indicator and basic search.

Acceptance criteria:

- Existing document-list e2e behavior remains unchanged.
- Clicking evidence still navigates to the expected page.
- The viewer works for both desktop split layout and mobile stacked layout.

### Page-Level Editing PoC

- Add backend endpoints that produce derived PDFs, not in-place mutations:
  - rotate selected pages;
  - delete selected pages;
  - reorder pages;
  - export selected page range.
- Store revision manifests in `derived/`.
- Keep analysis results tied to the original `raw.pdf` unless the user
  explicitly runs analysis on a derived revision.

Acceptance criteria:

- Invalid page numbers return 400.
- Original `raw.pdf` is never overwritten.
- Derived artifacts can be downloaded and previewed.
- Tests cover manifest generation and path safety.

### Stirling Sidecar Smoke Test

- Add only a non-production spike script or ADR appendix first.
- Exercise one endpoint, such as OCR searchable PDF or compression, against a
  locally running Stirling container.
- Record file lifecycle, timeout behavior, error envelope, and deployment
  requirements.

Acceptance criteria:

- No production API route depends on Stirling.
- The spike documents exact configuration and failure behavior.

## Testing Strategy

For this research-only branch:

```powershell
python -m pytest tests/test_render.py tests/test_routes_web.py
```

For a later implementation branch:

```powershell
python -m pytest
bash scripts/local_ci.sh
```

Additional tests should be added only when PoC code is introduced:

- PDFium rendering tests with optional skip.
- API tests for derived PDF revision endpoints.
- Frontend unit/e2e tests for viewer page navigation and lazy loading.
- Path traversal and invalid page-range tests.

## Sources

- Stirling-PDF documentation: https://docs.stirlingpdf.com/
- Stirling-PDF OCR documentation: https://docs.stirlingpdf.com/Functionality/OCR/
- Stirling-PDF Docker Hub overview: https://hub.docker.com/r/stirlingtools/stirling-pdf
- pypdfium2 documentation: https://pypdfium2.readthedocs.io/en/stable/
- pypdfium2 Python API documentation:
  https://pypdfium2-team.github.io/pypdfium2/python_api.html
- pypdfium2 licensing notes:
  https://pypdfium2-team.github.io/pypdfium2/readme.html#licensing
- PDFium license:
  https://pdfium.googlesource.com/pdfium.git/+/refs/heads/chromium/4547/LICENSE
