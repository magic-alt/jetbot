<script setup lang="ts">
import { Link as LinkIcon } from '@element-plus/icons-vue'
import type { SourceRef } from '@/api/types'

defineProps<{ source?: SourceRef | null; label?: string }>()
const emit = defineEmits<{ (e: 'jump', page: number): void }>()

function trigger(s?: SourceRef | null) {
  if (s?.page) emit('jump', s.page)
}
</script>

<template>
  <el-tooltip v-if="source" :content="source.quote || `第 ${source.page} 页`" placement="top">
    <el-button link type="primary" size="small" @click="trigger(source)">
      <el-icon style="margin-right:2px"><LinkIcon /></el-icon>
      {{ label || `P${source.page}${source.table_id ? ' · ' + source.table_id : ''}` }}
    </el-button>
  </el-tooltip>
  <span v-else class="muted">—</span>
</template>
