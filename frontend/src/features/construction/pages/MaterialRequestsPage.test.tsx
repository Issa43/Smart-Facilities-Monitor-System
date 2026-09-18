// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MaterialRequestsPage } from './MaterialRequestsPage'

const mocks = vi.hoisted(() => ({
  listMaterialRequests: vi.fn(),
  listProjects: vi.fn(),
  setMaterialRequestStatus: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/api/construction', () => ({
  listMaterialRequests: mocks.listMaterialRequests,
  listProjects: mocks.listProjects,
  setMaterialRequestStatus: mocks.setMaterialRequestStatus,
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'manager-1', role: 'construction_manager' }),
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MaterialRequestsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('MaterialRequestsPage approval boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listProjects.mockResolvedValue([{ id: 'project-1', name: 'المشروع' }])
    const request = {
      id: 'request-1',
      projectId: 'project-1',
      projectName: 'المشروع',
      materialId: 'material-1',
      materialName: 'أسمنت',
      requestedQty: 5,
      unit: 'كيس',
      reason: 'مطلوب لاستمرار التنفيذ',
      priority: 'high',
      status: 'pending',
      requestedById: 'manager-1',
      requestedByName: 'مدير الإنشاء',
      createdAt: '2026-08-24T10:00:00Z',
    }
    mocks.listMaterialRequests.mockResolvedValue([
      request,
      { ...request, id: 'request-2', requestedById: 'manager-2' },
    ])
  })

  it('shows every pending request as awaiting Super Admin without decision actions', async () => {
    renderPage()

    expect(await screen.findAllByText('بانتظار اعتماد المسؤول')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'اعتماد' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'رفض' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /طلب جديد/ })).toHaveAttribute(
      'href',
      '/construction/material-requests/new',
    )
  })
})
