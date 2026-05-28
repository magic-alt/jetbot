<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { docsApi } from '@/api/docs'
import type { Correction, FinancialFact, SourceRef } from '@/api/types'
import EvidenceLink from './EvidenceLink.vue'

const props = defineProps<{
  docId: string
  facts: FinancialFact[]
  corrections: Correction[]
}>()

const emit = defineEmits<{
  (e: 'jumpPage', target: number | SourceRef | SourceRef[]): void
  (e: 'updated'): void
}>()

const dialogVisible = ref(false)
const submitting = ref(false)
const selectedFact = ref<FinancialFact | null>(null)
const selectedField = ref('value')
const textValue = ref('')
const numberValue = ref<number | null>(null)
const periodTypeValue = ref<'instant' | 'duration' | 'unknown'>('duration')
const actor = ref('analyst')
const reason = ref('')
const sourceRefsJson = ref('[]')

const correctionCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const correction of props.corrections) {
    counts[correction.fact_id] = (counts[correction.fact_id] || 0) + 1
  }
  return counts
})

const recentCorrections = computed(() =>
  [...props.corrections].sort((left, right) => String(right.created_at || '').localeCompare(String(left.created_at || ''))),
)

function currentFieldValue(fact: FinancialFact, fieldName: string): unknown {
  switch (fieldName) {
    case 'value':
      return fact.value
    case 'concept':
      return fact.concept
    case 'unit':
      return fact.unit
    case 'period_start':
      return fact.period_start
    case 'period_end':
      return fact.period_end
    case 'period_type':
      return fact.period_type
    case 'source_refs':
      return fact.source_refs
    default:
      return null
  }
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value) || typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function formatTimestamp(value?: string | null): string {
  if (!value) return '刚刚'
  return value.replace('T', ' ').slice(0, 19)
}

function periodLabel(fact: FinancialFact): string {
  return [fact.period_start, fact.period_end, fact.period_type].filter(Boolean).join(' · ') || '—'
}

function seedForm(fact: FinancialFact, fieldName: string) {
  const current = currentFieldValue(fact, fieldName)
  numberValue.value = typeof current === 'number' ? current : null
  textValue.value = typeof current === 'string' ? current : ''
  periodTypeValue.value = (fact.period_type || 'duration') as 'instant' | 'duration' | 'unknown'
  sourceRefsJson.value = JSON.stringify(fact.source_refs, null, 2)
}

function openCorrection(fact: FinancialFact) {
  selectedFact.value = fact
  selectedField.value = 'value'
  actor.value = 'analyst'
  reason.value = ''
  seedForm(fact, 'value')
  dialogVisible.value = true
}

watch(selectedField, (fieldName) => {
  if (selectedFact.value) {
    seedForm(selectedFact.value, fieldName)
  }
})

function parseSourceRefs(): SourceRef[] {
  const parsed = JSON.parse(sourceRefsJson.value || '[]')
  if (!Array.isArray(parsed)) {
    throw new Error('证据 JSON 必须是数组。')
  }
  return parsed as SourceRef[]
}

function buildNewValue(): unknown {
  switch (selectedField.value) {
    case 'value':
      return numberValue.value
    case 'period_type':
      return periodTypeValue.value
    case 'source_refs':
      return parseSourceRefs()
    default:
      return textValue.value || null
  }
}

