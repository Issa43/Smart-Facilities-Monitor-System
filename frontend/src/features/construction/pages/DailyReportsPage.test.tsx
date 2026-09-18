// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DailyReportsPage } from './DailyReportsPage'

const mocks = vi.hoisted(() => ({
  createDailyReport: vi.fn(),
  deleteDailyReport: vi.fn(),
  getDailyReport: vi.fn(),
  listDailyReports: vi.fn(),
  listProjects: vi.fn(),
  showToast: vi.fn(),
  updateDailyReport: vi.fn(),
}))

vi.mock('@/api/construction', () => ({
  createDailyReport: mocks.createDailyReport,
  deleteDailyReport: mocks.deleteDailyReport,
  getDailyReport: mocks.getDailyReport,
  listDailyReports: mocks.listDailyReports,
  listProjects: mocks.listProjects,
  updateDailyReport: mocks.updateDailyReport,
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'manager-1', role: 'construction_manager' }),
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))

const listedReport = {
  id: 'report-1',
  projectId: 'project-1',
  title: 'تقرير القائمة',
  summary: 'ملخص القائمة القديم',
  progressPercent: 20,
  workforceCount: 8,
  photoCount: 1,
  authorId: 'manager-1',
  authorName: 'مدير الإنشاءات',
  reportDate: '2026-09-06',
}

