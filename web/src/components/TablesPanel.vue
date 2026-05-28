<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ExtractedTable, SourceRef, TableCell } from '@/api/types'

const props = defineProps<{ tables: ExtractedTable[] }>()
const emit = defineEmits<{ (e: 'jumpPage', source: SourceRef): void }>()

const selected = ref<string>('')
const query = ref('')

interface DisplayCell {
  row: number
  col: number
  text: string
  rowspan: number
  colspan: number
  covered: boolean
}

const filteredTables = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return props.tables
  return props.tables.filter((table) => {
    const haystack = [table.table_id, table.title || '', String(table.page), table.raw_markdown || '', ...table.cells.map((cell) => cell.text)]
      .join(' ')
      .toLowerCase()
    return haystack.includes(needle)
  })
})

watch(
  () => props.tables,
  (t) => {
    if (!t.length) {
      selected.value = ''
      return
    }
    if (!t.some((table) => table.table_id === selected.value)) selected.value = t[0].table_id
  },
  { immediate: true },
)

watch(filteredTables, (tables) => {
  if (!tables.length) return
  if (!tables.some((table) => table.table_id === selected.value)) selected.value = tables[0].table_id
})

const current = computed(() => props.tables.find((t) => t.table_id === selected.value) || null)

function toMatrix(cells: TableCell[]): DisplayCell[][] {
  let rows = 0
  let cols = 0
  for (const c of cells) {
    rows = Math.max(rows, c.row + (c.rowspan || 1))
    cols = Math.max(cols, c.col + (c.colspan || 1))
  }
  const m: DisplayCell[][] = Array.from({ length: rows }, (_, row) =>
    Array.from({ length: cols }, (_, col) => ({ row, col, text: '', rowspan: 1, colspan: 1, covered: false })),
  )
  for (const c of cells) {
    const rowspan = c.rowspan || 1
    const colspan = c.colspan || 1
    m[c.row][c.col] = { row: c.row, col: c.col, text: c.text, rowspan, colspan, covered: false }
    for (let row = c.row; row < c.row + rowspan; row += 1) {
      for (let col = c.col; col < c.col + colspan; col += 1) {
        if (row === c.row && col === c.col) continue
        if (m[row]?.[col]) m[row][col].covered = true
      }
    }
  }
  return m
}

const matrix = computed(() => (current.value ? toMatrix(current.value.cells) : []))
const stats = computed(() => ({
  rows: matrix.value.length,
  cols: matrix.value[0]?.length || 0,
  cells: current.value?.cells.length || 0,
}))
</script>

<template>
  <div class="tables-panel">
    <el-empty v-if="!tables.length" description="未提取到表格" />
    <div v-else class="layout">
      <div class="sidebar">
        <el-input v-model="query" placeholder="搜索表格、页码或单元格" clearable size="small" />
        <el-scrollbar height="500px" class="list">
          <div
            v-for="t in filteredTables"
            :key="t.table_id"
            class="item"
            :class="{ active: t.table_id === selected }"
            @click="selected = t.table_id"
          >
            <div class="item-title">{{ t.title || t.table_id }}</div>
            <div class="item-meta muted">第 {{ t.page }} 页 · {{ t.n_rows || '—' }}×{{ t.n_cols || '—' }} · {{ t.cells.length }} 单元格</div>
          </div>
          <div v-if="!filteredTables.length" class="list-empty">没有匹配的表格</div>
        </el-scrollbar>
      </div>

      <div class="preview">
        <div v-if="current" class="preview-header">
          <div>
            <div class="preview-title">{{ current.title || current.table_id }}</div>
            <div class="table-stats muted">第 {{ current.page }} 页 · {{ stats.rows }} 行 · {{ stats.cols }} 列 · {{ stats.cells }} 单元格</div>
          </div>
          <el-button
            link
            type="primary"
            size="small"
            @click="emit('jumpPage', { ref_type: 'table', page: current.page, table_id: current.table_id, confidence: 1 })"
          >
            定位至 PDF 第 {{ current.page }} 页
          </el-button>
        </div>
        <div v-if="current" class="table-shell">
          <table class="grid">
            <tbody>
              <tr v-for="(row, ri) in matrix" :key="ri">
                <template v-for="cell in row" :key="`${cell.row}-${cell.col}`">
                  <td
                    v-if="!cell.covered"
                    :rowspan="cell.rowspan"
                    :colspan="cell.colspan"
                    :class="{ 'head-cell': ri === 0, 'row-head': cell.col === 0 && ri > 0, 'empty-cell': !cell.text.trim() }"
                  >
                    {{ cell.text || ' ' }}
                  </td>
                </template>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tables-panel { padding: 16px; }
.layout { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 16px; }
.sidebar { display: flex; flex-direction: column; gap: 8px; }
.list { border: 1px solid var(--el-border-color-lighter); border-radius: 6px; background: #fff; }
.item {
  padding: 10px 12px; border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
}
.item:hover { background: #f5f7fa; }
.item.active { background: #eef6ff; box-shadow: inset 3px 0 0 #2563eb; }
.item-title { font-size: 13px; font-weight: 500; }
.item-meta { font-size: 11px; margin-top: 2px; }
.list-empty { padding: 24px 12px; color: #6b7280; font-size: 12px; text-align: center; }
.preview-header {
  display: flex; justify-content: space-between; align-items: center;
  gap: 16px; margin-bottom: 10px;
}
.preview-title { font-size: 14px; font-weight: 650; color: #111827; }
.table-stats { margin-top: 3px; font-size: 12px; }
.table-shell {
  max-height: 560px;
  overflow: auto;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
}
.grid { min-width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
.grid td {
  min-width: 112px;
  max-width: 280px;
  border-right: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
  padding: 7px 10px;
  vertical-align: top;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: #1f2937;
}
.grid tr:first-child td {
  position: sticky;
  top: 0;
  z-index: 2;
}
.grid td:first-child {
  position: sticky;
  left: 0;
  z-index: 1;
}
.grid tr:first-child td:first-child { z-index: 3; }
.head-cell { background: #f1f5f9; font-weight: 650; color: #0f172a; }
.row-head { background: #f8fafc; font-weight: 600; color: #334155; }
.empty-cell { color: #9ca3af; background-image: linear-gradient(135deg, rgba(148, 163, 184, 0.12) 25%, transparent 25%, transparent 50%, rgba(148, 163, 184, 0.12) 50%, rgba(148, 163, 184, 0.12) 75%, transparent 75%); background-size: 8px 8px; }
.muted { color: #6b7280; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .preview-header { align-items: flex-start; flex-direction: column; }
  .grid td { min-width: 96px; }
}
</style>
