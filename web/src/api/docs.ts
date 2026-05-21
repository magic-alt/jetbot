import { http, unwrap } from './client'
import type {
  DocumentListItem,
  ExtractedTable,
  FinancialStatements,
  KeyNote,
  RiskSignal,
} from './types'

export const docsApi = {
  list(limit = 50, offset = 0) {
    return unwrap<{ items: DocumentListItem[]; total: number; limit: number; offset: number }>(
      http.get('/v1/documents', { params: { limit, offset } }),
    )
  },
  /** Returns { meta, task }. */
  detail(docId: string) {
    return unwrap<DocumentListItem>(http.get(`/v1/documents/${docId}`))
  },
  statements(docId: string) {
    return unwrap<FinancialStatements>(http.get(`/v1/documents/${docId}/statements`))
  },
  riskSignals(docId: string) {
    return unwrap<RiskSignal[]>(http.get(`/v1/documents/${docId}/risk-signals`))
  },
  notes(docId: string) {
    return unwrap<KeyNote[]>(http.get(`/v1/documents/${docId}/notes`))
  },
  reportJson(docId: string) {
    return unwrap<any>(http.get(`/v1/documents/${docId}/report`))
  },
  reportMd(docId: string) {
    return http
      .get(`/v1/documents/${docId}/report.md`, { responseType: 'text' })
      .then((r) => r.data as string)
  },
  tables(docId: string) {
    return unwrap<ExtractedTable[]>(http.get(`/v1/documents/${docId}/tables`))
  },
  pdfUrl(docId: string) {
    // Note: the iframe cannot send the X-API-Key header. For deployments
    // with auth enabled, place the SPA + API behind a reverse proxy that
    // injects the header, or disable auth for this read-only route.
    return `/v1/documents/${docId}/pdf`
  },
  upload(file: File, opts: { language?: string; ocr?: boolean } = {}) {
    const form = new FormData()
    form.append('file', file)
    if (opts.language) form.append('language', opts.language)
    if (opts.ocr !== undefined) form.append('ocr', String(opts.ocr))
    return unwrap<{ doc_id: string; status: string }>(
      http.post('/v1/documents', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }),
    )
  },
}
