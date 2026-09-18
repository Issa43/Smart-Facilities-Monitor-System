// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AssetsPage } from './AssetsPage'

const mocks = vi.hoisted(() => ({
  createAsset: vi.fn(),
  getAssetFilterOptions: vi.fn(),
  getAssetMonitoring: vi.fn(),
  listAssetsPage: vi.fn(),
  listFacilities: vi.fn(),
  showToast: vi.fn(),
}))
vi.mock('@/api/operations', () => ({
  createAsset: mocks.createAsset,
  getAssetFilterOptions: mocks.getAssetFilterOptions,
  getAssetMonitoring: mocks.getAssetMonitoring,
  listAssetsPage: mocks.listAssetsPage,
  listFacilities: mocks.listFacilities,
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({
    id: 'manager-1',
    fullName: 'Operations Manager',
    role: 'operations_manager',
  }),
}))

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AssetsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const asset = {
  id: 'asset-1',
  facilityId: '11111111-1111-4111-8111-111111111111',
  name: 'Main Chiller',
  assetType: 'Chiller',
  category: 'custom-hvac',
  manufacturer: 'Carrier',
  model: 'X1',
  locationInFacility: 'Roof',
  serialNumber: 'CH-001',
  installDate: '2026-01-01',
  commissionDate: null,
  status: 'operational',
  notes: '',
  healthScore: 95,
  lastMaintenanceAt: null,
  remainingUsefulLife: 120,
  faultCount: 0,
  createdAt: '2026-01-01T00:00:00Z',
  createdById: 'user-1',
  updatedAt: '2026-01-01T00:00:00Z',
}

describe('AssetsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listFacilities.mockResolvedValue([{ id: asset.facilityId, name: 'Main Facility' }])
    mocks.getAssetFilterOptions.mockResolvedValue({
      assetTypes: ['Chiller'],
      categories: ['custom-hvac'],
      manufacturers: ['Carrier'],
    })
    mocks.getAssetMonitoring.mockResolvedValue({
      total: 1,
      averageHealthScore: 95,
      statusCounts: { operational: 1, under_maintenance: 0, out_of_service: 0 },
    })
    mocks.listAssetsPage.mockResolvedValue({
      count: 1,
      totalPages: 1,
      currentPage: 1,
      pageSize: 20,
      results: [asset],
    })
    mocks.createAsset.mockResolvedValue(asset)
  })

  it('renders backend asset type and sends typed custom values on create without a status', async () => {
    const user = userEvent.setup()
    renderPage()
    expect((await screen.findAllByText('Chiller')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('custom-hvac').length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: '+ أصل جديد' }))
    const form = within(screen.getByRole('dialog'))
    await user.selectOptions(form.getByLabelText(/^المنشأة/), asset.facilityId)
    await user.type(form.getByLabelText(/^اسم الأصل/), 'Backup Generator')
    await user.type(form.getByLabelText(/^نوع الأصل/), 'Generator')
    await user.type(form.getByLabelText(/^فئة الأصل/), 'power-custom')
    await user.type(form.getByLabelText(/^الشركة المصنعة/), 'CAT')
    await user.type(form.getByLabelText(/^الطراز/), 'G1')
    await user.type(form.getByLabelText(/^الموقع داخل المنشأة/), 'Yard')
    await user.type(form.getByLabelText(/^الرقم التسلسلي/), 'GEN-1')
    await user.type(form.getByLabelText(/^تاريخ التركيب/), '2026-01-01')
    await user.click(form.getByRole('button', { name: 'حفظ الأصل' }))
    await waitFor(() => expect(mocks.createAsset).toHaveBeenCalled())
    expect(mocks.createAsset.mock.calls[0]?.[0]).toMatchObject({
      assetType: 'Generator',
      category: 'power-custom',
      facilityId: asset.facilityId,
    })
    expect(mocks.createAsset.mock.calls[0]?.[0]).not.toHaveProperty('status')
  })

  it('sends server-side type, facility, and status filters and shows loading errors honestly', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Main Chiller')
    await user.selectOptions(screen.getByLabelText('نوع الأصل'), 'Chiller')
    await user.selectOptions(screen.getByLabelText('الحالة'), 'operational')
    await user.selectOptions(screen.getByLabelText('المنشأة'), asset.facilityId)
    await waitFor(() =>
      expect(mocks.listAssetsPage).toHaveBeenLastCalledWith(
        expect.objectContaining({
          assetType: 'Chiller',
          status: 'operational',
          facilityId: asset.facilityId,
        }),
      ),
    )
  })

  it('renders a create API error instead of closing the form', async () => {
    mocks.createAsset.mockRejectedValue(new Error('serial_number: already exists'))
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '+ أصل جديد' }))
    const form = within(screen.getByRole('dialog'))
    fireEvent.change(form.getByLabelText(/^المنشأة/), { target: { value: asset.facilityId } })
    for (const [label, value] of [
      ['اسم الأصل', 'Backup Generator'],
      ['نوع الأصل', 'Generator'],
      ['فئة الأصل', 'power'],
      ['الشركة المصنعة', 'CAT'],
      ['الطراز', 'G1'],
      ['الموقع داخل المنشأة', 'Yard'],
      ['الرقم التسلسلي', 'GEN-1'],
    ] as const)
      fireEvent.change(form.getByLabelText(new RegExp(`^${label}`)), { target: { value } })
    fireEvent.change(form.getByLabelText(/^تاريخ التركيب/), { target: { value: '2026-01-01' } })
    await user.click(form.getByRole('button', { name: 'حفظ الأصل' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('serial_number: already exists')
  })
})
