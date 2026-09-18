// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { safetyAlertFromDto, type SafetyAlertDto } from '@/api/adapters/safety'
import { alertDto } from '@/test/safetyFixtures'
import { SafetyAlertDetailPage } from './SafetyAlertDetailPage'

const mocks = vi.hoisted(() => ({
  getSafetyAlert: vi.fn(),
  acknowledgeSafetyAlert: vi.fn(),
  decideSafetyAlert: vi.fn(),
  dismissSafetyAlert: vi.fn(),
  closeSafetyAlert: vi.fn(),
  showToast: vi.fn(),
}))
vi.mock('@/api/safety', () => ({
  getSafetyAlert: mocks.getSafetyAlert,
  acknowledgeSafetyAlert: mocks.acknowledgeSafetyAlert,
  decideSafetyAlert: mocks.decideSafetyAlert,
  dismissSafetyAlert: mocks.dismissSafetyAlert,
  closeSafetyAlert: mocks.closeSafetyAlert,
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({
    id: 'cm-1',
    fullName: 'Construction Manager',
    role: 'construction_manager',
  }),
}))

const ALERT_ID = '11111111-1111-4111-8111-111111111111'
const model = (overrides: Partial<SafetyAlertDto> = {}) => safetyAlertFromDto(alertDto(overrides))

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/construction/safety-alerts/${ALERT_ID}`]}>
        <Routes>
          <Route path="/construction/safety-alerts/:alertId" element={<SafetyAlertDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const actionButtons = () =>
  ['إقرار الاطلاع', 'تسجيل القرار', 'إغلاق الإنذار', 'استبعاد الإنذار'].filter((name) =>
    screen.queryByRole('button', { name }),
  )

beforeEach(() => {
  mocks.getSafetyAlert.mockResolvedValue(model())
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('no direct network access in tests'))),
  )
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('SafetyAlertDetailPage', () => {
  it('renders alert, project, hazard, and decision data without raw payload', async () => {
    const { container } = renderPage()

    expect(
      await screen.findByRole('heading', { name: 'M 6.0 - Synthetic region' }),
    ).toBeInTheDocument()
    expect(mocks.getSafetyAlert).toHaveBeenCalledWith(ALERT_ID)
    expect(screen.getByText(ALERT_ID)).toBeInTheDocument()
    expect(screen.getByText('خطورة عالية')).toBeInTheDocument()
    expect(screen.getByText('earthquake.m5_5_r100')).toBeInTheDocument()
    expect(screen.getByText('30.044400, 31.235700')).toBeInTheDocument()
    expect(screen.getByText('us7000test')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getByText('M6.0 mww')).toBeInTheDocument()
    expect(screen.getByText('التوصية استرشادية')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/payload|\{"|mag":/)
    const link = screen.getByRole('link', { name: 'فتح صفحة المصدر (موقع خارجي)' })
    expect(link).toHaveAttribute(
      'href',
      'https://earthquake.usgs.gov/earthquakes/eventpage/us7000test',
    )
    expect(link).toHaveAttribute('rel', 'noopener noreferrer nofollow')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('does not link unapproved provider URLs', async () => {
    mocks.getSafetyAlert.mockResolvedValue(
      model({
        hazard_event: { ...alertDto().hazard_event, source_url: 'https://evil.example/phish' },
      }),
    )
    renderPage()
    await screen.findByRole('heading', { name: 'M 6.0 - Synthetic region' })
    expect(screen.queryByRole('link', { name: /صفحة المصدر/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/evil\.example/)).not.toBeInTheDocument()
  })

  it.each([
    [
      ['acknowledge', 'dismiss'],
      ['إقرار الاطلاع', 'استبعاد الإنذار'],
    ],
    [
      ['decide', 'close'],
      ['تسجيل القرار', 'إغلاق الإنذار'],
    ],
    [
      ['decide', 'dismiss'],
      ['تسجيل القرار', 'استبعاد الإنذار'],
    ],
    [[], []],
  ])('renders controls only from available_actions %j', async (available, expected) => {
    mocks.getSafetyAlert.mockResolvedValue(model({ available_actions: available as string[] }))
    renderPage()
    await screen.findByRole('heading', { name: 'M 6.0 - Synthetic region' })
    expect(actionButtons()).toEqual(expected)
    if (!available.length) {
      expect(
        screen.getByText('لا توجد إجراءات متاحة لك على هذا الإنذار في حالته الحالية.'),
      ).toBeInTheDocument()
    }
  })

  it('keeps withdrawn alerts actionable when the server says so', async () => {
    mocks.getSafetyAlert.mockResolvedValue(
      model({
        hazard_withdrawn_at: '2026-09-15T13:00:00Z',
        available_actions: ['acknowledge', 'dismiss'],
      }),
    )
    renderPage()
    expect(await screen.findByText('أفاد المصدر بسحب هذا الحدث')).toBeInTheDocument()
    expect(actionButtons()).toEqual(['إقرار الاطلاع', 'استبعاد الإنذار'])
  })

  it('acknowledges and renders the server response, including an idempotent 200', async () => {
    const user = userEvent.setup()
    mocks.acknowledgeSafetyAlert.mockResolvedValue(
      model({
        status: 'acknowledged',
        acknowledged_by: { id: 'cm-1', full_name: 'Construction Manager' },
        acknowledged_at: '2026-09-15T12:10:00Z',
        available_actions: ['decide', 'dismiss'],
      }),
    )
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'إقرار الاطلاع' }))

    expect(mocks.acknowledgeSafetyAlert).toHaveBeenCalledWith(ALERT_ID)
    expect(await screen.findByText('تم الإقرار')).toBeInTheDocument()
    expect(screen.getByText('Construction Manager')).toBeInTheDocument()
    expect(actionButtons()).toEqual(['تسجيل القرار', 'استبعاد الإنذار'])
    expect(mocks.showToast).toHaveBeenCalledWith({
      tone: 'success',
      title: 'تم إقرار الاطلاع على الإنذار',
    })
  })

  it('requires notes for the "other" decision and sends the exact contract', async () => {
    const user = userEvent.setup()
    mocks.getSafetyAlert.mockResolvedValue(
      model({ status: 'acknowledged', available_actions: ['decide', 'dismiss'] }),
    )
    mocks.decideSafetyAlert.mockResolvedValue(
      model({
        status: 'actioned',
        decision: 'other',
        decision_notes: 'Delay concrete pour',
        available_actions: ['decide', 'close'],
      }),
    )
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'تسجيل القرار' }))

    const dialog = within(screen.getByRole('dialog'))
    const save = dialog.getByRole('button', { name: 'حفظ القرار' })
    expect(save).toBeDisabled()
    expect(dialog.getAllByRole('option').map((option) => option.getAttribute('value'))).toEqual([
      '',
      'suspend_outdoor_work',
      'delay_shift',
      'modify_working_hours',
      'increase_precautions',
      'inspect_site',
      'monitor',
      'other',
    ])
    await user.selectOptions(dialog.getByLabelText(/القرار/), 'other')
    expect(save).toBeDisabled()
    await user.type(dialog.getByLabelText(/ملاحظات/), 'Delay concrete pour')
    expect(save).toBeEnabled()
    await user.click(save)

    expect(mocks.decideSafetyAlert).toHaveBeenCalledWith(ALERT_ID, {
      decision: 'other',
      notes: 'Delay concrete pour',
    })
    expect(await screen.findByText('Delay concrete pour')).toBeInTheDocument()
  })

  it('requires a dismissal reason and confirms before dismissing', async () => {
    const user = userEvent.setup()
    mocks.dismissSafetyAlert.mockResolvedValue(
      model({ status: 'dismissed', resolution_notes: 'Not relevant', available_actions: [] }),
    )
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'استبعاد الإنذار' }))

    const dialog = within(screen.getByRole('dialog'))
    const confirm = dialog.getByRole('button', { name: 'تأكيد الاستبعاد' })
    expect(confirm).toBeDisabled()
    await user.type(dialog.getByLabelText(/سبب الاستبعاد/), 'Not relevant')
    await user.click(confirm)

    expect(mocks.dismissSafetyAlert).toHaveBeenCalledWith(ALERT_ID, 'Not relevant')
    expect(await screen.findByText('مستبعد')).toBeInTheDocument()
    expect(actionButtons()).toEqual([])
  })

  it('closes with optional notes after confirmation', async () => {
    const user = userEvent.setup()
    mocks.getSafetyAlert.mockResolvedValue(
      model({ status: 'actioned', decision: 'monitor', available_actions: ['decide', 'close'] }),
    )
    mocks.closeSafetyAlert.mockResolvedValue(
      model({ status: 'closed', decision: 'monitor', available_actions: [] }),
    )
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'إغلاق الإنذار' }))
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'تأكيد الإغلاق' }),
    )

    expect(mocks.closeSafetyAlert).toHaveBeenCalledWith(ALERT_ID, '')
    expect(await screen.findByText('مغلق')).toBeInTheDocument()
  })

  it.each([
    [400, 'تعذّر قبول البيانات المُدخلة', false],
    [401, 'انتهت الجلسة', false],
    [403, 'لا تملك صلاحية هذا الإجراء', true],
    [404, 'الإنذار غير متاح', true],
    [409, 'تعذّر تنفيذ الإجراء على حالة الإنذار الحالية', true],
  ])(
    'handles HTTP %s from a workflow action without trusting UI state',
    async (status, title, reconcile) => {
      const user = userEvent.setup()
      mocks.acknowledgeSafetyAlert.mockRejectedValue(
        new ApiError('Only a new safety alert can be acknowledged.', status),
      )
      renderPage()
      await user.click(await screen.findByRole('button', { name: 'إقرار الاطلاع' }))

      await waitFor(() =>
        expect(mocks.showToast).toHaveBeenCalledWith(
          expect.objectContaining({ tone: 'critical', title }),
        ),
      )
      expect(JSON.stringify(mocks.showToast.mock.calls)).not.toContain('Only a new safety alert')
      await waitFor(() => expect(mocks.getSafetyAlert).toHaveBeenCalledTimes(reconcile ? 2 : 1))
    },
  )

  it.each([
    [404, 'الإنذار غير متاح'],
    [403, 'لا تملك صلاحية هذا الإجراء'],
  ])('shows a safe state when loading the alert returns %s', async (status, title) => {
    mocks.getSafetyAlert.mockRejectedValue(new ApiError('internal detail', status))
    renderPage()
    expect(await screen.findByText(title)).toBeInTheDocument()
    expect(screen.queryByText('internal detail')).not.toBeInTheDocument()
    expect(actionButtons()).toEqual([])
  })

  it('shows the standard error state for server failures while loading', async () => {
    mocks.getSafetyAlert.mockRejectedValue(new ApiError('Traceback', 503))
    renderPage()
    expect(await screen.findByText('تعذّر تحميل البيانات')).toBeInTheDocument()
    expect(screen.queryByText('Traceback')).not.toBeInTheDocument()
  })
})
