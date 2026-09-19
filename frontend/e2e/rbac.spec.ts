import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const apiUrl = process.env.E2E_API_URL ?? 'http://127.0.0.1:18000/api/v1'
const password = process.env.E2E_TEST_PASSWORD

if (!password) throw new Error('E2E_TEST_PASSWORD is required')

const accounts = {
  super_admin: 'e2e_super_admin@example.test',
  construction_manager: 'e2e_construction_manager@example.test',
  operations_manager: 'e2e_operations_manager@example.test',
  security_officer: 'e2e_security_officer@example.test',
} as const

async function tokenFor(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post(`${apiUrl}/auth/login/`, {
    data: { email, password },
  })
  expect(response.ok()).toBeTruthy()
  return String((await response.json()).access)
}

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.locator('input[type="email"]').fill(email)
  await page.locator('input[type="password"]').fill(password)
  await page.locator('button[type="submit"]').click()
}

test.describe('four-role browser workflows', () => {
  for (const [role, home] of Object.entries({
    super_admin: '/admin/dashboard',
    construction_manager: '/construction/dashboard',
    operations_manager: '/operations/dashboard',
    security_officer: '/security/dashboard',
  })) {
    test(`${role} signs in and reaches only its dashboard`, async ({ page }) => {
      await login(page, accounts[role as keyof typeof accounts])
      await expect(page).toHaveURL(new RegExp(`${home.replaceAll('/', '\\/')}$`))
      await expect(page.locator('main')).toBeVisible()

      if (role !== 'super_admin') {
        await page.goto('/admin/users')
        await expect(page).not.toHaveURL(/\/admin\/users$/)
      }
    })
  }

  test('inactive account is rejected', async ({ page }) => {
    await login(page, 'e2e_inactive@example.test')
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('alert')).toBeVisible()
  })

  test('RTL and mobile layout remain usable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await login(page, accounts.operations_manager)
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)
  })
})

test('object scope, self-approval, protected files, reports, and notifications', async ({
  request,
}) => {
  const adminToken = await tokenFor(request, accounts.super_admin)
  const constructionToken = await tokenFor(request, accounts.construction_manager)
  const operationsToken = await tokenFor(request, accounts.operations_manager)
  const securityToken = await tokenFor(request, accounts.security_officer)

  const adminProjects = await request.get(`${apiUrl}/projects/?search=E2E%20Foreign%20Project`, {
    headers: authHeaders(adminToken),
  })
  const foreignProject = (await adminProjects.json()).results[0]
  expect(
    (
      await request.get(`${apiUrl}/construction/projects/${foreignProject.id}/`, {
        headers: authHeaders(constructionToken),
      })
    ).status(),
  ).toBe(404)

  const facilities = await request.get(`${apiUrl}/facilities/`, {
    headers: authHeaders(adminToken),
  })
  const facilityRows = (await facilities.json()).results
  const foreignFacility = facilityRows.find((row: { name: string }) => row.name.includes('Foreign'))
  expect(
    (
      await request.get(`${apiUrl}/facilities/${foreignFacility.id}/`, {
        headers: authHeaders(operationsToken),
      })
    ).status(),
  ).toBe(404)
  expect(
    (
      await request.get(`${apiUrl}/security/facilities/${foreignFacility.id}/`, {
        headers: authHeaders(securityToken),
      })
    ).status(),
  ).toBe(404)

  const projectResponse = await request.get(`${apiUrl}/construction/projects/`, {
    headers: authHeaders(constructionToken),
  })
  const project = (await projectResponse.json()).results[0]
  const phasesResponse = await request.get(`${apiUrl}/construction/phases/`, {
    headers: authHeaders(constructionToken),
  })
  const phase = (await phasesResponse.json()).results[0]
  const selfApproval = await request.post(
    `${apiUrl}/projects/${project.id}/phases/${phase.id}/approve/`,
    { headers: authHeaders(constructionToken), data: { notes: 'Self approval attempt' } },
  )
  expect(selfApproval.ok()).toBeFalsy()

  const upload = await request.post(`${apiUrl}/construction/documents/`, {
    headers: authHeaders(constructionToken),
    multipart: {
      project: project.id,
      title: 'E2E protected document',
      document_type: 'report',
      file: {
        name: 'e2e.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('%PDF-1.4\n%%EOF\n'),
      },
    },
  })
  expect(upload.status()).toBe(201)
  const document = await upload.json()
  const download = await request.get(`${apiUrl}/construction/documents/${document.id}/download/`, {
    headers: authHeaders(constructionToken),
  })
  expect(download.ok()).toBeTruthy()
  expect(download.headers()['content-type']).toContain('application/pdf')

  const reportRequest = await request.post(`${apiUrl}/reports/requests/`, {
    headers: authHeaders(constructionToken),
    data: {
      type: 'E2E construction summary',
      module: 'construction',
      format: 'excel',
      parameters: { project_id: project.id },
    },
  })
  expect(reportRequest.status()).toBe(202)
  const reportId = (await reportRequest.json()).id
  await expect
    .poll(async () => {
      const response = await request.get(`${apiUrl}/reports/requests/${reportId}/`, {
        headers: authHeaders(constructionToken),
      })
      return (await response.json()).status
    })
    .toBe('completed')
  expect(
    (
      await request.get(`${apiUrl}/reports/requests/${reportId}/download/`, {
        headers: authHeaders(constructionToken),
      })
    ).ok(),
  ).toBeTruthy()

  const notifications = await request.get(`${apiUrl}/notifications/`, {
    headers: authHeaders(constructionToken),
  })
  expect(notifications.ok()).toBeTruthy()
  expect((await notifications.json()).results.length).toBeGreaterThan(0)
})
