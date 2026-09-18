// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { formatDecimal } from '@/lib/format'
import { safetyAlertFromDto } from '@/api/adapters/safety'
import type { SafetyAlert, SafetyMonitoringCoverage, SafetyPage } from '@/types'
import { alertDto } from '@/test/safetyFixtures'
import { SafetyAlertsPage } from './SafetyAlertsPage'

const mocks = vi.hoisted(() => ({
  listSafetyAlerts: vi.fn(),
  getSafetyMonitoringCoverage: vi.fn(),
}))
vi.mock('@/api/safety', () => ({
  listSafetyAlerts: mocks.listSafetyAlerts,
  getSafetyMonitoringCoverage: mocks.getSafetyMonitoringCoverage,
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({
    id: 'manager-1',
    fullName: 'Operations Manager',
    role: 'operations_manager',
  }),
}))

const coverage = (overrides: Partial<SafetyMonitoringCoverage> = {}): SafetyMonitoringCoverage => ({
  monitoredProjects: 3,
  projectsWithCoordinates: 3,
  projectsMissingCoordinates: 0,
  alertCreationEnabled: true,
  ...overrides,
})

const pageOf = (items: SafetyAlert[], overrides: Partial<SafetyPage<SafetyAlert>> = {}) => ({
  items,
  count: items.length,
  page: 1,
  totalPages: 1,
  ...overrides,
})

