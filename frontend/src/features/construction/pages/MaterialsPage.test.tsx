// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MaterialsPage } from './MaterialsPage'

const mocks = vi.hoisted(() => ({
  consumeMaterial: vi.fn(),
  createMaterial: vi.fn(),
  deleteMaterial: vi.fn(),
  listMaterials: vi.fn(),
  listMaterialConsumption: vi.fn(),
  listProjects: vi.fn(),
  showToast: vi.fn(),
  updateMaterial: vi.fn(),
}))

vi.mock('@/api/construction', () => ({
  consumeMaterial: mocks.consumeMaterial,
  createMaterial: mocks.createMaterial,
  deleteMaterial: mocks.deleteMaterial,
  listMaterials: mocks.listMaterials,
  listMaterialConsumption: mocks.listMaterialConsumption,
  listProjects: mocks.listProjects,
  updateMaterial: mocks.updateMaterial,
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'manager-1', role: 'construction_manager' }),
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))

const material = {
  id: 'material-1',
  projectId: 'project-1',
  name: 'أسمنت',
  unit: 'bag',
  requiredQty: 10,
  usedQty: 6,
  remainingQty: 4,
  minStockThreshold: 4,
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/construction/materials?material=material-1']}>
        <MaterialsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MaterialsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listProjects.mockResolvedValue([
      { id: 'project-1', name: 'المشروع', status: 'in_progress' },
    ])
    mocks.listMaterials.mockResolvedValue([
      material,
      { ...material, id: 'material-2', name: 'حديد' },
    ])
    mocks.listMaterialConsumption.mockResolvedValue([])
  })

  it('targets notification navigation and exposes safe edit, consumption, and delete controls', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText('أسمنت')).toBeInTheDocument()
    expect(screen.queryByText('حديد')).not.toBeInTheDocument()
    expect(screen.getByText('تحت الحد')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'تعديل' }))
    const editDialog = screen.getByRole('dialog', { name: 'تعديل مادة' })
    expect(within(editDialog).getByLabelText(/المشروع/)).toBeDisabled()
    expect(within(editDialog).getByLabelText(/وحدة القياس/)).toHaveValue('bag')
    await user.click(within(editDialog).getByRole('button', { name: 'إلغاء' }))

    await user.click(screen.getByRole('button', { name: 'تسجيل استهلاك' }))
    expect(screen.getByRole('dialog', { name: 'تسجيل استهلاك مادة' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'إلغاء' }))

    await user.click(screen.getByRole('button', { name: 'حذف' }))
    expect(screen.getByRole('dialog', { name: 'تأكيد حذف المادة' })).toBeInTheDocument()
  })

  it('shows dependent query failures instead of an empty materials success state', async () => {
    mocks.listProjects.mockRejectedValue(new Error('projects unavailable'))

    renderPage()

    expect(await screen.findByText('projects unavailable')).toBeInTheDocument()
  })

  it('shows a critical toast when a material action is rejected', async () => {
    const user = userEvent.setup()
    mocks.deleteMaterial.mockRejectedValue(new Error('material has protected history'))
    renderPage()

    await user.click(await screen.findByRole('button', { name: /^حذف$/ }))
    const dialog = screen.getByRole('dialog', { name: 'تأكيد حذف المادة' })
    await user.click(within(dialog).getByRole('button', { name: 'حذف المادة' }))

    await waitFor(() =>
      expect(mocks.showToast).toHaveBeenCalledWith(
        expect.objectContaining({
          tone: 'critical',
          description: 'material has protected history',
        }),
      ),
    )
  })
})
