// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StagesPage } from './StagesPage'

const mocks = vi.hoisted(() => ({
  createStage: vi.fn(),
  listProjects: vi.fn(),
  listStages: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/api/construction', () => ({
  createStage: mocks.createStage,
  listProjects: mocks.listProjects,
  listStages: mocks.listStages,
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'manager-1', role: 'construction_manager' }),
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))

const project = {
  id: 'project-1',
  name: 'Boundary project',
  status: 'in_progress' as const,
  startDate: '2026-09-05',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StagesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function openAndPopulateForm(startDate: string) {
  const user = userEvent.setup()
  renderPage()
  await user.click(await screen.findByRole('button', { name: /مرحلة جديدة/ }))
  const dialog = screen.getByRole('dialog', { name: 'إضافة مرحلة تنفيذ' })

  await user.selectOptions(within(dialog).getByLabelText(/المشروع/), project.id)
  await user.type(within(dialog).getByLabelText(/اسم المرحلة/), 'Stage 3')
  await user.type(within(dialog).getByLabelText(/وصف المرحلة/), 'Parallel construction stage')
  const startInput = within(dialog).getByLabelText(/تاريخ البداية/)
  await user.type(startInput, startDate)
  await user.type(within(dialog).getByLabelText(/النهاية المتوقعة/), '2026-09-15')
  return { user, dialog, startInput }
}

describe('StagesPage project date boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listProjects.mockResolvedValue([project])
    mocks.listStages.mockResolvedValue([])
    mocks.createStage.mockResolvedValue({ id: 'phase-1', name: 'Stage 3' })
  })

  it('sets the selected project start as the picker minimum and rejects an earlier date', async () => {
    const { user, dialog, startInput } = await openAndPopulateForm('2026-09-01')

    expect(startInput).toHaveAttribute('min', '2026-09-05')
    await user.click(within(dialog).getByRole('button', { name: 'حفظ المرحلة' }))

    expect(
      await within(dialog).findByText('تاريخ بداية المرحلة لا يمكن أن يسبق تاريخ بداية المشروع'),
    ).toBeInTheDocument()
    expect(mocks.createStage).not.toHaveBeenCalled()
  })

  it('allows a stage starting exactly on the project start date', async () => {
    const { user, dialog } = await openAndPopulateForm('2026-09-05')
    await user.click(within(dialog).getByRole('button', { name: 'حفظ المرحلة' }))

    await waitFor(() =>
      expect(mocks.createStage).toHaveBeenCalledWith(
        expect.objectContaining({
          projectId: 'project-1',
          startDate: expect.stringContaining('2026-09-05'),
        }),
      ),
    )
  })
})
