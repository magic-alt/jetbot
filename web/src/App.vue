<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Key } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const showApiKeyDialog = ref(false)
const tmpKey = ref('')

onMounted(() => {
  auth.load()
})

const activeMenu = computed(() => {
  if (route.path.startsWith('/upload')) return '/upload'
  if (route.path.startsWith('/documents/')) return '/'
  return route.path
})

function openApiKey() {
  tmpKey.value = auth.apiKey ?? ''
  showApiKeyDialog.value = true
}

function saveApiKey() {
  auth.setApiKey(tmpKey.value.trim())
  showApiKeyDialog.value = false
}
</script>

<template>
  <el-container class="layout">
    <el-header class="app-header">
      <div class="brand" @click="router.push('/')">
        <span class="logo">📊</span>
        <span class="title">Jetbot · 财报分析平台</span>
      </div>
      <el-menu
        mode="horizontal"
        :default-active="activeMenu"
        :ellipsis="false"
        class="nav-menu"
        @select="(idx: string) => router.push(idx)"
      >
        <el-menu-item index="/">文档列表</el-menu-item>
        <el-menu-item index="/upload">上传分析</el-menu-item>
      </el-menu>
      <div class="header-actions">
        <el-button size="small" @click="openApiKey">
          <el-icon><Key /></el-icon>
          <span style="margin-left:4px">{{ auth.apiKey ? 'API Key 已设置' : '设置 API Key' }}</span>
        </el-button>
      </div>
    </el-header>

    <el-main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </el-main>

    <el-dialog v-model="showApiKeyDialog" title="设置 API Key" width="420px">
      <el-form>
        <el-form-item label="X-API-Key">
          <el-input v-model="tmpKey" placeholder="留空表示不发送该请求头" show-password />
        </el-form-item>
        <p class="hint">仅保存在浏览器 localStorage,刷新后仍生效。</p>
      </el-form>
      <template #footer>
        <el-button @click="showApiKeyDialog = false">取消</el-button>
        <el-button type="primary" @click="saveApiKey">保存</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<style scoped>
.layout { min-height: 100vh; }
.app-header {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-light);
  padding: 0 24px;
}
.brand {
  display: flex; align-items: center; gap: 8px;
  cursor: pointer; font-weight: 600;
}
.brand .logo { font-size: 22px; }
.brand .title { font-size: 16px; color: var(--el-color-primary); }
.nav-menu { flex: 1; border-bottom: none; }
.header-actions { margin-left: auto; }
.app-main { padding: 24px; background: #f5f7fa; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin: 0; }
.fade-enter-active, .fade-leave-active { transition: opacity .15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
