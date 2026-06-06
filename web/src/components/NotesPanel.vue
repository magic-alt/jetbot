<script setup lang="ts">
import type { KeyNote, SourceRef } from '@/api/types'
import EvidenceLink from './EvidenceLink.vue'

defineProps<{ notes: KeyNote[] }>()
const emit = defineEmits<{ (e: 'jumpPage', source: SourceRef): void }>()
</script>

<template>
  <div class="notes-panel">
    <el-empty v-if="notes.length === 0" description="未提取到关键注释" />
    <el-timeline v-else>
      <el-timeline-item v-for="(n, i) in notes" :key="i" :timestamp="n.topic" placement="top">
        <el-card shadow="never">
          <div class="summary">{{ n.summary }}</div>
          <div v-if="n.evidence?.length" class="evidence">
            <span class="muted">证据: </span>
            <EvidenceLink
              v-for="(e, j) in n.evidence"
              :key="j"
              :source="e"
              @jump="(source: SourceRef) => emit('jumpPage', source)"
            />
          </div>
        </el-card>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<style scoped>
.notes-panel { padding: 16px; }
.summary { font-size: 13px; line-height: 1.6; white-space: pre-wrap; }
.evidence { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
</style>
