<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Delete, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { docsApi } from '@/api/docs'
import type { DocumentListItem } from '@/api/types'

const router = useRouter()
const loading = ref(false)
const items = ref<DocumentListItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const error = ref<string | null>(null)
const deletingIds = ref<Set<string>>(new Set())

function setDeleting(docId: string, deleting: boolean) {
  const next = new Set(deletingIds.value)
  if (deleting) next.add(docId)
  else next.delete(docId)
  deletingIds.value = next
}

function isDeleting(docId: string): boolean {
  return deletingIds.value.has(docId)
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const offset = (page.value - 1) * pageSize.value
    const data = await docsApi.list(pageSize.value, offset)
    items.value = data.items
    total.value = data.total
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function statusTag(s?: string | null): { type: 'success' | 'warning' | 'info' | 'danger'; label: string } {
  switch (s) {
    case 'completed': return { type: 'success', label: '已完成' }
    case 'succeeded': return { type: 'success', label: '已完成' }
    case 'running': return { type: 'warning', label: '运行中' }
    case 'queued': return { type: 'info', label: '排队中' }
    case 'failed': return { type: 'danger', label: '失败' }
    default: return { type: 'info', label: s || '未知' }
  }
}

function go(docId: string) {
  if (isDeleting(docId)) return
  router.push(`/documents/${docId}`)
}

async function remove(row: DocumentListItem) {
  const docId = row.meta.doc_id
  try {
    await ElMessageBox.confirm(
      `确认删除文档“${row.meta.filename || docId}”？删除后将移除分析结果和任务状态。`,
      '删除文档',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }

  setDeleting(docId, true)
  try {
    await docsApi.delete(docId)
    ElMessage.success('文档已删除')
    if (items.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  } finally {
    setDeleting(docId, false)
  }
}

function handleCurrentPageUpdate(value: number) {
  page.value = value
  void load()
}

function handlePageSizeUpdate(value: number) {
  pageSize.value = value
  page.value = 1
  void load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="list-header">
      <div>
        <span class="page-title">文档列表</span>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="$router.push('/upload')">上传新报告</el-button>
        <el-button :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="error" type="error" :title="error" show-icon style="margin-bottom:12px" />

    <el-card v-loading="loading" class="panel-card">
      <el-table :data="items" stripe row-class-name="clickable-row" @row-click="(r: DocumentListItem) => go(r.meta.doc_id)">
        <el-table-column prop="meta.filename" label="文件名" min-width="220" />
        <el-table-column prop="meta.company" label="公司" min-width="140">
          <template #default="{ row }: { row: DocumentListItem }">
            {{ row.meta.company || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="meta.report_type" label="类型" width="120">
          <template #default="{ row }: { row: DocumentListItem }">
            {{ row.meta.report_type || '—' }}
          </template>
        </el-table-column>
        <el-table-column prop="meta.period_end" label="报告期末" width="120">
          <template #default="{ row }: { row: DocumentListItem }">
            {{ row.meta.period_end || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }: { row: DocumentListItem }">
            <el-tag :type="statusTag(row.task?.status).type" effect="light">
              {{ statusTag(row.task?.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="140">
          <template #default="{ row }: { row: DocumentListItem }">
            <el-progress
              v-if="row.task?.progress != null"
              :percentage="Math.round(row.task.progress)"
              :stroke-width="8"
            />
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="meta.created_at" label="创建时间" width="200">
          <template #default="{ row }: { row: DocumentListItem }">
            {{ row.meta.created_at?.replace('T', ' ').slice(0, 19) || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }: { row: DocumentListItem }">
            <el-button link type="primary" @click.stop="go(row.meta.doc_id)">查看</el-button>
            <el-button
              link
              type="danger"
              :icon="Delete"
              :loading="isDeleting(row.meta.doc_id)"
              @click.stop="remove(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有文档,先上传一份吧" />
        </template>
      </el-table>

      <div class="pager">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @update:current-page="handleCurrentPageUpdate"
          @update:page-size="handlePageSizeUpdate"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.list-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px; }
.page-title { font-size: 18px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; }
.pager { display: flex; justify-content: flex-end; margin-top: 12px; }
:deep(.clickable-row) { cursor: pointer; }
</style>
