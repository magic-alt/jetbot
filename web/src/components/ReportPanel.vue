<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import { Download } from '@element-plus/icons-vue'

const props = defineProps<{ docId: string; markdown: string }>()

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const html = computed(() => DOMPurify.sanitize(md.render(props.markdown || '')))

function download() {
  const blob = new Blob([props.markdown], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `trader_report_${props.docId}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="report-panel">
    <div v-if="!markdown" class="empty">
      <el-empty description="分析报告尚未生成或不可用" />
    </div>
    <template v-else>
      <div class="toolbar">
        <el-button :icon="Download" size="small" @click="download">下载 Markdown</el-button>
      </div>
      <article class="markdown-body" v-html="html" />
    </template>
  </div>
</template>

<style scoped>
.report-panel { padding: 16px; }
.toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.markdown-body {
  font-size: 14px; line-height: 1.7; color: #303133;
}
.markdown-body :deep(h1) { font-size: 20px; margin-top: 16px; }
.markdown-body :deep(h2) { font-size: 17px; margin-top: 14px; padding-bottom: 4px; border-bottom: 1px solid #eee; }
.markdown-body :deep(h3) { font-size: 15px; margin-top: 12px; }
.markdown-body :deep(table) { border-collapse: collapse; margin: 8px 0; }
.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid #ddd; padding: 4px 8px; font-size: 12px;
}
.markdown-body :deep(code) {
  background: #f4f4f5; padding: 2px 4px; border-radius: 3px; font-size: 12px;
}
.markdown-body :deep(pre) {
  background: #f4f4f5; padding: 12px; border-radius: 4px; overflow-x: auto;
}
.markdown-body :deep(blockquote) {
  margin: 8px 0; padding: 4px 12px; border-left: 4px solid var(--el-color-primary);
  color: var(--el-text-color-secondary); background: #fafbff;
}
</style>
