<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RiskSignal, SourceRef } from '@/api/types'
import SeverityTag from './SeverityTag.vue'
import EvidenceLink from './EvidenceLink.vue'

const props = defineProps<{ signals: RiskSignal[] }>()
const emit = defineEmits<{ (e: 'jumpPage', source: SourceRef): void }>()

const filterSeverity = ref<string>('all')
const filterCategory = ref<string>('all')

const categories = computed(() => {
  const s = new Set<string>()
  for (const r of props.signals) s.add(r.category)
  return Array.from(s)
})

const rows = computed(() =>
  props.signals.filter((r) => {
    if (filterSeverity.value !== 'all' && r.severity !== filterSeverity.value) return false
    if (filterCategory.value !== 'all' && r.category !== filterCategory.value) return false
    return true
  }),
)
</script>

<template>
  <div class="risk-panel">
    <div class="filters">
      <el-select v-model="filterSeverity" size="small" style="width: 140px">
        <el-option label="全部严重度" value="all" />
        <el-option label="高" value="high" />
        <el-option label="中" value="medium" />
        <el-option label="低" value="low" />
      </el-select>
      <el-select v-model="filterCategory" size="small" style="width: 180px">
        <el-option label="全部类别" value="all" />
        <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
      </el-select>
    </div>

    <el-empty v-if="rows.length === 0" description="无符合条件的风险信号" />
    <el-collapse v-else accordion>
      <el-collapse-item v-for="r in rows" :key="r.id" :name="r.id">
        <template #title>
          <div class="row-title">
            <SeverityTag :severity="r.severity" />
            <span class="cat">[{{ r.category }}]</span>
            <span class="desc">{{ r.description }}</span>
          </div>
        </template>
        <div class="detail">
          <p class="desc-full">{{ r.description }}</p>
          <div v-if="r.metric_refs?.length" class="metrics">
            <strong>关联指标:</strong>
            <el-tag v-for="m in r.metric_refs" :key="m" size="small" style="margin-left: 4px">{{ m }}</el-tag>
          </div>
          <div v-if="r.evidence?.length" class="evidence">
            <strong>证据:</strong>
            <span v-for="(e, idx) in r.evidence" :key="idx" style="margin-left: 8px">
              <EvidenceLink :source="e" @jump="(source: SourceRef) => emit('jumpPage', source)" />
            </span>
          </div>
          <div v-if="r.confidence != null" class="confidence muted">
            置信度: {{ Math.round(r.confidence * 100) }}%
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.risk-panel { padding: 16px; }
.filters { display: flex; gap: 12px; margin-bottom: 12px; }
.row-title { display: flex; align-items: center; gap: 8px; }
.cat { color: var(--el-text-color-secondary); font-size: 12px; }
.desc { color: #303133; font-size: 13px; }
.detail { padding: 8px 4px; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
.desc-full { margin: 0; line-height: 1.6; }
</style>
