// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StageDetailPage } from './StageDetailPage'

const mocks = vi.hoisted(() => ({
  addStageUpdate: vi.fn(),
  deleteStage: vi.fn(),
  getProject: vi.fn(),
  getStage: vi.fn(),
  listInspections: vi.fn(),
  listStageReviews: vi.fn(),
  listStageUpdates: vi.fn(),
  reviewStage: vi.fn(),
  showToast: vi.fn(),
  updateStage: vi.fn(),
}))

vi.mock('@/api/construction', () => ({
  addStageUpdate: mocks.addStageUpdate,
  deleteStage: mocks.deleteStage,
  getProject: mocks.getProject,
  getStage: mocks.getStage,
  listInspections: mocks.listInspections,
  listStageReviews: mocks.listStageReviews,
  listStageUpdates: mocks.listStageUpdates,
  reviewStage: mocks.reviewStage,
  updateStage: mocks.updateStage,
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'manager-1', role: 'construction_manager' }),
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))

const stage = {
  id: 'phase-1',
  projectId: 'project-1',
  name: 'الأساسات',
  description: 'تنفيذ أعمال الأساسات',
  startDate: '2026-08-01',
  expectedEndDate: '2026-09-01',
  progressPercent: 0,
  priority: 'high' as const,
  status: 'not_started' as const,
  reviewNote: null,
  updatedAt: '2026-08-24T10:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/construction/stages/phase-1']}>
        <Routes>
          <Route path="/construction/stages/:stageId" element={<StageDetailPage />} />
          <Route path="/construction/stages" element={<div>قائمة المراحل</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('StageDetailPage lifecycle controls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getStage.mockResolvedValue(stage)
    mocks.getProject.mockResolvedValue({
      id: 'project-1',
      name: 'مشروع الاختبار',
      startDate: '2026-08-01',
    })
    mocks.listInspections.mockResolvedValue([])
    mocks.listStageUpdates.mockResolvedValue([])
    mocks.listStageReviews.mockResolvedValue([
      {
        id: 'review-1',
        stageId: 'phase-1',
        decision: 'rejected',
        disposition: 'needs_modification',
        reason: 'استكمال مستندات الفحص',
        reviewerId: 'manager-1',
        createdAt: '2026-08-24T09:00:00Z',
      },
    ])
    mocks.updateStage.mockImplementation(async (_id, input) => ({ ...stage, ...input }))
    mocks.deleteStage.mockResolvedValue(undefined)
  })

  it('renders review history and edits phase metadata', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('استكمال مستندات الفحص')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^تعديل$/ }))
    const dialog = screen.getByRole('dialog', { name: 'تعديل بيانات المرحلة' })
    const name = within(dialog).getByLabelText(/اسم المرحلة/)
    const save = within(dialog).getByRole('button', { name: 'حفظ التعديلات' })
    expect(save).toBeEnabled()
    expect(name).toHaveValue('الأساسات')
  })

  it('requires confirmation before deleting an unstarted zero-progress phase', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /^حذف$/ }))
    const dialog = screen.getByRole('dialog', { name: 'تأكيد حذف المرحلة' })
    await user.click(within(dialog).getByRole('button', { name: 'حذف المرحلة' }))

    await waitFor(() => expect(mocks.deleteStage).toHaveBeenCalledWith('phase-1'))
  })

  it('uses the parent project start date as the edit date lower boundary', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /^تعديل$/ }))
    const dialog = screen.getByRole('dialog', { name: 'تعديل بيانات المرحلة' })
    const startDate = within(dialog).getByLabelText(/تاريخ البداية/)
    const save = within(dialog).getByRole('button', { name: 'حفظ التعديلات' })

    expect(startDate).toHaveAttribute('min', '2026-08-01')
    await user.clear(startDate)
    await user.type(startDate, '2026-07-31')

    expect(save).toBeDisabled()
    expect(
      within(dialog).getByText('تاريخ بداية المرحلة لا يمكن أن يسبق تاريخ بداية المشروع'),
    ).toBeInTheDocument()
    expect(mocks.updateStage).not.toHaveBeenCalled()
  })
})
