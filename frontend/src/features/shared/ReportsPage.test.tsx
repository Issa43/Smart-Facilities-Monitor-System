// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { GeneratedReport } from '@/types'

const api = vi.hoisted(() => ({
  generateReport: vi.fn(),
  listGeneratedReports: vi.fn(),
  listProjects: vi.fn(),
  listFacilities: vi.fn(),
  listSecurityFacilities: vi.fn(),
  listUsers: vi.fn(),
}))
const showToast = vi.hoisted(() => vi.fn())

vi.mock('@/api/reports', () => ({
  downloadGeneratedReport: vi.fn(),
  generateReport: api.generateReport,
  listGeneratedReports: api.listGeneratedReports,
  retryGeneratedReport: vi.fn(),
}))
vi.mock('@/api/construction', () => ({ listProjects: api.listProjects }))
vi.mock('@/api/operations', () => ({ listFacilities: api.listFacilities }))
vi.mock('@/api/security', () => ({ listSecurityFacilities: api.listSecurityFacilities }))
vi.mock('@/api/users', () => ({ listUsers: api.listUsers }))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({
    id: 'manager-1',
    fullName: 'Construction Manager',
    role: 'construction_manager',
  }),
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast }) }))

import { reportPollingInterval, ReportsPage } from './ReportsPage'

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/construction/reports']}>
        <ReportsPage
          title="Construction Reports"
          description="Construction Project Report v1"
          cards={[{ kind: 'construction', icon: 'reports', description: 'Composite report' }]}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listGeneratedReports.mockResolvedValue([])
  api.listProjects.mockResolvedValue([{ id: 'project-1', name: 'Assigned Project' }])
  api.listFacilities.mockResolvedValue([])
  api.listSecurityFacilities.mockResolvedValue([])
  api.listUsers.mockResolvedValue([])
  api.generateReport.mockResolvedValue({
    id: 'report-1',
    kind: 'construction',
    title: 'Construction Report',
    format: 'pdf',
    periodLabel: 'Last 30 days',
    generatedById: 'manager-1',
    generatedAt: '2026-09-10T00:00:00Z',
    sizeKb: null,
    status: 'queued',
    failureDetails: null,
    downloadAvailable: false,
  })
})

describe('ReportsPage construction contract', () => {
  it('blocks generation until an assigned project is selected', async () => {
    renderPage()
    await screen.findByRole('option', { name: 'Assigned Project' })

    fireEvent.click(screen.getByRole('button', { name: 'PDF' }))

    expect(api.generateReport).not.toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith(
      expect.objectContaining({ tone: 'warning', title: 'اختر المشروع أولاً' }),
    )
  })

  it('submits the selected project and calculated date range for PDF and Excel', async () => {
    const today = new Date()
    const expectedDateTo = today.toISOString().slice(0, 10)
    const expectedDateFromValue = new Date(today)
    expectedDateFromValue.setDate(expectedDateFromValue.getDate() - 30)
    const expectedDateFrom = expectedDateFromValue.toISOString().slice(0, 10)
    renderPage()
    const projectOption = await screen.findByRole('option', { name: 'Assigned Project' })
    fireEvent.change(projectOption.parentElement as HTMLSelectElement, {
      target: { value: 'project-1' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'PDF' }))
    await waitFor(() => expect(api.generateReport).toHaveBeenCalledTimes(1))
    expect(api.generateReport).toHaveBeenLastCalledWith(
      expect.objectContaining({
        kind: 'construction',
        format: 'pdf',
        projectId: 'project-1',
        dateFrom: expectedDateFrom,
        dateTo: expectedDateTo,
      }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Excel' }))
    await waitFor(() => expect(api.generateReport).toHaveBeenCalledTimes(2))
    expect(api.generateReport).toHaveBeenLastCalledWith(
      expect.objectContaining({
        kind: 'construction',
        format: 'excel',
        projectId: 'project-1',
        dateFrom: expectedDateFrom,
        dateTo: expectedDateTo,
      }),
    )
  })

  it('polls only while reports are queued or processing', () => {
    expect(reportPollingInterval(undefined)).toBe(false)
    expect(reportPollingInterval([])).toBe(false)
    expect(reportPollingInterval([{ status: 'queued' } as GeneratedReport])).toBe(3000)
    expect(reportPollingInterval([{ status: 'completed' } as GeneratedReport])).toBe(false)
  })
})
