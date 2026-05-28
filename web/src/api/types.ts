// ── API response types (mirror src/finance/schemas.py & src/schemas/models.py)

export interface SourceRef {
  ref_type?: 'page_text' | 'table' | 'image' | string
  page: number
  table_id?: string | null
  row?: number | null
  col?: number | null
  bbox?: [number, number, number, number] | null
  quote?: string | null
  confidence?: number
  engine?: string | null
  artifact_path?: string | null
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

export interface FinancialFact {
  fact_id: string
  doc_id: string
  company?: string | null
  ticker?: string | null
  cik?: string | null
  filing_type?: string | null
  statement_type: 'income' | 'balance' | 'cashflow' | 'note' | 'other' | string
  concept: string
  label: string
  raw_label?: string | null
  value?: number | null
  unit?: string | null
  scale?: number | null
  currency?: string | null
  period_start?: string | null
  period_end?: string | null
  period_type?: 'instant' | 'duration' | 'unknown' | string
  source_refs: SourceRef[]
  confidence: number
  extraction_engine?: string | null
  metadata?: Record<string, unknown>
}

export interface Correction {
  correction_id: string
  doc_id: string
  fact_id: string
  field_name: string
  old_value?: unknown
  new_value?: unknown
  actor: string
  reason?: string | null
  source_refs: SourceRef[]
  created_at?: string | null
}

export interface CorrectionCreateRequest {
  field_name: string
  new_value: unknown
  old_value?: unknown
  actor?: string
  reason?: string | null
  source_refs?: SourceRef[]
}

export interface FactValidationIssue {
  code: string
  severity: 'low' | 'medium' | 'high' | string
  message: string
  fact_ids?: string[]
  concepts?: string[]
  statement_type?: string | null
  metadata?: Record<string, unknown>
}

export interface FactValidationResult {
  issues: FactValidationIssue[]
  checks: Record<string, boolean | number | string>
  metrics: Record<string, number | string>
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
  ticker?: string | null
  cik?: string | null
  filing_type?: string | null
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
  bbox?: [number, number, number, number] | null
  confidence?: number | null
  engine?: string | null
}

export interface ExtractedTable {
  table_id: string
  page: number
  title?: string | null
  n_rows?: number | null
  n_cols?: number | null
  raw_markdown?: string | null
  cells: TableCell[]
}

export interface ExtractedPage {
  page_number: number
  text: string
  images?: string[]
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

export interface AgentCapability {
  capability_id: string
  name: string
  description: string
  enabled: boolean
  provider?: string | null
  inputs: string[]
  outputs: string[]
}

export interface ModelInvocation {
  provider: string
  model: string
  task: string
  status: 'succeeded' | 'failed' | 'skipped' | string
  elapsed_ms?: number | null
  error?: string | null
  metadata?: Record<string, unknown>
  created_at?: string | null
}

export interface AgentRun {
  run_id: string
  doc_id: string
  node_name: string
  provider: string
  model: string
  status: 'succeeded' | 'failed' | 'skipped' | string
  started_at?: string | null
  completed_at?: string | null
  elapsed_ms?: number | null
  error?: string | null
  metadata?: Record<string, unknown>
}

export interface AnalysisFinding {
  finding_id: string
  category: string
  title: string
  severity: 'low' | 'medium' | 'high' | string
  summary: string
  detail?: string | null
  metrics?: Record<string, number | string>
  evidence?: SourceRef[]
  confidence?: number
}

export interface DeepAnalysisResult {
  doc_id: string
  provider: string
  model: string
  summary: string
  findings: AnalysisFinding[]
  limitations: string[]
  invocations: ModelInvocation[]
  created_at?: string | null
}
