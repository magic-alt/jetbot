import { expect, test } from '@playwright/test'

const documentItem = {
  meta: {
    doc_id: 'doc-1',
    filename: 'apple.pdf',
    company: 'Apple Inc.',
    report_type: 'annual',
    period_end: '2024-09-28',
    created_at: '2024-09-29T10:00:00Z',
  },
  task: { status: 'completed', progress: 100, current_node: null, error_message: null },
}

test.beforeEach(async ({ page }) => {
  await page.route(/\/v1\/documents\?/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, data: { items: [documentItem], total: 1, limit: 20, offset: 0 } }),
    })
  })
  await page.route(/\/v1\/documents\/doc-1$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, data: documentItem }) })
  })
  await page.route(/\/v1\/documents\/doc-1\/statements$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        data: {
          income: { line_items: [], totals: { revenue: 391035, net_income: 93736 } },
          balance: { line_items: [], totals: { total_assets: 364980 } },
          cashflow: { line_items: [], totals: { operating_cf: 118254 } },
        },
      }),
    })
  })
  await page.route(/\/v1\/documents\/doc-1\/risk-signals$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, data: [] }) })
  })
  await page.route(/\/v1\/documents\/doc-1\/notes$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, data: [] }) })
  })
  await page.route(/\/v1\/documents\/doc-1\/tables$/, async (route) => {
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ ok: true, data: [] }) })
  })
  await page.route(/\/v1\/documents\/doc-1\/report\.md$/, async (route) => {
    await route.fulfill({ contentType: 'text/markdown', body: '## Summary\nApple annual report loaded.' })
  })
})

test('document list view navigates without auto-loading PDF preview', async ({ page }) => {
  let pdfRequests = 0
  await page.route(/\/v1\/documents\/doc-1\/pdf$/, async (route) => {
    pdfRequests += 1
    await route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.4\n%%EOF' })
  })

  await page.goto('/#/')

  await expect(page.getByText('文档列表')).toBeVisible()
  await expect(page.getByRole('button', { name: /返回|Back/i })).toHaveCount(0)

  await page.getByRole('button', { name: '查看' }).click()

  await expect(page).toHaveURL(/#\/documents\/doc-1$/)
  await expect(page.getByText('PDF 预览未加载')).toBeVisible()
  expect(pdfRequests).toBe(0)

  await page.getByRole('button', { name: '加载 PDF 预览' }).click()
  await expect.poll(() => pdfRequests).toBe(1)
})