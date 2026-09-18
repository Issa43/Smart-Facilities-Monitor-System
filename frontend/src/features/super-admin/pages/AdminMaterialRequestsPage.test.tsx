// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminMaterialRequestsPage } from './AdminMaterialRequestsPage'

const mocks = vi.hoisted(() => ({
  getMaterialRequest: vi.fn(),
  listMaterialRequests: vi.fn(),
  setMaterialRequestStatus: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/api/construction', () => ({
  getMaterialRequest: mocks.getMaterialRequest,
  listMaterialRequests: mocks.listMaterialRequests,
  setMaterialRequestStatus: mocks.setMaterialRequestStatus,
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'admin-1', role: 'super_admin' }),
}))

const pendingRequest = {
  id: 'request-12345678',
  projectId: 'project-1',
  projectName: 'مشروع المطار',
  materialId: 'material-1',
  materialName: 'أسمنت',
  requestedQty: 25,
  unit: 'كيس',
  reason: 'استكمال أعمال المرحلة الحالية',
  priority: 'high' as const,
  status: 'pending' as const,
  requestedById: 'manager-1',
  requestedByName: 'خالد أحمد',
  createdAt: '2026-09-12T10:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminMaterialRequestsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AdminMaterialRequestsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listMaterialRequests.mockResolvedValue([pendingRequest])
    mocks.getMaterialRequest.mockResolvedValue(pendingRequest)
  })

  it('lists reviewable requests and loads their details', async () => {
    renderPage()
    expect(await screen.findByText('مشروع المطار')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'اعتماد' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'رفض' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'استعراض' }))
    await waitFor(() => expect(mocks.getMaterialRequest).toHaveBeenCalledWith(pendingRequest.id))
    expect(await screen.findByText('استكمال أعمال المرحلة الحالية')).toBeInTheDocument()
  })

  it.each([
    ['اعتماد', 'approved'],
    ['رفض', 'rejected'],
  ] as const)('submits %s and refreshes the displayed state', async (label, status) => {
    mocks.setMaterialRequestStatus.mockResolvedValue({ ...pendingRequest, status })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: label }))

    await waitFor(() =>
      expect(mocks.setMaterialRequestStatus).toHaveBeenCalledWith(pendingRequest.id, status),
    )
    expect(mocks.showToast).toHaveBeenCalled()
  })

  it('shows API errors and hides invalid actions for terminal states', async () => {
    mocks.listMaterialRequests.mockResolvedValue([{ ...pendingRequest, status: 'rejected' }])
    renderPage()
    expect(await screen.findByText('مرفوض')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'اعتماد' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'رفض' })).not.toBeInTheDocument()

    mocks.listMaterialRequests.mockRejectedValueOnce(new Error('تعذر الاتصال'))
    renderPage()
    expect(await screen.findByText('تعذر الاتصال')).toBeInTheDocument()
  })
})
