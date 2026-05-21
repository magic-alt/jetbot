<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { docsApi } from '@/api/docs'
import type {
  DocumentListItem,
  ExtractedTable,
  FinancialStatements,
  KeyNote,
  RiskSignal,
} from '@/api/types'
import { usePolling } from '@/composables/usePolling'
import { Document } from '@element-plus/icons-vue'
import PdfViewer from '@/components/PdfViewer.vue'
import OverviewPanel from '@/components/OverviewPanel.vue'
import StatementsPanel from '@/components/StatementsPanel.vue'
import TablesPanel from '@/components/TablesPanel.vue'
import RiskSignalsPanel from '@/components/RiskSignalsPanel.vue'
import NotesPanel from '@/components/NotesPanel.vue'
import ReportPanel from '@/components/ReportPanel.vue'

const route = useRoute()
const docId = computed(() => String(route.params.docId))

const detail = ref<DocumentListItem | null>(null)
const statements = ref<FinancialStatements | null>(null)
const signals = ref<RiskSignal[]>([])
const notes = ref<KeyNote[]>([])
const tables = ref<ExtractedTable[]>([])
const reportMd = ref<string>('')
const errors = ref<Record<string, string>>({})
const activeTab = ref('overview')
const focusedPage = ref<number | null>(null)

async function loadDetail() {
  try {
    detail.value = await docsApi.detail(docId.value)
  } catch (e: any) {
    errors.value.detail = e.message || '加载失败'
  }
}

async function loadAll() {
  await loadDetail()
  await Promise.all([
    docsApi.statements(docId.value).then((d) => (statements.value = d)).catch(() => null),
    docsApi.riskSignals(docId.value).then((d) => (signals.value = d || [])).catch(() => null),
    docsApi.notes(docId.value).then((d) => (notes.value = d || [])).catch(() => null),
    docsApi.tables(docId.value).then((d) => (tables.value = d || [])).catch(() => null),
    docsApi
      .reportMd(docId.value)
      .then((d) => (reportMd.value = d))
      .catch(() => (reportMd.value = '')),
  ])
}

const status = computed(() => detail.value?.task?.status)
const isFinal = computed(() => ['completed', 'succeeded', 'failed'].includes(status.value || ''))

const polling = usePolling(async () => {
  await loadDetail()
  if (isFinal.value) {
    polling.stop()
    await loadAll()
  }
}, 2500)

onMounted(async () => {
  await loadDetail()
  if (isFinal.value) {
    await loadAll()
  } else {
    polling.start()
  }
})

watch(() => docId.value, async () => {
  polling.stop()
  detail.value = null
  statements.value = null
  signals.value = []
  notes.value = []
  tables.value = []
  reportMd.value = ''
  await loadDetail()
  if (isFinal.value) await loadAll()
  else polling.start()
})

function jumpToPage(page: number) {
  focusedPage.value = page
}
</script>

<template>
  <div class="dashboard">
    <!-- Header card -->
    <el-card class="panel-card header-card">
      <div class="header-row">
        <div class="header-left">
          <div class="title">
            <el-icon><Document /></el-icon>
            <span>{{ detail?.meta.company || detail?.meta.filename || docId }}</span>
          </div>
          <div class="meta-row muted">
            <span v-if="detail?.meta.report_type">类型: {{ detail.meta.report_type }}</span>
            <span v-if="detail?.meta.period_end">报告期末: {{ detail.meta.period_end }}</span>
            <span v-if="detail?.meta.language">语言: {{ detail.meta.language }}</span>
            <span>doc_id: <code>{{ docId }}</code></span>
          </div>
        </div>
        <div class="header-right">
          <el-tag
            v-if="status"
            :type="status === 'completed' || status === 'succeeded' ? 'success' : status === 'failed' ? 'danger' : 'warning'"
          >
            {{ status }}
          </el-tag>
          <el-progress
            v-if="detail?.task?.progress != null && status !== 'completed' && status !== 'succeeded'"
            :percentage="Math.round(detail.task.progress)"
            :stroke-width="8"
            style="width: 200px; margin-left: 12px"
          />
          <span
            v-if="detail?.task?.current_node && status !== 'completed' && status !== 'succeeded'"
            class="muted"
            style="margin-left:8px"
          >
            · {{ detail.task.current_node }}
          </span>
        </div>
      </div>
      <el-alert
        v-if="detail?.task?.error_message"
        type="error"
        show-icon
        :title="detail.task.error_message"
        style="margin-top: 8px"
      />
    </el-card>

    <!-- Split: tabs on the left, PDF viewer on the right -->
    <el-row :gutter="16" class="split">
      <el-col :xs="24" :md="14" :lg="15">
        <el-card class="panel-card content-card">
          <el-tabs v-model="activeTab" type="border-card" class="tabs">
            <el-tab-pane label="概览" name="overview">
              <OverviewPanel
                :statements="statements"
                :signals="signals"
                :report-md="reportMd"
                @jump-page="jumpToPage"
              />
            </el-tab-pane>
            <el-tab-pane label="财务指标" name="statements">
              <StatementsPanel :statements="statements" @jump-page="jumpToPage" />
            </el-tab-pane>
            <el-tab-pane :label="`原始表格 (${tables.length})`" name="tables">
              <TablesPanel :tables="tables" @jump-page="jumpToPage" />
            </el-tab-pane>
            <el-tab-pane :label="`风险信号 (${signals.length})`" name="signals">
              <RiskSignalsPanel :signals="signals" @jump-page="jumpToPage" />
            </el-tab-pane>
            <el-tab-pane :label="`关键注释 (${notes.length})`" name="notes">
              <NotesPanel :notes="notes" @jump-page="jumpToPage" />
            </el-tab-pane>
            <el-tab-pane label="分析报告" name="report">
              <ReportPanel :doc-id="docId" :markdown="reportMd" />
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="10" :lg="9">
        <el-card class="panel-card pdf-card" body-style="padding:0">
          <template #header>
            <div class="pdf-header">
              <span>原始 PDF</span>
              <el-tag v-if="focusedPage" type="info" size="small">已定位至第 {{ focusedPage }} 页</el-tag>
            </div>
          </template>
          <PdfViewer :doc-id="docId" :page="focusedPage" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }
.header-card .header-row {
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
}
.title { display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 600; }
.meta-row { display: flex; gap: 16px; margin-top: 6px; flex-wrap: wrap; }
.header-right { display: flex; align-items: center; }
.split { margin: 0 !important; }
.content-card :deep(.el-card__body) { padding: 0; }
.tabs { border: none; }
.pdf-card { position: sticky; top: 16px; }
.pdf-header { display: flex; justify-content: space-between; align-items: center; }
</style>
