<script setup lang="ts">
import { computed } from 'vue'
import { docsApi } from '@/api/docs'

const props = defineProps<{ docId: string; page: number | null }>()

const src = computed(() => {
  const base = docsApi.pdfUrl(props.docId)
  // PDF.js viewers in Chrome/Edge honor #page= anchors.
  return props.page ? `${base}#page=${props.page}` : base
})
</script>

<template>
  <div class="pdf-wrapper">
    <iframe :src="src" class="pdf-iframe" title="PDF Preview" />
  </div>
</template>

<style scoped>
.pdf-wrapper { width: 100%; height: calc(100vh - 240px); min-height: 480px; }
.pdf-iframe { width: 100%; height: 100%; border: 0; background: #fafafa; }
</style>
