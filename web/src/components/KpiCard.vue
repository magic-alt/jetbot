<script setup lang="ts">
defineProps<{
  title: string
  value: string | number | null | undefined
  unit?: string | null
  hint?: string | null
}>()
</script>

<template>
  <el-card class="kpi-card" shadow="never">
    <div class="title">{{ title }}</div>
    <div class="value">
      <span v-if="value !== null && value !== undefined && value !== ''">{{ value }}</span>
      <span v-else class="muted">—</span>
      <span v-if="unit" class="unit">{{ unit }}</span>
    </div>
    <div v-if="hint" class="hint muted">{{ hint }}</div>
  </el-card>
</template>

<style scoped>
.kpi-card { border-radius: var(--jetbot-radius); }
.title { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.value { font-size: 20px; font-weight: 600; color: var(--el-color-primary); }
.unit { font-size: 12px; color: var(--el-text-color-secondary); margin-left: 4px; }
.hint { font-size: 11px; margin-top: 4px; }
</style>
