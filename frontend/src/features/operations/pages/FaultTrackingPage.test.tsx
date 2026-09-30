// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { faultTypeLabel } from '@/types'
import { FaultTrackingPage } from './FaultTrackingPage'

const mocks = vi.hoisted(() => ({
  listFaults: vi.fn(),
  listAssets: vi.fn(),
  listFacilities: vi.fn(),
  listUsers: vi.fn(),
}))
vi.mock('@/api/operations', () => ({
  createFault: vi.fn(),
  listAssets: mocks.listAssets,
  listFacilities: mocks.listFacilities,
  listFaults: mocks.listFaults,
  resolveFault: vi.fn(),
  setFaultStatus: vi.fn(),
}))
vi.mock('@/api/users', () => ({ listUsers: mocks.listUsers }))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('@/context/AuthContext', () => {
  const user = { id: 'manager-1', fullName: 'Operations Manager', role: 'operations_manager' }
  return { useAuth: () => ({ user }), useCurrentUser: () => user }
})

const fault = (overrides: Record<string, unknown>) => ({
  id: 'fault-1',
  reference: 'FLT-CAM0001',
  assetId: 'asset-1',
  facilityId: 'facility-1',
  faultType: 'camera_maintenance',
  description: 'Lens cracked',
  severity: 'high',
  rootCause: null,
  resolution: null,
  status: 'reported',
  assignedToId: null,
  discoveredAt: '2026-09-01T00:00:00Z',
  resolvedAt: null,
  ...overrides,
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FaultTrackingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('FaultTrackingPage fault type labels', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listAssets.mockResolvedValue([])
    mocks.listFacilities.mockResolvedValue([])
    mocks.listUsers.mockResolvedValue([])
    mocks.listFaults.mockResolvedValue([
      fault({}),
      fault({ id: 'fault-2', reference: 'FLT-MANUAL01', faultType: 'تسرب غاز تبريد' }),
    ])
  })

  it('shows the camera maintenance code as a readable label, and free-text types as typed', async () => {
    renderPage()

    expect(await screen.findByText('صيانة كاميرا')).toBeTruthy()
    expect(screen.queryByText('camera_maintenance')).toBeNull()
    expect(screen.getByText('تسرب غاز تبريد')).toBeTruthy()
  })

  it('maps only the known code and passes every other value through', () => {
    expect(faultTypeLabel('camera_maintenance')).toBe('صيانة كاميرا')
    expect(faultTypeLabel('عطل ميكانيكي')).toBe('عطل ميكانيكي')
    expect(faultTypeLabel('')).toBe('')
  })
})
