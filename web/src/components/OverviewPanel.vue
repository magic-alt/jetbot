<script setup lang="ts">
import { computed } from 'vue'
import type { FinancialStatements, MetricItem, RiskSignal } from '@/api/types'
import KpiCard from './KpiCard.vue'
import SeverityTag from './SeverityTag.vue'
import EvidenceLink from './EvidenceLink.vue'

const props = defineProps<{
  statements: FinancialStatements | null
  signals: RiskSignal[]
  reportMd: string
}>()
const emit = defineEmits<{ (e: 'jumpPage', page: number): void }>()

function findMetric(name: RegExp): MetricItem | null {
  if (!props.statements) return null
  for (const list of Object.values(props.statements)) {
    if (!list) continue
    for (const m of list) if (name.test(m.name)) return m
  }
  return null
}

const revenue = computed(() => findMetric(/^(revenue|total revenue|营业收入|主营业务收入)/i))
const netIncome = computed(() => findMetric(/^(net income|净利润)/i))
const assets = computed(() => findMetric(/^(total assets|资产总计)/i))
const cash = computed(() => findMetric(/(cash and|经营活动产生的现金流|operating cash flow)/i))

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(2) + 'K'
  return String(v)
}

const severitySummary = computed(() => {
  const out = { high: 0, medium: 0, low: 0, other: 0 }
  for (const s of props.signals) {
    if (s.severity === 'high') out.high++
    else if (s.severity === 'medium') out.medium++
    else if (s.severity === 'low') out.low++
    else out.other++
  }
  return out
})

const topSignals = computed(() =>
  [...props.signals]
    .sort((a, b) => sevRank(b.severity) - sevRank(a.severity))
    .slice(0, 5),
)
function sevRank(s: string) {
  return { high: 3, medium: 2, low: 1 }[s] ?? 0
}

const conclusion = computed(() => {
  if (!props.reportMd) return ''
  // Extract a concise conclusion section if present.
  const m =
    props.reportMd.match(/##\s*(?:Conclusion|结论)[\s\S]+?(?=\n##|$)/i) ||
    props.reportMd.match(/##\s*(?:Summary|总结|执行摘要)[\s\S]+?(?=\n##|$)/i)
  return (m?.[0] || props.reportMd.slice(0, 600)).trim()
})
</script>

<template>
  <div class="overview">
    <h3 class="section-title">关键财务指标</h3>
    <div class="kpi-grid">
      <KpiCard
        title="营业收入"
        :value="fmt(revenue?.value ?? null)"
        :unit="revenue?.unit"
        :hint="revenue?.period ?? null"
      />
      <KpiCard
        title="净利润"
        :value="fmt(netIncome?.value ?? null)"
        :unit="netIncome?.unit"
        :hint="netIncome?.period ?? null"
      />
      <KpiCard
        title="资产总计"
        :value="fmt(assets?.value ?? null)"
        :unit="assets?.unit"
        :hint="assets?.period ?? null"
      />
      <KpiCard
        title="经营现金流"
        :value="fmt(cash?.value ?? null)"
        :unit="cash?.unit"
        :hint="cash?.period ?? null"
      />
    </div>

    <h3 class="section-title">风险信号概览</h3>
    <el-row :gutter="12">
      <el-col :span="6"><KpiCard title="高风险" :value="severitySummary.high" /></el-col>
      <el-col :span="6"><KpiCard title="中风险" :value="severitySummary.medium" /></el-col>
      <el-col :span="6"><KpiCard title="低风险" :value="severitySummary.low" /></el-col>
      <el-col :span="6"><KpiCard title="其他" :value="severitySummary.other" /></el-col>
    </el-row>

    <h3 class="section-title">优先关注</h3>
    <el-empty v-if="topSignals.length === 0" description="暂无风险信号" />
    <el-table v-else :data="topSignals" stripe size="small">
      <el-table-column label="等级" width="80">
        <template #default="{ row }: { row: RiskSignal }">
          <SeverityTag :severity="row.severity" />
        </template>
      </el-table-column>
      <el-table-column prop="category" label="类别" width="120" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="证据" width="120">
        <template #default="{ row }: { row: RiskSignal }">
          <EvidenceLink
            :source="row.evidence?.[0]"
            @jump="(p: number) => emit('jumpPage', p)"
          />
        </template>
      </el-table-column>
    </el-table>

    <h3 class="section-title">分析结论</h3>
    <el-card v-if="conclusion" shadow="never" class="conclusion-card">
      <pre class="conclusion">{{ conclusion }}</pre>
    </el-card>
    <el-empty v-else description="尚未生成分析报告" />
  </div>
</template>

<style scoped>
.overview { padding: 16px; }
.section-title { font-size: 14px; font-weight: 600; margin: 18px 0 10px; color: #303133; }
.section-title:first-child { margin-top: 0; }
.conclusion-card { background: #fafbff; }
.conclusion {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  font-family: inherit; font-size: 13px; line-height: 1.6;
}
</style>
