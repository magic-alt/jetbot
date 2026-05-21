// ── API response types (mirror src/finance/schemas.py & src/schemas/models.py)

export interface SourceRef {
  page: number
  table_id?: string | null
  bbox?: [number, number, number, number] | null
  quote?: string | null
}

export interface MetricItem {
  name: string
  value: number | null
  unit?: string | null
  period?: string | null
  fx?: string | null
  source: SourceRef
  confidence?: number
}

export interface FinancialStatements {
  income_statement?: MetricItem[]
  balance_sheet?: MetricItem[]
  cash_flow?: MetricItem[]
  [k: string]: MetricItem[] | undefined
}

export interface RiskSignal {
  id: string
  category: string
  severity: 'low' | 'medium' | 'high' | string
  description: string
  evidence?: SourceRef[]
  metric_refs?: string[]
  confidence?: number
}

export interface KeyNote {
  topic: string
  summary: string
  evidence?: SourceRef[]
}

export interface DocumentMeta {
  doc_id: string
  filename: string
  company?: string | null
  period_end?: string | null
  report_type?: string | null
  language?: string | null
  created_at?: string | null
}

export interface TaskState {
  doc_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | string
  progress?: number
  current_node?: string | null
  error_message?: string | null
}

export interface DocumentListItem {
  meta: DocumentMeta
  task: TaskState | null
}

export interface TableCell {
  row: number
  col: number
  text: string
  rowspan?: number
  colspan?: number
}

export interface ExtractedTable {
  table_id: string
  page: number
  title?: string | null
  cells: TableCell[]
}

export interface PdfOperationResult {
  doc_id: string
  revision_id: string
  source: string
  output_pdf: string
  operation: 'extract' | 'delete' | 'reorder' | 'rotate'
  pages?: number[] | null
  degrees?: number | null
  page_count: number
  created_at: string
  download_url: string
}
