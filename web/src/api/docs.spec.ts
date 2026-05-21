import { describe, expect, it } from 'vitest'
import { normalizeStatements } from './docs'

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