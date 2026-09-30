// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FacilityCameraRequirementPanel } from './FacilityCameraRequirementPanel'
import { validateRequiredCameraCount } from './cameraRequirement'

const mocks = vi.hoisted(() => ({
  getFacilityCameraRequirement: vi.fn(),
  setFacilityCameraRequirement: vi.fn(),
  showToast: vi.fn(),
}))
vi.mock('@/api/operations', () => ({
  getFacilityCameraRequirement: mocks.getFacilityCameraRequirement,
  setFacilityCameraRequirement: mocks.setFacilityCameraRequirement,
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))

const camera = (n: number) => ({
  id: `cam-${n}`,
  facilityId: 'facility-1',
  assetId: `asset-${n}`,
  code: `CAM-ABCDEF012345-00${n}`,
  name: `Camera 00${n}`,
  zone: 'Unassigned',
  status: 'offline' as const,
  lastSeenAt: null,
  createdAt: '2026-09-01T00:00:00Z',
})

const requirement = (overrides: Record<string, unknown> = {}) => ({
  facilityId: 'facility-1',
  requiredCameraCount: 3,
  previousRequiredCameraCount: 3,
  existing: 3,
  created: 0,
  surplus: 0,
  cameraCount: 3,
  createdCameraIds: [],
  cameras: [camera(1), camera(2), camera(3)],
  ...overrides,
})

function renderPanel(props: { showCameras?: boolean } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <FacilityCameraRequirementPanel facilityId="facility-1" {...props} />
    </QueryClientProvider>,
  )
}

describe('FacilityCameraRequirementPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getFacilityCameraRequirement.mockResolvedValue(requirement())
  })

  it('shows the current requirement and the facility cameras', async () => {
    renderPanel()

    expect(await screen.findByDisplayValue('3')).toBeTruthy()
    expect(screen.getByText('CAM-ABCDEF012345-001')).toBeTruthy()
    expect(screen.queryByText(/كاميرا فائضة/)).toBeNull()
  })

  it('saves the absolute count and reports how many cameras were created', async () => {
    const saved = requirement({
      requiredCameraCount: 5,
      previousRequiredCameraCount: 3,
      created: 2,
      cameraCount: 5,
      cameras: [1, 2, 3, 4, 5].map(camera),
    })
    mocks.setFacilityCameraRequirement.mockResolvedValue(saved)
    renderPanel()
    const input = await screen.findByDisplayValue('3')
    // After saving, the invalidated query refetches the server's new state.
    mocks.getFacilityCameraRequirement.mockResolvedValue({ ...saved, created: 0 })

    await userEvent.clear(input)
    await userEvent.type(input, '5')
    await userEvent.click(screen.getByRole('button', { name: 'حفظ' }))

    await waitFor(() =>
      expect(mocks.setFacilityCameraRequirement).toHaveBeenCalledWith('facility-1', 5),
    )
    expect(await screen.findByText('أُضيفت في آخر حفظ')).toBeTruthy()
    expect(await screen.findByText('CAM-ABCDEF012345-005')).toBeTruthy()
    expect(mocks.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ tone: 'success', description: expect.stringContaining('2') }),
    )
  })

  it('warns about surplus cameras without offering to delete them', async () => {
    mocks.getFacilityCameraRequirement.mockResolvedValue(
      requirement({ requiredCameraCount: 1, surplus: 2 }),
    )
    renderPanel()

    expect(await screen.findByText(/2 كاميرا فائضة|٢ كاميرا فائضة/)).toBeTruthy()
    expect(screen.getByText(/لا تُحذف الكاميرات تلقائياً/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /حذف/ })).toBeNull()
  })

  it('blocks invalid values before calling the server', async () => {
    renderPanel()
    const input = await screen.findByDisplayValue('3')

    await userEvent.clear(input)
    await userEvent.type(input, '201')
    await userEvent.click(screen.getByRole('button', { name: 'حفظ' }))

    expect(await screen.findByText(/الحد الأعلى/)).toBeTruthy()
    expect(mocks.setFacilityCameraRequirement).not.toHaveBeenCalled()
  })

  it('shows the server error when saving fails', async () => {
    mocks.setFacilityCameraRequirement.mockRejectedValue(
      new Error('Cameras cannot be provisioned for a decommissioned facility.'),
    )
    renderPanel()
    await screen.findByDisplayValue('3')

    await userEvent.click(screen.getByRole('button', { name: 'حفظ' }))

    await waitFor(() =>
      expect(mocks.showToast).toHaveBeenCalledWith(
        expect.objectContaining({
          tone: 'critical',
          description: 'Cameras cannot be provisioned for a decommissioned facility.',
        }),
      ),
    )
  })

  it('can hide the camera table', async () => {
    renderPanel({ showCameras: false })

    await screen.findByDisplayValue('3')
    expect(screen.queryByText('CAM-ABCDEF012345-001')).toBeNull()
  })
})

describe('validateRequiredCameraCount', () => {
  it('accepts 0 through 200 and rejects everything else', () => {
    expect(validateRequiredCameraCount('0')).toBeNull()
    expect(validateRequiredCameraCount('200')).toBeNull()
    expect(validateRequiredCameraCount('')).not.toBeNull()
    expect(validateRequiredCameraCount('-1')).not.toBeNull()
    expect(validateRequiredCameraCount('2.5')).not.toBeNull()
    expect(validateRequiredCameraCount('201')).not.toBeNull()
  })
})
