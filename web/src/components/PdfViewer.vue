<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { docsApi } from '@/api/docs'

const props = defineProps<{ docId: string; page: number | null }>()

const imageUrl = ref('')
const pageNumber = ref(props.page || 1)
const totalPages = ref<number | null>(null)
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
  imageUrl.value = nextUrl
}

async function loadPreview(docId: string) {
  const token = ++requestToken
  hasRequestedPreview.value = true
  loading.value = true
  error.value = ''

  try {
    const [pages, imageBlob] = await Promise.all([
      docsApi.pages(docId).catch(() => []),
      docsApi.pageImageBlob(docId, pageNumber.value),
    ])
    if (token !== requestToken) {
      return
    }
    totalPages.value = pages.length ? pages.length : totalPages.value
    replaceObjectUrl(URL.createObjectURL(imageBlob))
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

function goToPage(nextPage: number) {
  const maxPage = totalPages.value || Number.MAX_SAFE_INTEGER
  pageNumber.value = Math.max(1, Math.min(nextPage, maxPage))
  if (hasRequestedPreview.value) {
    void loadPreview(props.docId)
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
    pageNumber.value = props.page || 1
    totalPages.value = null
  },
)

watch(
  () => props.page,
  (page) => {
    if (!page || page === pageNumber.value) return
    pageNumber.value = page
    if (hasRequestedPreview.value) {
      void loadPreview(props.docId)
    }
  },
)

onBeforeUnmount(() => {
  replaceObjectUrl('')
})

const pageLabel = computed(() => (totalPages.value ? `第 ${pageNumber.value} / ${totalPages.value} 页` : `第 ${pageNumber.value} 页`))
</script>

<template>
  <div class="pdf-wrapper">
    <div class="pdf-toolbar">
      <span class="engine-badge">PDFium</span>
      <el-button size="small" :disabled="pageNumber <= 1 || loading" @click="goToPage(pageNumber - 1)">上一页</el-button>
      <span class="page-label">{{ pageLabel }}</span>
      <el-button size="small" :disabled="Boolean(totalPages && pageNumber >= totalPages) || loading" @click="goToPage(pageNumber + 1)">
        下一页
      </el-button>
      <el-button size="small" type="primary" plain :loading="loading" @click="loadPreview(docId)">刷新预览</el-button>
    </div>
    <div v-if="imageUrl" class="pdf-canvas">
      <img :src="imageUrl" class="pdf-image" :alt="`PDF 第 ${pageNumber} 页`" />
    </div>
    <div v-else class="pdf-placeholder">
      <div class="pdf-placeholder-inner">
        <p>{{ loading ? 'PDF 页面渲染中...' : error || (hasRequestedPreview ? '暂无 PDF 预览' : 'PDF 预览未加载') }}</p>
        <el-button v-if="!loading" type="primary" plain @click="loadPreview(docId)">
          加载 PDF 预览
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-wrapper { width: 100%; height: calc(100vh - 240px); min-height: 480px; display: flex; flex-direction: column; }
.pdf-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  padding: 8px 12px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
}
.engine-badge {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 8px;
  border-radius: 6px;
  background: #111827;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.page-label { min-width: 96px; color: #374151; font-size: 13px; text-align: center; }
.pdf-canvas {
  flex: 1;
  overflow: auto;
  padding: 20px;
  background: #f3f4f6;
  text-align: center;
}
.pdf-image {
  max-width: min(100%, 1120px);
  height: auto;
  background: #fff;
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.16);
}
.pdf-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-height: 480px;
  padding: 24px;
  color: #6b7280;
  background: #fafafa;
  text-align: center;
}
.pdf-placeholder-inner { display: grid; gap: 12px; justify-items: center; }
.pdf-placeholder-inner p { margin: 0; }
</style>
