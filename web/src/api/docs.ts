import { buildApiUrl, http, unwrap } from './client'
import type {
  DocumentListItem,
  ExtractedTable,
  FinancialStatements,
  KeyNote,
  MetricItem,
  RiskSignal,
  SourceRef,
} from './types'

const DEFAULT_SOURCE: SourceRef = { page: 1, table_id: null, bbox: null, quote: null }

function normalizeSourceRef(raw: any): SourceRef {
  if (!raw || typeof raw !== 'object') return DEFAULT_SOURCE
  const page = Number(raw.page)
  return {
    page: Number.isFinite(page) && page > 0 ? page : 1,
    table_id: raw.table_id ?? null,
    bbox: raw.bbox ?? null,
    quote: raw.quote ?? null,
  }
}

function normalizeMetricName(name: string): string {
  return name.replace(/_/g, ' ')
}

function normalizeStatements(raw: any): FinancialStatements {
  if (!raw || typeof raw !== 'object') return {}

  const groupMap: Record<string, keyof FinancialStatements> = {
    income: 'income_statement',
    income_statement: 'income_statement',
    balance: 'balance_sheet',
    balance_sheet: 'balance_sheet',
    cashflow: 'cash_flow',
    cash_flow: 'cash_flow',
  }

  const result: FinancialStatements = {}
  for (const [key, value] of Object.entries(raw)) {
    const targetKey = groupMap[key] || key
    if (Array.isArray(value)) {
      result[targetKey] = value as MetricItem[]
      continue
    }
    if (!value || typeof value !== 'object') continue

    const rows: MetricItem[] = []
    const lineItems = Array.isArray((value as any).line_items) ? (value as any).line_items : []
    for (const item of lineItems) {
      rows.push({
        name: item.name_norm || item.name_raw || 'unknown',
        value: item.value_current ?? item.value ?? null,
        unit: item.unit ?? null,
        period: (value as any).period_end ?? (value as any).period_start ?? null,
        fx: item.currency ?? null,
        source: normalizeSourceRef(item.source ?? item.source_refs?.[0]),
        confidence: item.confidence ?? item.source_refs?.[0]?.confidence ?? (value as any).extraction_confidence ?? undefined,
      })
    }

    const totals = (value as any).totals
    if (totals && typeof totals === 'object') {
      const source = lineItems[0]?.source_refs?.[0]
      for (const [name, total] of Object.entries(totals)) {
        rows.push({
          name: normalizeMetricName(name),
          value: typeof total === 'number' ? total : null,
          unit: null,
          period: (value as any).period_end ?? (value as any).period_start ?? null,
          fx: null,
          source: normalizeSourceRef(source),
          confidence: (value as any).extraction_confidence ?? undefined,
        })
      }
    }

    result[targetKey] = rows
  }
  return result
}

function normalizeSignals(raw: any): RiskSignal[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item, index) => ({
    id: item.id || item.signal_id || `signal-${index + 1}`,
    category: item.category || 'other',
    severity: item.severity || 'low',
    description: item.description || item.title || 'No description',
    evidence: Array.isArray(item.evidence) ? item.evidence.map(normalizeSourceRef) : [],
    metric_refs: Array.isArray(item.metric_refs)
      ? item.metric_refs
      : item.metrics && typeof item.metrics === 'object'
        ? Object.entries(item.metrics)
            .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '')
            .map(([name, value]) => `${name}: ${value}`)
        : [],
    confidence: item.confidence ?? item.evidence?.[0]?.confidence ?? undefined,
  }))
}

function normalizeNotes(raw: any): KeyNote[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item) => ({
    topic: item.topic || item.note_type || 'other',
    summary: item.summary || item.description || 'No notes extracted.',
    evidence: Array.isArray(item.evidence)
      ? item.evidence.map(normalizeSourceRef)
      : Array.isArray(item.source_refs)
        ? item.source_refs.map(normalizeSourceRef)
        : [],
  }))
}

function normalizeTables(raw: any): ExtractedTable[] {
  if (Array.isArray(raw)) return raw as ExtractedTable[]
  if (Array.isArray(raw?.tables)) return raw.tables as ExtractedTable[]
  return []
}

export const docsApi = {
  list(limit = 50, offset = 0) {
    return unwrap<{ items: DocumentListItem[]; total: number; limit: number; offset: number }>(
      http.get('/v1/documents', { params: { limit, offset } }),
    )
  },
  analyze(docId: string) {
    return unwrap<{ doc_id: string; status: string; progress?: number; current_node?: string | null }>(
      http.post(`/v1/documents/${docId}/analyze`),
    )
  },
  /** Returns { meta, task }. */
  detail(docId: string) {
    return unwrap<DocumentListItem>(http.get(`/v1/documents/${docId}`))
  },
  statements(docId: string) {
    return unwrap<any>(http.get(`/v1/documents/${docId}/statements`)).then(normalizeStatements)
  },
  riskSignals(docId: string) {
    return unwrap<any>(http.get(`/v1/documents/${docId}/risk-signals`)).then(normalizeSignals)
  },
  notes(docId: string) {
    return unwrap<any>(http.get(`/v1/documents/${docId}/notes`)).then(normalizeNotes)
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
    return unwrap<any>(http.get(`/v1/documents/${docId}/tables`)).then(normalizeTables)
  },
  pdfUrl(docId: string) {
    // Note: the iframe cannot send the X-API-Key header. For deployments
    // with auth enabled, place the SPA + API behind a reverse proxy that
    // injects the header, or disable auth for this read-only route.
    return buildApiUrl(`/v1/documents/${docId}/pdf`)
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
