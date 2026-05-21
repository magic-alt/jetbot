<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { UploadFilled } from '@element-plus/icons-vue'
import { docsApi } from '@/api/docs'
import type { UploadRequestOptions, UploadUserFile } from 'element-plus'
import { ElMessage } from 'element-plus'

const router = useRouter()
const fileList = ref<UploadUserFile[]>([])
const language = ref<'auto' | 'zh' | 'en'>('auto')
const useOcr = ref(false)
const uploading = ref(false)
const lastDocId = ref<string | null>(null)

async function uploadHandler(opts: UploadRequestOptions) {
  uploading.value = true
  try {
    const data = await docsApi.upload(opts.file as File, {
      language: language.value === 'auto' ? undefined : language.value,
      ocr: useOcr.value || undefined,
    })
    lastDocId.value = data.doc_id
    ElMessage.success(`已创建任务: ${data.doc_id}`)
    opts.onSuccess?.(data)
    // Jump to detail page so the user can watch progress live.
    setTimeout(() => router.push(`/documents/${data.doc_id}`), 400)
  } catch (e: any) {
    ElMessage.error(e.message || '上传失败')
    opts.onError?.(e as any)
  } finally {
    uploading.value = false
  }
}

function beforeUpload(file: File): boolean {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.error('仅支持 PDF 文件')
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件不能超过 50MB')
    return false
  }
  return true
}
</script>

<template>
  <div class="upload-view">
    <el-card class="panel-card">
      <template #header><span class="title">上传财报 PDF</span></template>

      <el-form label-width="100px" label-position="left">
        <el-form-item label="语言">
          <el-radio-group v-model="language">
            <el-radio value="auto">自动</el-radio>
            <el-radio value="zh">中文</el-radio>
            <el-radio value="en">English</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="OCR">
          <el-switch v-model="useOcr" />
          <span class="muted" style="margin-left:12px">扫描件或图片型 PDF 建议开启</span>
        </el-form-item>
        <el-form-item label="PDF 文件">
          <el-upload
            v-model:file-list="fileList"
            :http-request="uploadHandler"
            :before-upload="beforeUpload"
            :limit="1"
            accept="application/pdf"
            drag
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">
              拖动 PDF 至此 或 <em>点击选择</em>
            </div>
            <template #tip>
              <div class="muted" style="margin-top:8px">
                上传后将立即创建分析任务,完成后可在“文档列表”查看结果。
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="lastDocId"
        type="success"
        show-icon
        :title="`任务已创建: ${lastDocId}`"
        :description="`分析约需 1-3 分钟,稍后可在文档详情页查看进度。`"
        style="margin-top:12px"
      />
    </el-card>
  </div>
</template>

<style scoped>
.upload-view { max-width: 720px; margin: 0 auto; }
.title { font-weight: 600; font-size: 16px; }
</style>
