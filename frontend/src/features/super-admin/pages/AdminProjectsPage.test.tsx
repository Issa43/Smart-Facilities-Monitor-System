// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminProjectsPage } from './AdminProjectsPage'

const mocks = vi.hoisted(() => ({
  listProjects: vi.fn(),
  listUsers: vi.fn(),
  getFacilityCameraRequirement: vi.fn(),
  setFacilityCameraRequirement: vi.fn(),
  showToast: vi.fn(),
}))
vi.mock('@/api/construction', () => ({ listProjects: mocks.listProjects }))
vi.mock('@/api/users', () => ({ listUsers: mocks.listUsers }))
vi.mock('@/api/operations', () => ({
  getFacilityCameraRequirement: mocks.getFacilityCameraRequirement,
  setFacilityCameraRequirement: mocks.setFacilityCameraRequirement,
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))
vi.mock('@/context/AuthContext', () => {
  const user = { id: 'admin-1', fullName: 'Super Admin', role: 'super_admin' }
  return { useAuth: () => ({ user }), useCurrentUser: () => user }
})

const project = (overrides: Record<string, unknown> = {}) => ({
  id: 'project-1',
  name: 'Operational Tower',
  facilityType: 'commercial',
  description: '',
  location: 'Amman',
  latitude: null,
  longitude: null,
  startDate: '2026-01-01',
  expectedEndDate: '2026-06-01',
  status: 'operational',
  imageUrl: null,
  constructionManagerId: 'manager-1',
  progressPercent: 100,
  currentStageName: '—',
  updatedAt: '2026-06-01T00:00:00Z',
  facilityId: 'facility-1',
  ...overrides,
})

const requirement = {
  facilityId: 'facility-1',
  requiredCameraCount: null,
  previousRequiredCameraCount: null,
  existing: 0,
  created: 0,
  surplus: 0,
  cameraCount: 0,
  createdCameraIds: [],
  cameras: [],
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AdminProjectsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AdminProjectsPage camera requirement editor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mocks.listUsers.mockResolvedValue([])
    mocks.getFacilityCameraRequirement.mockResolvedValue(requirement)
  })

  it('edits the required count of an operational project through its facility', async () => {
    mocks.listProjects.mockResolvedValue([
      project(),
      project({ id: 'project-2', name: 'Planned Site', status: 'planning', facilityId: null }),
    ])
    mocks.setFacilityCameraRequirement.mockResolvedValue({
      ...requirement,
      requiredCameraCount: 4,
      created: 4,
      cameraCount: 4,
    })
    renderPage()

    const trigger = await screen.findByRole('button', { name: /Operational Tower/ })
    expect(screen.queryByRole('button', { name: /Planned Site/ })).toBeNull()
    await userEvent.click(trigger)
    await userEvent.type(await screen.findByLabelText(/عدد الكاميرات المطلوب/), '4')
    await userEvent.click(screen.getByRole('button', { name: 'حفظ' }))

    await waitFor(() =>
      expect(mocks.setFacilityCameraRequirement).toHaveBeenCalledWith('facility-1', 4),
    )
    expect(mocks.getFacilityCameraRequirement).toHaveBeenCalledWith('facility-1')
  })

  it('shows no editor when no project is operational', async () => {
    mocks.listProjects.mockResolvedValue([project({ status: 'in_progress', facilityId: null })])
    renderPage()

    await screen.findAllByText('Operational Tower')
    expect(screen.queryByText('كاميرات المشاريع التشغيلية')).toBeNull()
  })
})
