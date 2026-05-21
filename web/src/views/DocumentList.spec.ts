// @vitest-environment jsdom

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DocumentList from './DocumentList.vue'

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  confirm: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  docsApi: {
    list: vi.fn(),
    delete: vi.fn(),
  },
}))

const { routerPush, confirm, success, error, docsApi } = mocks

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('@element-plus/icons-vue', () => ({ Delete: {}, Refresh: {} }))

vi.mock('element-plus', async () => {
  const { defineComponent, h } = await import('vue')

  function getByPathLocal(source: any, path?: string): string {
    if (!path) return ''
    return String(path.split('.').reduce((value, part) => value?.[part], source) ?? '')
  }

  const ElTable = defineComponent({
    props: { data: { type: Array, default: () => [] } },
    emits: ['row-click'],
    setup(props, { emit, slots }) {
      return () =>
        h(
          'div',
          { class: 'table-stub' },
          (props.data as any[]).map((tableRow) =>
            h(
              'div',
              { class: 'table-row', onClick: () => emit('row-click', tableRow) },
              (slots.default?.() ?? []).flatMap((column: any) => {
                const columnSlots = column.children || {}
                if (typeof columnSlots.default === 'function') return columnSlots.default({ row: tableRow })
                return getByPathLocal(tableRow, column.props?.prop)
              }),
            ),
          ),
        )
    },
  })

  return {
    ElMessageBox: { confirm: mocks.confirm },
    ElMessage: { success: mocks.success, error: mocks.error },
    ElLoadingDirective: { mounted() {}, updated() {} },
    ElAlert: { template: '<div><slot /></div>' },
    ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\', $event)"><slot /></button>' },
    ElCard: { template: '<div><slot /></div>' },
    ElEmpty: { template: '<div><slot /></div>' },
    ElPagination: { template: '<div><slot /></div>' },
    ElProgress: { template: '<div><slot /></div>' },
    ElTable,
    ElTableColumn: { props: ['prop', 'label'], template: '<div><slot /></div>' },
    ElTag: { template: '<span><slot /></span>' },
  }
})

vi.mock('@/api/docs', () => ({ docsApi: mocks.docsApi }))

const row = {
  meta: {
    doc_id: 'doc-1',
    filename: 'apple.pdf',
    company: 'Apple Inc.',
    report_type: 'annual',
    period_end: '2024-09-28',
    created_at: '2024-09-29T10:00:00Z',
  },
  task: { status: 'completed', progress: 100 },
}

function getByPath(source: any, path?: string): string {
  if (!path) return ''
  return String(path.split('.').reduce((value, part) => value?.[part], source) ?? '')
}

const ElTableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  emits: ['row-click'],
  setup(props, { emit, slots }) {
    return () =>
      h(
        'div',
        { class: 'table-stub' },
        (props.data as any[]).map((tableRow) =>
          h(
            'div',
            { class: 'table-row', onClick: () => emit('row-click', tableRow) },
            (slots.default?.() ?? []).flatMap((column: any) => {
              const columnSlots = column.children || {}
              if (typeof columnSlots.default === 'function') return columnSlots.default({ row: tableRow })
              return getByPath(tableRow, column.props?.prop)
            }),
          ),
        ),
      )
  },
})

function mountList() {
  return mount(DocumentList, {
    global: {
      mocks: { $router: { push: routerPush } },
      stubs: {
        ElTable: ElTableStub,
        ElTableColumn: { template: '<div><slot /></div>' },
        ElCard: { template: '<div><slot /></div>' },
        ElButton: { emits: ['click'], template: '<button @click="$emit(\'click\', $event)"><slot /></button>' },
        ElAlert: true,
        ElTag: { template: '<span><slot /></span>' },
        ElProgress: true,
        ElPagination: true,
        ElEmpty: true,
      },
    },
  })
}

describe('DocumentList', () => {
  beforeEach(() => {
    routerPush.mockReset()
    confirm.mockReset()
    success.mockReset()
    error.mockReset()
    docsApi.list.mockReset().mockResolvedValue({ items: [row], total: 1, limit: 20, offset: 0 })
    docsApi.delete.mockReset().mockResolvedValue({ doc_id: 'doc-1', deleted: true })
  })

  it('renders without a page-header back button', async () => {
    const wrapper = mountList()
    await flushPromises()

    expect(wrapper.findComponent({ name: 'ElPageHeader' }).exists()).toBe(false)
    expect(wrapper.text()).toContain('文档列表')
  })

  it('opens detail view without requesting deletion confirmation', async () => {
    const wrapper = mountList()
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text() === '查看')?.trigger('click')

    expect(routerPush).toHaveBeenCalledWith('/documents/doc-1')
    expect(confirm).not.toHaveBeenCalled()
    expect(docsApi.delete).not.toHaveBeenCalled()
  })

  it('confirms and deletes documents', async () => {
    confirm.mockResolvedValue(undefined)
    const wrapper = mountList()
    await flushPromises()

    await wrapper.findAll('button').find((button) => button.text().includes('删除'))?.trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalled()
    expect(docsApi.delete).toHaveBeenCalledWith('doc-1')
    expect(success).toHaveBeenCalledWith('文档已删除')
    expect(routerPush).not.toHaveBeenCalledWith('/documents/doc-1')
  })
})