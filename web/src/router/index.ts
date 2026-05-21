import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'documents',
    component: () => import('@/views/DocumentList.vue'),
    meta: { title: '文档列表' },
  },
  {
    path: '/upload',
    name: 'upload',
    component: () => import('@/views/UploadView.vue'),
    meta: { title: '上传分析' },
  },
  {
    path: '/documents/:docId',
    name: 'document-detail',
    component: () => import('@/views/DocumentDashboard.vue'),
    props: true,
    meta: { title: '分析报告' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.afterEach((to) => {
  const t = (to.meta?.title as string) || ''
  document.title = t ? `${t} · Jetbot` : 'Jetbot'
})

export default router