const baseAlert = safetyAlertFromDto(alertDto())

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/operations/safety-alerts']}>
        <Routes>
          <Route
            path="/operations/safety-alerts"
            element={<SafetyAlertsPage basePath="/operations" />}
          />
          <Route path="/operations/safety-alerts/:alertId" element={<p>detail route reached</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const lastFilters = () => mocks.listSafetyAlerts.mock.calls.at(-1)?.[0]

beforeEach(() => {
  mocks.listSafetyAlerts.mockResolvedValue(pageOf([baseAlert]))
  mocks.getSafetyMonitoringCoverage.mockResolvedValue(coverage())
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('no direct network access in tests'))),
  )
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('SafetyAlertsPage', () => {
  it('renders scoped alerts with severity, status, hazard, project, provider, and actions', async () => {
    renderPage()

    expect(await screen.findByText('M 6.0 - Synthetic region')).toBeInTheDocument()
    const table = within(screen.getByRole('table'))
    expect(table.getByText('Cairo construction')).toBeInTheDocument()
    expect(table.getByText('خطورة عالية')).toBeInTheDocument()
    expect(table.getByText('جديد')).toBeInTheDocument()
    expect(table.getByText('زلزال')).toBeInTheDocument()
    expect(table.getByText('USGS')).toBeInTheDocument()
    expect(table.getByText(`${formatDecimal(33)} كم`)).toBeInTheDocument()
    expect(table.getByText('إيقاف الأعمال الخارجية مؤقتاً')).toBeInTheDocument()
    expect(table.getByText('إقرار الاطلاع، استبعاد الإنذار')).toBeInTheDocument()
    expect(lastFilters()).toMatchObject({ page: 1, ordering: '-created_at' })
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows withdrawn and escalated flags from the server response', async () => {
    mocks.listSafetyAlerts.mockResolvedValue(
      pageOf([
        safetyAlertFromDto(
          alertDto({
            hazard_withdrawn_at: '2026-09-15T13:00:00Z',
            escalated_at: '2026-09-15T12:30:00Z',
          }),
        ),
      ]),
    )
    renderPage()
    await screen.findByText('M 6.0 - Synthetic region')
    const table = within(screen.getByRole('table'))
    expect(table.getByText('سحبه المصدر')).toBeInTheDocument()
    expect(table.getByText('تم التصعيد')).toBeInTheDocument()
  })

  it('does not show an empty state while the first page is loading', async () => {
    mocks.listSafetyAlerts.mockReturnValue(new Promise(() => undefined))
    renderPage()
    await waitFor(() => expect(mocks.listSafetyAlerts).toHaveBeenCalled())
    expect(screen.queryByText(/لا توجد إنذارات/)).not.toBeInTheDocument()
  })

  it('distinguishes an empty scope from no matches without implying safety', async () => {
    const user = userEvent.setup()
    mocks.listSafetyAlerts.mockResolvedValue(pageOf([]))
    renderPage()

    expect(await screen.findByText('لا توجد إنذارات سلامة ضمن نطاقك حالياً')).toBeInTheDocument()
    expect(screen.getByText(/غياب الإنذارات لا يعني غياب المخاطر/)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('الخطورة'), 'critical')
    expect(await screen.findByText('لا توجد إنذارات مطابقة للمرشحات')).toBeInTheDocument()
    expect(screen.queryByText(/لا توجد مخاطر/)).not.toBeInTheDocument()
  })

  it('sends only contract filters, resets pagination, and orders server-side', async () => {
    const user = userEvent.setup()
    mocks.listSafetyAlerts.mockImplementation(async (filters: { page?: number }) =>
      pageOf([baseAlert], { count: 40, totalPages: 2, page: filters.page ?? 1 }),
    )
    renderPage()
    await screen.findByText('M 6.0 - Synthetic region')

    await user.click(screen.getByRole('button', { name: 'التالي' }))
    await waitFor(() => expect(lastFilters()).toMatchObject({ page: 2 }))

    await user.selectOptions(screen.getByLabelText('نوع الخطر'), 'flood')
    await waitFor(() => expect(lastFilters()).toMatchObject({ page: 1, hazardType: 'flood' }))
    await user.selectOptions(screen.getByLabelText('المصدر'), 'gdacs')
    await user.selectOptions(screen.getByLabelText('حالة الحدث لدى المصدر'), 'yes')
    await user.selectOptions(screen.getByLabelText('الترتيب'), 'distance_km')
    await user.click(screen.getByRole('button', { name: /تم الإقرار/ }))
    await user.type(screen.getByPlaceholderText('ابحث باسم المشروع أو عنوان الحدث…'), 'Cairo')

    await waitFor(() =>
      expect(lastFilters()).toEqual({
        page: 1,
        search: 'Cairo',
        status: 'acknowledged',
        severity: undefined,
        hazardType: 'flood',
        provider: 'gdacs',
        hazardWithdrawn: true,
        createdAfter: undefined,
        createdBefore: undefined,
        ordering: 'distance_km',
      }),
    )
  })

  it('converts created date filters to ISO boundaries and blocks reversed ranges', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('M 6.0 - Synthetic region')

    await user.type(screen.getByLabelText('من تاريخ الإنشاء'), '2026-09-10')
    await waitFor(() => expect(lastFilters()?.createdAfter).toMatch(/^2026-09-(09|10)T/))

    const calls = mocks.listSafetyAlerts.mock.calls.length
    await user.type(screen.getByLabelText('إلى تاريخ الإنشاء'), '2026-09-01')
    expect(await screen.findByText('يجب ألا يسبق تاريخ البداية')).toBeInTheDocument()
    expect(screen.getByText('نطاق التاريخ غير صالح')).toBeInTheDocument()
    expect(mocks.listSafetyAlerts.mock.calls.length).toBe(calls)
  })

  it('navigates to the role-scoped detail route', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByText('M 6.0 - Synthetic region'))
    expect(await screen.findByText('detail route reached')).toBeInTheDocument()
  })

  it('explains disabled alert creation and unmatched projects neutrally', async () => {
    mocks.getSafetyMonitoringCoverage.mockResolvedValue(
      coverage({
        alertCreationEnabled: false,
        projectsWithCoordinates: 2,
        projectsMissingCoordinates: 1,
      }),
    )
    renderPage()

    expect(await screen.findByText('إنشاء الإنذارات الخارجية غير مفعّل حالياً')).toBeInTheDocument()
    expect(screen.getByText('بعض المشاريع غير قابلة للمطابقة الجغرافية')).toBeInTheDocument()
    expect(screen.getByText(/غياب الإنذارات عنها لا يعني أنها آمنة/)).toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('keeps alerts usable when coverage fails', async () => {
    mocks.getSafetyMonitoringCoverage.mockRejectedValue(new ApiError('boom', 500))
    renderPage()
    expect(await screen.findByText('تعذّر تحميل تغطية المراقبة')).toBeInTheDocument()
    expect(screen.getByText('M 6.0 - Synthetic region')).toBeInTheDocument()
  })

  it.each([
    [403, 'لا تملك صلاحية هذا الإجراء'],
    [404, 'الإنذار غير متاح'],
  ])('shows the forbidden/not-available state for HTTP %s without data', async (status, title) => {
    mocks.listSafetyAlerts.mockRejectedValue(new ApiError('Forbidden detail', status))
    renderPage()
    expect(await screen.findByText(title)).toBeInTheDocument()
    expect(screen.queryByText('Forbidden detail')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows the standard retryable error state for server failures', async () => {
    const user = userEvent.setup()
    mocks.listSafetyAlerts.mockRejectedValueOnce(
      new ApiError('Traceback (most recent call last)', 500),
    )
    renderPage()

    expect(await screen.findByText('تعذّر تحميل البيانات')).toBeInTheDocument()
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'إعادة المحاولة' }))
    expect(await screen.findByText('M 6.0 - Synthetic region')).toBeInTheDocument()
  })
})
