// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentInsightsPanel from './AgentInsightsPanel.vue'

describe('AgentInsightsPanel', () => {
  it('renders capabilities, findings, runs, and limitations', () => {
    const wrapper = mount(AgentInsightsPanel, {
      props: {
        capabilities: [
          {
            capability_id: 'deep_analysis',
            name: 'Deep financial analysis',
            description: 'Analyze context.',
            enabled: true,
            provider: 'mock',
            inputs: ['analysis_context'],
            outputs: ['deep_analysis'],
          },
        ],
        deepAnalysis: {
          doc_id: 'doc-1',
          provider: 'mock',
          model: 'mock',
          summary: 'Deep summary.',
          findings: [
            {
              finding_id: 'finding-1',
              category: 'cash_quality',
              title: 'Cash quality watch',
              severity: 'medium',
              summary: 'Cash conversion needs review.',
              evidence: [{ page: 2, quote: 'cash flow', confidence: 0.6 }],
              confidence: 0.6,
            },
          ],
          limitations: ['Mock output.'],
          invocations: [],
        },
        agentRuns: [
          {
            run_id: 'run-1',
            doc_id: 'doc-1',
            node_name: 'run_deep_analysis',
            provider: 'mock',
            model: 'mock',
            status: 'succeeded',
            elapsed_ms: 12,
          },
        ],
      },
      global: {
        stubs: {
          EvidenceLink: { props: ['source'], template: '<button>page {{ source.page }}</button>' },
          SeverityTag: { props: ['severity'], template: '<span>{{ severity }}</span>' },
          ElAlert: { template: '<div><slot name="title" /></div>' },
          ElCollapse: { template: '<div><slot /></div>' },
          ElCollapseItem: { template: '<div><slot name="title" /><slot /></div>' },
          ElEmpty: { props: ['description'], template: '<div>{{ description }}</div>' },
          ElTable: { props: ['data'], template: '<div><slot /></div>' },
          ElTableColumn: { template: '<div />' },
          ElTag: { template: '<span><slot /></span>' },
        },
      },
    })

    expect(wrapper.text()).toContain('Deep financial analysis')
    expect(wrapper.text()).toContain('Deep summary.')
    expect(wrapper.text()).toContain('Cash quality watch')
    expect(wrapper.text()).toContain('Mock output.')
  })
})