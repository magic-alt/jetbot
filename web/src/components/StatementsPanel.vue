<script setup lang="ts">
import { computed } from 'vue'
import type { FinancialStatements, MetricItem } from '@/api/types'
import EvidenceLink from './EvidenceLink.vue'

const props = defineProps<{ statements: FinancialStatements | null }>()
const emit = defineEmits<{ (e: 'jumpPage', page: number): void }>()

const groups = computed(() => {
  if (!props.statements) return [] as { key: string; label: string; rows: MetricItem[] }[]
  const labels: Record<string, string> = {
    income_statement: '利润表',
    balance_sheet: '资产负债表',
    cash_flow: '现金流量表',
  }
  return Object.entries(props.statements)
    .filter(([, v]) => Array.isArray(v) && v.length)
    .map(([k, v]) => ({ key: k, label: labels[k] || k, rows: v as MetricItem[] }))
})
</script>

<template>
  <div class="statements">
    <el-empty v-if="!statements || groups.length === 0" description="尚未提取财务报表数据" />
    <el-collapse v-else :model-value="groups.map((g) => g.key)" accordion>
      <el-collapse-item v-for="g in groups" :key="g.key" :name="g.key" :title="`${g.label} (${g.rows.length})`">
        <el-table :data="g.rows" stripe size="small">
          <el-table-column prop="name" label="科目" min-width="200" />
          <el-table-column label="数值" width="160" align="right">
            <template #default="{ row }: { row: MetricItem }">
              <span v-if="row.value !== null && row.value !== undefined">
                {{ row.value.toLocaleString() }}
              </span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="unit" label="单位" width="100" />
          <el-table-column prop="period" label="期间" width="140" />
          <el-table-column prop="fx" label="币种" width="80" />
          <el-table-column label="置信度" width="100">
            <template #default="{ row }: { row: MetricItem }">
              <el-progress
                v-if="row.confidence != null"
                :percentage="Math.round(row.confidence * 100)"
                :stroke-width="6"
                :show-text="false"
              />
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="证据" width="120">
            <template #default="{ row }: { row: MetricItem }">
              <EvidenceLink :source="row.source" @jump="(p: number) => emit('jumpPage', p)" />
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.statements { padding: 16px; }
</style>
