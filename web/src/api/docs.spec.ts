import { describe, expect, it } from 'vitest'
import { normalizeDeepAnalysis, normalizeStatements } from './docs'

describe('normalizeStatements', () => {
  it('normalizes backend statement objects and canonical totals', () => {
    const result = normalizeStatements({
      income: {
        period_end: '2024-09-28',
        extraction_confidence: 0.7,
        line_items: [
          {
            name_raw: 'Total net sales',
            name_norm: 'revenue',
            value_current: 391035,
            unit: 'USD millions',
            currency: 'USD',
            source_refs: [{ page: 1, quote: 'Total net sales 391,035', confidence: 0.65 }],
          },
        ],
        totals: { net_income: 93736 },
      },
      balance: {
        line_items: [],
        totals: { total_assets: 364980 },
      },
      cashflow: {
        line_items: [],
        totals: { operating_cf: 118254 },
      },
    })

    expect(result.income_statement?.[0]).toMatchObject({
      name: 'revenue',
      value: 391035,
      unit: 'USD millions',
      period: '2024-09-28',
      fx: 'USD',
    })
    expect(result.income_statement?.some((item) => item.name === 'net income' && item.value === 93736)).toBe(true)
    expect(result.balance_sheet?.some((item) => item.name === 'total assets' && item.value === 364980)).toBe(true)
    expect(result.cash_flow?.some((item) => item.name === 'operating cf' && item.value === 118254)).toBe(true)
  })
})

describe('normalizeDeepAnalysis', () => {
  it('normalizes findings and source confidence', () => {
    const result = normalizeDeepAnalysis({
      doc_id: 'doc-1',
      provider: 'mock',
      model: 'mock',
      summary: 'summary',
      findings: [
        {
          title: 'Cash quality',
          severity: 'medium',
          summary: 'Operating cashflow trails earnings.',
          evidence: [{ page: 3, quote: 'Cash generated', confidence: 0.75 }],
          confidence: 0.7,
        },
      ],
      limitations: ['limited'],
      invocations: [],
    })

    expect(result?.findings[0]).toMatchObject({
      title: 'Cash quality',
      severity: 'medium',
      confidence: 0.7,
    })
    expect(result?.findings[0].evidence?.[0]).toMatchObject({ page: 3, confidence: 0.75 })
  })
})