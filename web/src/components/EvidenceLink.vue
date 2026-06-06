<script setup lang="ts">
import { computed } from 'vue'
import { Link as LinkIcon } from '@element-plus/icons-vue'
import type { SourceRef } from '@/api/types'

const props = defineProps<{ source?: SourceRef | null; label?: string }>()
const emit = defineEmits<{ (e: 'jump', source: SourceRef): void }>()

function sourceLabel(source: SourceRef): string {
  const parts = [`P${source.page}`]
  if (source.table_id) parts.push(source.table_id)
  if (source.row != null || source.col != null) {
    parts.push(`r${source.row ?? '?'}c${source.col ?? '?'}`)
  }
  return props.label || parts.join(' · ')
}

const tooltipText = computed(() => {
  if (!props.source) return ''
  const parts = [sourceLabel(props.source)]
  if (props.source.engine) parts.push(`engine: ${props.source.engine}`)
  if (props.source.quote) parts.push(props.source.quote)
  return parts.join(' | ')
})

function trigger(source?: SourceRef | null) {
  if (source) emit('jump', source)
}
</script>

<template>
  <el-tooltip v-if="source" :content="tooltipText" placement="top">
    <el-button link type="primary" size="small" @click="trigger(source)">
      <el-icon style="margin-right:2px"><LinkIcon /></el-icon>
      {{ sourceLabel(source) }}
    </el-button>
  </el-tooltip>
  <span v-else class="muted">—</span>
</template>
