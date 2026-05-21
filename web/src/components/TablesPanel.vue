<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ExtractedTable, TableCell } from '@/api/types'

const props = defineProps<{ tables: ExtractedTable[] }>()
const emit = defineEmits<{ (e: 'jumpPage', page: number): void }>()

const selected = ref<string>('')

watch(
  () => props.tables,
  (t) => {
    if (t.length && !selected.value) selected.value = t[0].table_id
  },
  { immediate: true },
)

const current = computed(() => props.tables.find((t) => t.table_id === selected.value) || null)

/** Convert sparse cell list into a 2D string matrix. */
function toMatrix(cells: TableCell[]): string[][] {
  let rows = 0
  let cols = 0
  for (const c of cells) {
    rows = Math.max(rows, c.row + (c.rowspan || 1))
    cols = Math.max(cols, c.col + (c.colspan || 1))
  }
  const m: string[][] = Array.from({ length: rows }, () => Array(cols).fill(''))
  for (const c of cells) m[c.row][c.col] = c.text
  return m
}

const matrix = computed(() => (current.value ? toMatrix(current.value.cells) : []))
</script>

<template>
  <div class="tables-panel">
    <el-empty v-if="!tables.length" description="未提取到表格" />
    <div v-else class="layout">
      <div class="sidebar">
        <el-input v-model="selected" placeholder="搜索 table_id" clearable size="small" />
        <el-scrollbar height="500px" class="list">
          <div
            v-for="t in tables"
            :key="t.table_id"
            class="item"
            :class="{ active: t.table_id === selected }"
            @click="selected = t.table_id"
          >
            <div class="item-title">{{ t.title || t.table_id }}</div>
            <div class="item-meta muted">第 {{ t.page }} 页 · {{ t.cells.length }} 单元格</div>
          </div>
        </el-scrollbar>
      </div>

      <div class="preview">
        <div v-if="current" class="preview-header">
          <span><strong>{{ current.title || current.table_id }}</strong></span>
          <el-button link type="primary" size="small" @click="emit('jumpPage', current.page)">
            定位至 PDF 第 {{ current.page }} 页
          </el-button>
        </div>
        <el-scrollbar v-if="current" max-height="540px">
          <table class="grid">
            <tbody>
              <tr v-for="(row, ri) in matrix" :key="ri">
                <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
              </tr>
            </tbody>
          </table>
        </el-scrollbar>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tables-panel { padding: 16px; }
.layout { display: grid; grid-template-columns: 240px 1fr; gap: 16px; }
.sidebar { display: flex; flex-direction: column; gap: 8px; }
.list { border: 1px solid var(--el-border-color-lighter); border-radius: 4px; }
.item {
  padding: 8px 10px; border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
}
.item:hover { background: #f5f7fa; }
.item.active { background: #ecf5ff; }
.item-title { font-size: 13px; font-weight: 500; }
.item-meta { font-size: 11px; margin-top: 2px; }
.preview-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.grid { border-collapse: collapse; font-size: 12px; }
.grid td {
  border: 1px solid #ddd; padding: 4px 8px; vertical-align: top;
  white-space: pre-wrap;
}
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
}
</style>
