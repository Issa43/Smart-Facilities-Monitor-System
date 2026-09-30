// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CameraMonitoringPage } from './CameraMonitoringPage'

const mocks = vi.hoisted(() => ({
  listCameras: vi.fn(),
  listSecurityFacilities: vi.fn(),
  reportCameraMaintenance: vi.fn(),
  showToast: vi.fn(),
  role: 'security_officer',
}))
vi.mock('@/api/security', () => ({
  listCameras: mocks.listCameras,
  listSecurityFacilities: mocks.listSecurityFacilities,
  reportCameraMaintenance: mocks.reportCameraMaintenance,
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'user-1', fullName: 'User', role: mocks.role }),
}))

const camera = {
  id: 'cam-1',
  name: 'Gate Camera',
  code: 'CAM-GATE-001',
  zone: 'North gate',
  facilityId: 'facility-1',
  status: 'offline',
  online: false,
  streamAvailable: false,
  lastSeenAt: null,
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CameraMonitoringPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CameraMonitoringPage maintenance reporting', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.role = 'security_officer'
    mocks.listCameras.mockResolvedValue([camera])
    mocks.listSecurityFacilities.mockResolvedValue([{ id: 'facility-1', name: 'Main Facility' }])
  })

  it('lets a Security Officer report a camera and shows the fault reference', async () => {
    mocks.reportCameraMaintenance.mockResolvedValue({
      id: 'fault-1',
      reference: 'FLT-ABC123',
      cameraId: 'cam-1',
      status: 'reported',
      severity: 'high',
      description: 'Lens cracked',
      created: true,
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: /الإبلاغ عن صيانة/ }))
    const submit = screen.getByRole('button', { name: 'إرسال البلاغ' })
    expect((submit as HTMLButtonElement).disabled).toBe(true)
    await userEvent.type(screen.getByLabelText(/وصف المشكلة/), 'Lens cracked')
    await userEvent.selectOptions(screen.getByLabelText('الخطورة'), 'high')
    await userEvent.click(submit)

    await waitFor(() =>
      expect(mocks.reportCameraMaintenance).toHaveBeenCalledWith('cam-1', {
        description: 'Lens cracked',
        severity: 'high',
      }),
    )
    expect(await screen.findByText('أُنشئ البلاغ FLT-ABC123')).toBeTruthy()
    // Only reporting is offered: no workflow controls the officer cannot use.
    expect(screen.queryByRole('button', { name: /أمر صيانة|تحقيق|إغلاق العطل/ })).toBeNull()
  })

  it('shows the already-open report instead of a new one', async () => {
    mocks.reportCameraMaintenance.mockResolvedValue({
      id: 'fault-1',
      reference: 'FLT-ABC123',
      cameraId: 'cam-1',
      status: 'reported',
      severity: 'medium',
      description: 'Lens cracked',
      created: false,
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: /الإبلاغ عن صيانة/ }))
    await userEvent.type(screen.getByLabelText(/وصف المشكلة/), 'Still broken')
    await userEvent.click(screen.getByRole('button', { name: 'إرسال البلاغ' }))

    expect(await screen.findByText('البلاغ FLT-ABC123 مفتوح مسبقاً لهذه الكاميرا')).toBeTruthy()
  })

  it('shows the server error when the report fails', async () => {
    mocks.reportCameraMaintenance.mockRejectedValue(new Error('Faults require an active asset.'))
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: /الإبلاغ عن صيانة/ }))
    await userEvent.type(screen.getByLabelText(/وصف المشكلة/), 'Broken')
    await userEvent.click(screen.getByRole('button', { name: 'إرسال البلاغ' }))

    expect(await screen.findByText('Faults require an active asset.')).toBeTruthy()
  })

  it('hides the report action from roles without the grant', async () => {
    mocks.role = 'operations_manager'
    renderPage()

    expect(await screen.findByText('CAM-GATE-001')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /الإبلاغ عن صيانة/ })).toBeNull()
  })
})
