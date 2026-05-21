// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import OverviewPanel from './OverviewPanel.vue'

describe('OverviewPanel', () => {
  it('renders KPI values from canonical metric names', () => {
    const source = { page: 1, table_id: null, bbox: null, quote: null }
    const wrapper = mount(OverviewPanel, {
      props: {
        statements: {
          income_statement: [
            { name: 'revenue', value: 391035, unit: 'USD millions', period: '2024-09-28', source },
            { name: 'net_income', value: 93736, unit: 'USD millions', period: '2024-09-28', source },
          ],
          balance_sheet: [{ name: 'total_assets', value: 364980, unit: 'USD millions', source }],
          cash_flow: [{ name: 'operating_cf', value: 118254, unit: 'USD millions', source }],
        },
        signals: [],
        reportMd: '',
      },
      global: {
        stubs: {
          KpiCard: {
            props: ['title', 'value', 'unit', 'hint'],
            template: '<div class="kpi"><span>{{ title }}</span><span>{{ value }}</span><span>{{ unit }}</span><span>{{ hint }}</span></div>',
          },
          SeverityTag: true,
          EvidenceLink: true,
          ElRow: { template: '<div><slot /></div>' },
          ElCol: { template: '<div><slot /></div>' },
          ElTable: true,
          ElTableColumn: true,
          ElCard: true,
          ElEmpty: true,
        },
      },
    })

    expect(wrapper.text()).toContain('391.04K')
    expect(wrapper.text()).toContain('93.74K')
    expect(wrapper.text()).toContain('364.98K')
    expect(wrapper.text()).toContain('118.25K')
  })
})