async function submitCorrection() {
  if (!selectedFact.value) return
  submitting.value = true
  try {
    const auditSourceRefs = selectedField.value === 'source_refs' ? parseSourceRefs() : selectedFact.value.source_refs
    await docsApi.createCorrection(props.docId, selectedFact.value.fact_id, {
      field_name: selectedField.value,
      new_value: buildNewValue(),
      actor: actor.value || 'analyst',
      reason: reason.value || null,
      source_refs: auditSourceRefs,
    })
    ElMessage.success('修正已保存')
    dialogVisible.value = false
    emit('updated')
  } catch (error: any) {
    ElMessage.error(error?.message || '保存修正失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="facts-review">
    <el-empty v-if="facts.length === 0" description="尚未提取事实数据" />
    <template v-else>
      <el-table :data="facts" stripe size="small">
        <el-table-column prop="label" label="事实" min-width="180" />
        <el-table-column prop="concept" label="Canonical Concept" min-width="160" />
        <el-table-column label="数值" width="140" align="right">
          <template #default="{ row }: { row: FinancialFact }">
            {{ row.value != null ? row.value.toLocaleString() : '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="unit" label="单位" width="100" />
        <el-table-column label="期间" min-width="180">
          <template #default="{ row }: { row: FinancialFact }">
            {{ periodLabel(row) }}
          </template>
        </el-table-column>
        <el-table-column label="证据" min-width="220">
          <template #default="{ row }: { row: FinancialFact }">
            <div class="evidence-cell">
              <EvidenceLink
                v-for="(source, index) in row.source_refs.slice(0, 2)"
                :key="`${row.fact_id}-${index}`"
                :source="source"
                @jump="(evidence: SourceRef) => emit('jumpPage', evidence)"
              />
              <el-button v-if="row.source_refs.length > 1" link type="primary" size="small" @click="emit('jumpPage', row.source_refs)">
                高亮全部
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="修正次数" width="100" align="center">
          <template #default="{ row }: { row: FinancialFact }">
            {{ correctionCounts[row.fact_id] || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }: { row: FinancialFact }">
            <el-button link type="primary" size="small" @click="openCorrection(row)">
              编辑修正
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="history-section">
        <h3 class="section-title">修正历史</h3>
        <el-empty v-if="recentCorrections.length === 0" description="尚未提交人工修正" />
        <el-timeline v-else>
          <el-timeline-item
            v-for="correction in recentCorrections"
            :key="correction.correction_id"
            :timestamp="formatTimestamp(correction.created_at)"
            placement="top"
          >
            <div class="history-item">
              <div class="history-title">{{ correction.field_name }} · {{ correction.actor }} · {{ correction.fact_id }}</div>
              <div class="history-body">{{ formatValue(correction.old_value) }} → {{ formatValue(correction.new_value) }}</div>
              <div v-if="correction.reason" class="muted history-reason">{{ correction.reason }}</div>
              <div v-if="correction.source_refs.length" class="history-evidence">
                <span class="muted">证据:</span>
                <EvidenceLink
                  v-for="(source, index) in correction.source_refs"
                  :key="`${correction.correction_id}-${index}`"
                  :source="source"
                  @jump="(evidence: SourceRef) => emit('jumpPage', evidence)"
                />
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>
    </template>

    <el-dialog v-model="dialogVisible" title="创建人工修正" width="640px">
      <div v-if="selectedFact" class="dialog-body">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            <span>{{ selectedFact.label }} · {{ selectedFact.concept }}</span>
          </template>
        </el-alert>

        <el-form label-position="top" class="correction-form">
          <el-form-item label="修正字段">
            <el-select v-model="selectedField">
              <el-option label="Value" value="value" />
              <el-option label="Concept" value="concept" />
              <el-option label="Unit" value="unit" />
              <el-option label="Period Start" value="period_start" />
              <el-option label="Period End" value="period_end" />
              <el-option label="Period Type" value="period_type" />
              <el-option label="Evidence / Source Refs" value="source_refs" />
            </el-select>
          </el-form-item>

          <el-form-item label="当前值">
            <div class="current-value">{{ formatValue(currentFieldValue(selectedFact, selectedField)) }}</div>
          </el-form-item>

          <el-form-item v-if="selectedField === 'value'" label="新数值">
            <el-input-number v-model="numberValue" :controls="false" style="width: 100%" />
          </el-form-item>

          <el-form-item v-else-if="selectedField === 'period_type'" label="新期间类型">
            <el-select v-model="periodTypeValue">
              <el-option label="instant" value="instant" />
              <el-option label="duration" value="duration" />
              <el-option label="unknown" value="unknown" />
            </el-select>
          </el-form-item>

          <el-form-item v-else-if="selectedField === 'source_refs'" label="新证据 JSON">
            <el-input v-model="sourceRefsJson" type="textarea" :rows="8" />
          </el-form-item>

          <el-form-item v-else label="新值">
            <el-input v-model="textValue" />
          </el-form-item>

          <el-form-item label="Actor">
            <el-input v-model="actor" />
          </el-form-item>

          <el-form-item label="Reason">
            <el-input v-model="reason" type="textarea" :rows="3" />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitCorrection">保存修正</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.facts-review { padding: 16px; display: flex; flex-direction: column; gap: 18px; }
.section-title { margin: 0 0 10px; font-size: 15px; }
.evidence-cell { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.history-section { display: flex; flex-direction: column; gap: 10px; }
.history-item {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
}
.history-title { font-size: 13px; font-weight: 600; }
.history-body { margin-top: 4px; font-size: 13px; line-height: 1.6; }
.history-reason { margin-top: 6px; font-size: 12px; }
.history-evidence { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.dialog-body { display: flex; flex-direction: column; gap: 14px; }
.correction-form { margin-top: 4px; }
.current-value {
  min-height: 34px;
  display: flex;
  align-items: center;
  padding: 0 11px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: #f8fafc;
  color: #374151;
  font-size: 13px;
}
.dialog-footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>
