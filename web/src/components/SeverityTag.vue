<script setup lang="ts">
defineProps<{ severity: string }>()

function tagType(s: string): 'success' | 'warning' | 'danger' | 'info' {
  switch (s) {
    case 'high': return 'danger'
    case 'medium': return 'warning'
    case 'low': return 'success'
    default: return 'info'
  }
}
function label(s: string) {
  return { high: '高', medium: '中', low: '低' }[s] || s
}
</script>

<template>
  <el-tag :type="tagType(severity)" effect="dark" size="small">{{ label(severity) }}</el-tag>
</template>
