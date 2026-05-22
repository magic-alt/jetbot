<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { docsApi } from '@/api/docs'

const props = defineProps<{ docId: string; page: number | null }>()

const objectUrl = ref('')
const loading = ref(false)
const error = ref('')
const hasRequestedPreview = ref(false)

let currentObjectUrl: string | null = null
let requestToken = 0

function replaceObjectUrl(nextUrl: string) {
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl)
  }
  currentObjectUrl = nextUrl || null
  objectUrl.value = nextUrl
}

async function loadPdf(docId: string) {
  const token = ++requestToken
  hasRequestedPreview.value = true
  loading.value = true
  error.value = ''

  try {
    const pdfBlob = await docsApi.pdfBlob(docId)
    if (token !== requestToken) {
      return
    }
    replaceObjectUrl(URL.createObjectURL(pdfBlob))
  } catch (e: any) {
    if (token !== requestToken) {
      return
    }
    replaceObjectUrl('')
    error.value = e?.message || 'PDF 预览加载失败'
  } finally {
    if (token === requestToken) {
      loading.value = false
    }
  }
}

watch(
  () => props.docId,
  () => {
    requestToken++
    replaceObjectUrl('')
    loading.value = false
    error.value = ''
    hasRequestedPreview.value = false
  },
)

onBeforeUnmount(() => {
  replaceObjectUrl('')
})

const src = computed(() => {
  const base = objectUrl.value
  if (!base) return ''
  // PDF.js viewers in Chrome/Edge honor #page= anchors.
  return props.page ? `${base}#page=${props.page}` : base
})
</script>

<template>
  <div class="pdf-wrapper">
    <iframe v-if="src" :src="src" class="pdf-iframe" title="PDF Preview" />
    <div v-else class="pdf-placeholder">
      <div class="pdf-placeholder-inner">
        <p>{{ loading ? 'PDF 加载中...' : error || (hasRequestedPreview ? '暂无 PDF 预览' : 'PDF 预览未加载') }}</p>
        <el-button v-if="!loading" type="primary" plain @click="loadPdf(docId)">
          加载 PDF 预览
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-wrapper { width: 100%; height: calc(100vh - 240px); min-height: 480px; }
.pdf-iframe { width: 100%; height: 100%; border: 0; background: #fafafa; }
.pdf-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 480px;
  padding: 24px;
  color: #6b7280;
  background: #fafafa;
  text-align: center;
}
.pdf-placeholder-inner { display: grid; gap: 12px; justify-items: center; }
.pdf-placeholder-inner p { margin: 0; }
</style>
