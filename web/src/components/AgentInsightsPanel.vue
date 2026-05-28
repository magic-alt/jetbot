<script setup lang="ts">
import { computed } from 'vue'
import type { AgentCapability, AgentRun, DeepAnalysisResult, SourceRef } from '@/api/types'
import EvidenceLink from './EvidenceLink.vue'
import SeverityTag from './SeverityTag.vue'

const props = defineProps<{
  deepAnalysis: DeepAnalysisResult | null
  agentRuns: AgentRun[]
  capabilities: AgentCapability[]
}>()
const emit = defineEmits<{ (e: 'jumpPage', source: SourceRef): void }>()

const enabledCapabilities = computed(() => props.capabilities.filter((capability) => capability.enabled))
const disabledCapabilities = computed(() => props.capabilities.filter((capability) => !capability.enabled))

function statusType(status: string): 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'skipped') return 'info'
  return 'warning'
}
</script>

<template>
  <div class="agent-insights">
    <section class="capability-strip">
      <el-tag
        v-for="capability in enabledCapabilities"
        :key="capability.capability_id"
        type="success"
        effect="light"
      >
        {{ capability.name }}
        <span v-if="capability.provider" class="provider">· {{ capability.provider }}</span>
      </el-tag>
      <el-tag
        v-for="capability in disabledCapabilities"
        :key="capability.capability_id"
        type="info"
        effect="plain"
      >
        {{ capability.name }} 未启用
      </el-tag>
    </section>

    <el-empty v-if="!deepAnalysis" description="尚未生成智能洞察" />
    <template v-else>
      <div class="summary-card">
        <div class="summary-meta">
          <el-tag type="primary" effect="light">{{ deepAnalysis.provider }} · {{ deepAnalysis.model }}</el-tag>
          <span v-if="deepAnalysis.created_at" class="muted">
            {{ deepAnalysis.created_at.replace('T', ' ').slice(0, 19) }}
          </span>
        </div>
        <p>{{ deepAnalysis.summary || '本次分析未返回摘要。' }}</p>
      </div>

      <h3 class="section-title">深度发现</h3>
      <el-empty v-if="deepAnalysis.findings.length === 0" description="暂无深度发现" />
      <el-collapse v-else accordion>
        <el-collapse-item v-for="finding in deepAnalysis.findings" :key="finding.finding_id" :name="finding.finding_id">
          <template #title>
            <div class="finding-title">
              <SeverityTag :severity="finding.severity" />
              <span class="category">[{{ finding.category }}]</span>
              <span>{{ finding.title }}</span>
            </div>
          </template>
          <div class="finding-body">
            <p>{{ finding.summary }}</p>
            <p v-if="finding.detail" class="muted detail">{{ finding.detail }}</p>
            <div v-if="finding.metrics && Object.keys(finding.metrics).length" class="tag-row">
              <el-tag v-for="(value, key) in finding.metrics" :key="key" size="small" effect="plain">
                {{ key }}: {{ value }}
              </el-tag>
            </div>
            <div v-if="finding.evidence?.length" class="evidence-row">
              <span class="muted">证据:</span>
              <EvidenceLink
                v-for="(source, index) in finding.evidence"
                :key="index"
                :source="source"
                @jump="(evidence: SourceRef) => emit('jumpPage', evidence)"
              />
            </div>
            <div v-if="finding.confidence != null" class="muted confidence">
              置信度: {{ Math.round(finding.confidence * 100) }}%
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>

      <h3 class="section-title">运行记录</h3>
      <el-table v-if="agentRuns.length" :data="agentRuns" stripe size="small">
        <el-table-column prop="node_name" label="节点" min-width="160" />
        <el-table-column label="模型" min-width="180">
          <template #default="{ row }: { row: AgentRun }">
            {{ row.provider }} · {{ row.model }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }: { row: AgentRun }">
            <el-tag :type="statusType(row.status)" effect="light">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }: { row: AgentRun }">
            {{ row.elapsed_ms != null ? `${row.elapsed_ms} ms` : '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误" min-width="180" show-overflow-tooltip />
      </el-table>
      <el-empty v-else description="暂无 agent 运行记录" />

      <el-alert
        v-if="deepAnalysis.limitations.length"
        type="warning"
        show-icon
        :closable="false"
        class="limitations"
      >
        <template #title>
          <span>{{ deepAnalysis.limitations.join('；') }}</span>
        </template>
      </el-alert>
    </template>
  </div>
</template>

<style scoped>
.agent-insights { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.capability-strip { display: flex; flex-wrap: wrap; gap: 8px; }
.provider { color: var(--el-text-color-secondary); }
.summary-card { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 14px; background: #fbfcfd; }
.summary-card p { margin: 10px 0 0; line-height: 1.7; }
.summary-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.section-title { margin: 4px 0 0; font-size: 15px; }
.finding-title { display: flex; align-items: center; gap: 8px; }
.category { color: var(--el-text-color-secondary); font-size: 12px; }
.finding-body { display: flex; flex-direction: column; gap: 8px; padding: 4px 0; }
.finding-body p { margin: 0; line-height: 1.7; }
.detail { white-space: pre-wrap; }
.tag-row, .evidence-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.confidence { font-size: 12px; }
.limitations { margin-top: 4px; }
</style>