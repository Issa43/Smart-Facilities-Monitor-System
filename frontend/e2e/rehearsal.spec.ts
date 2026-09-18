import { expect, test, type Page } from '@playwright/test'

const password = process.env.E2E_TEST_PASSWORD

if (!password) throw new Error('E2E_TEST_PASSWORD is required')

const accounts = {
  superAdmin: 'e2e_super_admin@example.test',
  constructionManager: 'e2e_construction_manager@example.test',
  operationsManager: 'e2e_operations_manager@example.test',
  securityOfficer: 'e2e_security_officer@example.test',
} as const

async function login(page: Page, email: string, expectedHome: string) {
  await page.goto('/login')
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(password)
  await page.locator('button[type="submit"]').click()
  await expect(page).toHaveURL(new RegExp(`${expectedHome.replaceAll('/', '\\/')}$`))
}

async function logout(page: Page) {
  await page.goto('/profile')
  await page.getByRole('button', { name: 'تسجيل الخروج' }).click()
  await expect(page).toHaveURL(/\/login$/)
}

test.describe.serial('visible full-system rehearsal', () => {
  test.setTimeout(60_000)

  const suffix = Date.now().toString()
  const projectName = `Rehearsal Project ${suffix}`
  const materialName = `Rehearsal Material ${suffix}`
  const assetName = `Rehearsal Asset ${suffix}`
  const orderReason = `Rehearsal inspection ${suffix}`
  const incidentLocation = `Rehearsal Zone ${suffix}`

  test('Super Admin creates a project and the assignment persists', async ({ page }) => {
    await login(page, accounts.superAdmin, '/admin/dashboard')
    await page.goto('/admin/projects/new')

    await page.getByLabel('اسم المشروع').fill(projectName)
    await page.getByLabel('نوع المنشأة').selectOption({ index: 1 })
    await page.getByLabel('موقع المشروع').fill('Riyadh — rehearsal district')
    await page
      .getByLabel('وصف المشروع')
      .fill('A browser-created rehearsal project used to verify assignment and persistence.')
    await page.getByLabel('تاريخ البداية').fill('2026-08-25')
    await page.getByLabel('تاريخ الانتهاء المتوقع').fill('2026-12-31')
    await page.getByLabel('مدير الإنشاءات المسؤول').selectOption({ index: 1 })
    await page.getByRole('button', { name: 'إنشاء المشروع' }).click()

    await expect(page.getByText(projectName, { exact: true }).first()).toBeVisible()
    await page.reload()
    await expect(page.getByText(projectName, { exact: true }).first()).toBeVisible()
    await logout(page)
  })

  test('Construction Manager manages stock and cannot self-approve a request', async ({ page }) => {
    await login(page, accounts.constructionManager, '/construction/dashboard')
    await expect(page.getByText(projectName, { exact: true }).first()).toBeVisible()
    await page.goto('/construction/materials')

    await page.getByRole('button', { name: '+ مادة جديدة' }).click()
    await page.getByLabel('المشروع').selectOption({ label: projectName })
    await page.getByRole('textbox', { name: /اسم المادة/ }).fill(materialName)
    await page.getByLabel('وحدة القياس').selectOption('each')
    await page.getByLabel('الكمية المطلوبة').fill('20')
    await page.getByLabel('الحد الأدنى للمخزون').fill('18')
    await page.getByRole('button', { name: 'حفظ المادة' }).click()

    let row = page.getByRole('row').filter({ hasText: materialName })
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: 'تسجيل استهلاك' }).click()
    await page.getByLabel('الكمية المستهلكة').fill('5')
    await page.getByRole('button', { name: 'حفظ الاستهلاك' }).click()
    await page.reload()
    row = page.getByRole('row').filter({ hasText: materialName })
    await expect(row).toContainText('15')

    await page.goto('/construction/material-requests/new')
    await page.getByLabel('المشروع').selectOption({ label: projectName })
    await page.getByLabel('المادة').selectOption({ label: materialName })
    await page.getByLabel('الكمية المطلوبة').fill('10')
    await page
      .getByLabel('سبب الطلب')
      .fill('Rehearsal request created after the verified stock threshold notification.')
    await page.getByRole('button', { name: 'إرسال الطلب' }).click()

    row = page.getByRole('row').filter({ hasText: materialName })
    await expect(row).toContainText('بانتظار مراجعة مستخدم آخر')
    await expect(row.getByRole('button', { name: 'اعتماد' })).toHaveCount(0)
    await page.reload()
    await expect(page.getByRole('row').filter({ hasText: materialName })).toBeVisible()

    await page.getByRole('button', { name: /الإشعارات/ }).click()
    await expect(page.getByRole('dialog', { name: 'الإشعارات' })).toContainText(materialName)
    await page.keyboard.press('Escape')

    await page.goto('/construction/reports')
    await page.getByLabel('المشروع').selectOption({ label: projectName })
    const reportCard = page.locator('article').filter({ hasText: 'تقرير الإنشاءات' })
    await reportCard.getByRole('button', { name: 'PDF' }).click()
    const reportRow = page
      .getByRole('row')
      .filter({ hasText: 'تقرير الإنشاءات' })
      .filter({ hasText: 'PDF' })
      .first()
    await expect(reportRow).toContainText('مكتمل', { timeout: 30_000 })
    const downloadPromise = page.waitForEvent('download')
    await reportRow.getByRole('button', { name: 'تنزيل' }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(/\.pdf$/i)
    await logout(page)
  })

  test('Operations Manager completes an asset maintenance lifecycle', async ({ page }) => {
    await login(page, accounts.operationsManager, '/operations/dashboard')
    await page.goto('/operations/assets')

    await page.getByRole('button', { name: '+ أصل جديد' }).click()
    const assetDialog = page.getByRole('dialog', { name: 'إضافة أصل' })
    await assetDialog
      .getByRole('combobox', { name: /المنشأة/ })
      .selectOption({ label: 'E2E Assigned Facility' })
    await assetDialog.getByLabel('اسم الأصل').fill(assetName)
    await assetDialog.getByLabel('نوع الأصل').fill('Rehearsal HVAC')
    await assetDialog.getByLabel('الشركة المصنعة').fill('SFLMS Test')
    await assetDialog.getByLabel('الطراز').fill(`MODEL-${suffix}`)
    await assetDialog.getByLabel('الموقع داخل المنشأة').fill('Mechanical room A')
    await assetDialog.getByLabel('الرقم التسلسلي').fill(`SERIAL-${suffix}`)
    await assetDialog.getByLabel('تاريخ التركيب').fill('2026-08-01')
    await assetDialog.getByLabel('تاريخ التشغيل').fill('2026-08-02')
    await assetDialog.getByRole('button', { name: 'حفظ الأصل' }).click()
    await expect(page.getByRole('row').filter({ hasText: assetName })).toBeVisible()

    await page.goto('/operations/work-orders')
    await page.getByRole('button', { name: '+ أمر صيانة' }).click()
    const orderDialog = page.getByRole('dialog', { name: 'إنشاء أمر صيانة' })
    await orderDialog.getByLabel('الأصل').selectOption({ label: assetName })
    await orderDialog.getByLabel('سبب الصيانة').fill(orderReason)
    await orderDialog
      .getByLabel('وصف العمل المطلوب')
      .fill('Inspect and validate the browser-created rehearsal asset.')
    await orderDialog.getByLabel('بنود التنفيذ').fill('Inspect unit\nRecord result')
    await orderDialog.getByLabel('تاريخ التنفيذ المتوقع').fill('2026-08-30')
    await orderDialog.getByRole('button', { name: 'إنشاء الأمر' }).click()

    const orderRow = page.getByRole('row').filter({ hasText: orderReason })
    await expect(orderRow).toBeVisible()
    await orderRow.click()
    await page.getByRole('button', { name: 'بدء التنفيذ' }).click()
    await page.getByRole('button', { name: 'Inspect unit' }).click()
    await page.getByRole('button', { name: 'Record result' }).click()
    await page
      .getByLabel('ملاحظات فنية')
      .fill('Lifecycle completed through the visible browser UI.')
    await page.getByRole('button', { name: 'حفظ الملاحظات' }).click()
    await page.getByRole('button', { name: 'إكمال الأمر' }).click()
    await page.getByRole('button', { name: 'تأكيد الإكمال' }).click()
    await page.getByRole('button', { name: 'إغلاق الأمر المكتمل' }).click()
    await expect(page.getByText('مغلق', { exact: true }).first()).toBeVisible()
    await page.reload()
    await expect(page.getByText('مغلق', { exact: true }).first()).toBeVisible()
    await logout(page)
  })

  test('Security Officer investigates, documents, and closes an incident', async ({ page }) => {
    await login(page, accounts.securityOfficer, '/security/dashboard')
    await page.goto('/security/incidents')

    await page.getByRole('button', { name: '+ حادث جديد' }).click()
    const incidentDialog = page.getByRole('dialog', { name: 'تسجيل حادث جديد' })
    await incidentDialog
      .getByRole('combobox', { name: /المنشأة/ })
      .selectOption({ label: 'E2E Assigned Facility' })
    await incidentDialog.getByLabel('موقع الحادث').fill(incidentLocation)
    await incidentDialog
      .getByLabel('وصف الحادث')
      .fill('Visible browser rehearsal incident for notes, actions, evidence, and closure.')
    await incidentDialog.getByRole('button', { name: 'إنشاء الحادث' }).click()

    await expect(page.getByText(incidentLocation, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'بدء التحقيق' }).click()
    await page.getByRole('tab', { name: /ملاحظات التحقيق/ }).click()
    await page
      .getByLabel('إضافة ملاحظة')
      .fill('Verified location and completed the initial investigation.')
    await page.getByRole('button', { name: 'إضافة الملاحظة' }).click()
    await expect(
      page.getByText('Verified location and completed the initial investigation.'),
    ).toBeVisible()

    await page.getByRole('tab', { name: /إجراءات الاستجابة/ }).click()
    await page.getByLabel('إضافة إجراء').fill('Secure rehearsal area')
    await page.getByRole('button', { name: 'إضافة', exact: true }).click()
    const responseAction = page.getByRole('button', { name: 'Secure rehearsal area' })
    await expect(responseAction).toHaveAttribute('aria-pressed', 'false')
    await responseAction.click()
    await expect(responseAction).toHaveAttribute('aria-pressed', 'true')

    await page.getByRole('tab', { name: /الأدلة والمرفقات/ }).click()
    await page.locator('input[type="file"]').setInputFiles({
      name: `rehearsal-${suffix}.pdf`,
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4\n%%EOF\n'),
    })
    await page.getByRole('button', { name: 'إضافة الدليل' }).click()
    await expect(page.getByText(`rehearsal-${suffix}.pdf`)).toBeVisible()

    await page.getByRole('button', { name: 'إغلاق الحادث' }).click()
    await page
      .getByLabel('التقرير النهائي')
      .fill('The incident was investigated, documented, secured, and safely closed.')
    await page.getByRole('button', { name: 'تأكيد الإغلاق' }).click()
    await expect(page.getByText(/تم إغلاق الحادث في/)).toBeVisible()
    await page.reload()
    await expect(page.getByText(/تم إغلاق الحادث في/)).toBeVisible()
    await logout(page)
  })
})
