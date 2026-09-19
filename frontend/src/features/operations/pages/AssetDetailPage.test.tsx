// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AssetDetailPage } from './AssetDetailPage'

const mocks = vi.hoisted(() => ({
  getAsset: vi.fn(),
  getFacility: vi.fn(),
  getAssetFilterOptions: vi.fn(),
  listFaults: vi.fn(),
  listWorkOrders: vi.fn(),
  transitionAssetStatus: vi.fn(),
  updateAsset: vi.fn(),
  showToast: vi.fn(),
}))
vi.mock('@/api/operations', () => mocks)
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'manager-1', fullName: 'Manager', role: 'operations_manager' }),
}))

const asset = {
  id: 'asset-1',
  facilityId: 'facility-1',
  name: 'Main Chiller',
  assetType: 'Chiller',
  category: 'custom-hvac',
  manufacturer: 'Carrier',
  model: 'X1',
  locationInFacility: 'Roof',
  serialNumber: 'CH-001',
  installDate: '2026-01-01',
  commissionDate: null,
  status: 'out_of_service',
  notes: 'Stable',
  healthScore: 91,
  lastMaintenanceAt: null,
  remainingUsefulLife: 120,
  faultCount: 0,
  createdAt: '2026-01-01T00:00:00Z',
  createdById: 'user-1',
  updatedAt: '2026-08-01T00:00:00Z',
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/operations/assets/asset-1']}>
        <Routes>
          <Route path="/operations/assets/:assetId" element={<AssetDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AssetDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getAsset.mockResolvedValue(asset)
    mocks.getFacility.mockResolvedValue({ id: 'facility-1', name: 'Main Facility' })
    mocks.getAssetFilterOptions.mockResolvedValue({
      assetTypes: ['Chiller'],
      categories: ['custom-hvac'],
      manufacturers: ['Carrier'],
    })
    mocks.listFaults.mockResolvedValue([])
    mocks.listWorkOrders.mockResolvedValue([])
    mocks.updateAsset.mockResolvedValue({ ...asset, name: 'Updated Chiller' })
    mocks.transitionAssetStatus.mockResolvedValue({ ...asset, status: 'under_maintenance' })
  })

  it('shows canonical fields and only backend-allowed lifecycle actions', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Main Chiller' })).toBeInTheDocument()
    expect(screen.getAllByText('Chiller').length).toBeGreaterThan(0)
    expect(screen.getByText('Carrier / X1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'تحت الصيانة' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'يعمل' })).not.toBeInTheDocument()
    expect(mocks.listWorkOrders).toHaveBeenCalledWith(undefined, 'asset-1')
    expect(mocks.listFaults).toHaveBeenCalledWith(undefined, 'asset-1')
  })

  it('preserves existing values in edit and submits the canonical patch', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'تعديل الأصل' }))
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByLabelText(/^نوع الأصل/)).toHaveValue('Chiller')
    expect(dialog.getByLabelText(/^الشركة المصنعة/)).toHaveValue('Carrier')
    const name = dialog.getByLabelText(/^اسم الأصل/)
    await user.clear(name)
    await user.type(name, 'Updated Chiller')
    await user.click(dialog.getByRole('button', { name: 'حفظ التعديلات' }))
    await waitFor(() =>
      expect(mocks.updateAsset).toHaveBeenCalledWith(
        'asset-1',
        expect.objectContaining({
          name: 'Updated Chiller',
          assetType: 'Chiller',
          category: 'custom-hvac',
        }),
      ),
    )
  })
})