const detailedReport = {
  ...listedReport,
  title: 'تقرير التفاصيل الفعلي',
  summary: 'هذه التفاصيل محمّلة مباشرة من واجهة التقرير المفرد.',
  progressPercent: 35,
  workforceCount: 12,
  photoCount: 3,
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DailyReportsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DailyReportsPage detail and edit integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listProjects.mockResolvedValue([
      { id: 'project-1', name: 'مشروع الاختبار', status: 'in_progress' },
    ])
    mocks.listDailyReports.mockResolvedValue([listedReport])
    mocks.getDailyReport.mockResolvedValue(detailedReport)
    mocks.createDailyReport.mockResolvedValue(detailedReport)
    mocks.updateDailyReport.mockResolvedValue(detailedReport)
    mocks.deleteDailyReport.mockResolvedValue(undefined)
  })

  it('loads the report detail from the API when استعراض is opened', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'استعراض' }))

    expect(mocks.getDailyReport).toHaveBeenCalledWith('report-1')
    const dialog = await screen.findByRole('dialog', { name: 'تفاصيل التقرير اليومي' })
    expect(within(dialog).getByText(detailedReport.summary)).toBeInTheDocument()
    expect(within(dialog).queryByText(listedReport.summary)).not.toBeInTheDocument()
    expect(within(dialog).getByText('مدير الإنشاءات')).toBeInTheDocument()
  })

  it('keeps all report actions inside one dedicated card action group', async () => {
    renderPage()

    const title = await screen.findByText(listedReport.title)
    const card = title.closest('article')
    expect(card).not.toBeNull()
    const actions = within(card!).getByLabelText('إجراءات التقرير')
    expect(within(actions).getByRole('button', { name: 'استعراض' })).toBeInTheDocument()
    expect(within(actions).getByRole('button', { name: 'تعديل' })).toBeInTheDocument()
    expect(within(actions).getByRole('button', { name: 'حذف' })).toBeInTheDocument()
  })

  it('loads actual detail values into the edit form', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'تعديل' }))

    expect(mocks.getDailyReport).toHaveBeenCalledWith('report-1')
    const dialog = await screen.findByRole('dialog', { name: 'تعديل التقرير اليومي' })
    expect(await within(dialog).findByDisplayValue(detailedReport.title)).toBeInTheDocument()
    expect(within(dialog).getByLabelText(/^ملخص الأعمال المنجزة/)).toHaveValue(
      detailedReport.summary,
    )
    expect(within(dialog).getByLabelText(/^نسبة الإنجاز/)).toHaveValue(35)
    expect(within(dialog).getByLabelText(/^عدد العمالة/)).toHaveValue(12)
  })

  it('patches an edited report and refreshes the displayed list', async () => {
    const user = userEvent.setup()
    const refreshed = { ...detailedReport, title: 'التقرير بعد التحديث' }
    mocks.updateDailyReport.mockResolvedValue(refreshed)
    mocks.listDailyReports.mockResolvedValueOnce([listedReport]).mockResolvedValue([refreshed])
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'تعديل' }))
    const dialog = await screen.findByRole('dialog', { name: 'تعديل التقرير اليومي' })
    const title = await within(dialog).findByDisplayValue(detailedReport.title)
    await user.clear(title)
    await user.type(title, refreshed.title)
    await user.click(within(dialog).getByRole('button', { name: 'حفظ التعديلات' }))

    await waitFor(() =>
      expect(mocks.updateDailyReport).toHaveBeenCalledWith(
        'report-1',
        expect.objectContaining({ title: refreshed.title, progressPercent: 35 }),
      ),
    )
    expect(await screen.findByText(refreshed.title)).toBeInTheDocument()
    expect(mocks.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ tone: 'success', title: 'تم تحديث التقرير اليومي' }),
    )
  })

  it('shows the existing error state when detail loading fails', async () => {
    const user = userEvent.setup()
    mocks.getDailyReport.mockRejectedValue(new Error('detail access denied'))
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'استعراض' }))

    const dialog = await screen.findByRole('dialog', { name: 'تفاصيل التقرير اليومي' })
    expect(await within(dialog).findByText('detail access denied')).toBeInTheDocument()
  })

  it('shows the existing mutation error feedback when PATCH fails', async () => {
    const user = userEvent.setup()
    mocks.updateDailyReport.mockRejectedValue(new Error('patch access denied'))
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'تعديل' }))
    const dialog = await screen.findByRole('dialog', { name: 'تعديل التقرير اليومي' })
    await within(dialog).findByDisplayValue(detailedReport.title)
    await user.click(within(dialog).getByRole('button', { name: 'حفظ التعديلات' }))

    await waitFor(() =>
      expect(mocks.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ tone: 'critical', description: 'patch access denied' }),
      ),
    )
    expect(dialog).toBeInTheDocument()
  })

  it('preserves the existing create workflow', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: '+ تقرير يومي' }))
    const dialog = screen.getByRole('dialog', { name: 'رفع تقرير يومي' })
    await user.selectOptions(within(dialog).getByLabelText(/^المشروع/), 'project-1')
    await user.type(within(dialog).getByLabelText(/^عنوان التقرير/), 'تقرير يومي جديد')
    await user.clear(within(dialog).getByLabelText(/^تاريخ التقرير/))
    await user.type(within(dialog).getByLabelText(/^تاريخ التقرير/), '2026-09-07')
    await user.type(
      within(dialog).getByLabelText(/^ملخص الأعمال المنجزة/),
      'تم تنفيذ الأعمال المجدولة لهذا اليوم بنجاح.',
    )
    await user.clear(within(dialog).getByLabelText(/^نسبة الإنجاز/))
    await user.type(within(dialog).getByLabelText(/^نسبة الإنجاز/), '40')
    await user.clear(within(dialog).getByLabelText(/^عدد العمالة/))
    await user.type(within(dialog).getByLabelText(/^عدد العمالة/), '14')
    await user.click(within(dialog).getByRole('button', { name: 'رفع التقرير' }))

    await waitFor(() =>
      expect(mocks.createDailyReport).toHaveBeenCalledWith({
        projectId: 'project-1',
        title: 'تقرير يومي جديد',
        reportDate: '2026-09-07',
        summary: 'تم تنفيذ الأعمال المجدولة لهذا اليوم بنجاح.',
        progressPercent: 40,
        workforceCount: 14,
      }),
    )
  })

  it('preserves the existing delete workflow', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'حذف' }))
    const dialog = screen.getByRole('dialog', { name: 'تأكيد حذف التقرير اليومي' })
    await user.click(within(dialog).getByRole('button', { name: 'حذف التقرير' }))

    await waitFor(() => expect(mocks.deleteDailyReport).toHaveBeenCalledWith('report-1'))
  })
})
