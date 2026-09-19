// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SafetyAlert, SafetyOpenProposal } from '@/types'
import { DecisionWorkflowPanel } from './DecisionWorkflowPanel'

const mocks = vi.hoisted(() => ({
  createSafetyProposal: vi.fn(),
  approveSafetyProposal: vi.fn(),
  rejectSafetyProposal: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/api/safety', () => ({
  createSafetyProposal: mocks.createSafetyProposal,
  approveSafetyProposal: mocks.approveSafetyProposal,
  rejectSafetyProposal: mocks.rejectSafetyProposal,
}))
vi.mock('@/context/ToastContext', () => ({
  useToast: () => ({ showToast: mocks.showToast }),
}))

const WORKER_PROPOSAL: SafetyOpenProposal = {
  id: 'p-worker',
  decisionType: 'worker_protection',
  proposedAction: 'suspend_outdoor_work',
  proposalNotes: 'حماية الطاقم أثناء مرور العاصفة.',
  effectiveFrom: null,
  effectiveUntil: null,
  workerScope: '',
  status: 'pending_manager_review',
  proposedBy: { id: 'cm-1', fullName: 'مدير الإنشاء' },
  proposedAt: '2026-09-18T08:00:00Z',
  canReview: false,
}

const ASSET_PROPOSAL: SafetyOpenProposal = {
  ...WORKER_PROPOSAL,
  id: 'p-asset',
  decisionType: 'asset_protection',
  proposedAction: 'increase_precautions',
  proposalNotes: 'تقليل حمل المعدات غير الأساسية.',
  proposedBy: { id: 'om-1', fullName: 'مدير التشغيل' },
}

function makeAlert(overrides: Partial<SafetyAlert> = {}): SafetyAlert {
  return {
    id: 'alert-1',
    status: 'acknowledged',
    availableActions: [],
    availableProposalTypes: [],
    openProposals: [],
    ...overrides,
  } as unknown as SafetyAlert
}

function renderPanel(alert: SafetyAlert) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DecisionWorkflowPanel alert={alert} />
    </QueryClientProvider>,
  )
}

describe('DecisionWorkflowPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.createSafetyProposal.mockResolvedValue({})
    mocks.approveSafetyProposal.mockResolvedValue({})
    mocks.rejectSafetyProposal.mockResolvedValue({})
  })

  it('renders nothing when the viewer can neither propose nor review', () => {
    const { container } = renderPanel(makeAlert())
    expect(container).toBeEmptyDOMElement()
  })

  it('never claims the system acts on its own', () => {
    renderPanel(makeAlert({ availableProposalTypes: ['worker_protection'] }))
    expect(screen.getByText(/الخطر الخارجي معلومة، وليس أمراً تنفيذياً/)).toBeInTheDocument()
    expect(screen.getByText(/لا يتخذ النظام أي إجراء تلقائي/)).toBeInTheDocument()
  })

  // --- General Manager ----------------------------------------------------

  it('shows the hazard decision awaiting the General Manager with approve and reject', () => {
    renderPanel(
      makeAlert({ openProposals: [{ ...WORKER_PROPOSAL, canReview: true }] }),
    )

    const card = within(screen.getByTestId('open-proposals'))
    expect(card.getByText('حماية العاملين')).toBeInTheDocument()
    expect(card.getByText('إيقاف الأعمال الخارجية مؤقتاً')).toBeInTheDocument()
    expect(card.getByText('حماية الطاقم أثناء مرور العاصفة.')).toBeInTheDocument()
    expect(card.getByText(/مدير الإنشاء/)).toBeInTheDocument()
    expect(card.getByText('بانتظار موافقة المدير العام')).toBeInTheDocument()
    expect(card.getByRole('button', { name: 'موافقة وإرسال القرار' })).toBeInTheDocument()
    expect(card.getByRole('button', { name: 'رفض' })).toBeInTheDocument()
  })

  it('renders a pending asset proposal for review too', () => {
    renderPanel(makeAlert({ openProposals: [{ ...ASSET_PROPOSAL, canReview: true }] }))
    expect(screen.getByText('حماية الأصول')).toBeInTheDocument()
    expect(screen.getByText('تقليل حمل المعدات غير الأساسية.')).toBeInTheDocument()
  })

  it('states that approving worker protection is what sends Telegram', async () => {
    const user = userEvent.setup()
    renderPanel(makeAlert({ openProposals: [{ ...WORKER_PROPOSAL, canReview: true }] }))

    await user.click(screen.getByRole('button', { name: 'موافقة وإرسال القرار' }))
    expect(screen.getByText(/بوت تيليجرام الرسمي/)).toBeInTheDocument()
    expect(screen.getByText(/قناة المشروع المتأثر فقط/)).toBeInTheDocument()
    expect(screen.getByText(/لا حاجة لأي إرسال يدوي/)).toBeInTheDocument()
  })

  it('states that approving asset protection shuts nothing down', async () => {
    const user = userEvent.setup()
    renderPanel(makeAlert({ openProposals: [{ ...ASSET_PROPOSAL, canReview: true }] }))

    await user.click(screen.getByRole('button', { name: 'اعتماد القرار' }))
    expect(screen.getByText(/لا يتم إيقاف أي أصل تلقائياً/)).toBeInTheDocument()
  })

  it('approves through the API', async () => {
    const user = userEvent.setup()
    renderPanel(makeAlert({ openProposals: [{ ...WORKER_PROPOSAL, canReview: true }] }))

    await user.click(screen.getByRole('button', { name: 'موافقة وإرسال القرار' }))
    const dialog = within(screen.getByRole('dialog'))
    await user.click(dialog.getByRole('button', { name: 'موافقة وإرسال القرار' }))

    await waitFor(() => expect(mocks.approveSafetyProposal).toHaveBeenCalledWith('p-worker', ''))
    expect(mocks.rejectSafetyProposal).not.toHaveBeenCalled()
  })

  it('requires a reason to reject and says nothing will be sent', async () => {
    const user = userEvent.setup()
    renderPanel(makeAlert({ openProposals: [{ ...WORKER_PROPOSAL, canReview: true }] }))

    await user.click(screen.getByRole('button', { name: 'رفض' }))
    const dialog = within(screen.getByRole('dialog'))
    expect(screen.getByText(/لن يتم إرسال أي إشعار للعاملين/)).toBeInTheDocument()

    const confirm = dialog.getByRole('button', { name: 'رفض' })
    expect(confirm).toBeDisabled()

    await user.type(screen.getByLabelText(/سبب الرفض/), 'الطاقم غادر الموقع.')
    await user.click(dialog.getByRole('button', { name: 'رفض' }))
    await waitFor(() =>
      expect(mocks.rejectSafetyProposal).toHaveBeenCalledWith('p-worker', 'الطاقم غادر الموقع.'),
    )
    expect(mocks.approveSafetyProposal).not.toHaveBeenCalled()
  })

  // --- Proposing managers -------------------------------------------------

  it('offers only the proposal kind the server says this viewer may raise', () => {
    renderPanel(makeAlert({ availableProposalTypes: ['worker_protection'] }))

    expect(screen.getByRole('button', { name: /اقتراح حماية العاملين/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /اقتراح حماية الأصول/ })).not.toBeInTheDocument()
  })

  it('offers asset protection to the manager entitled to it', () => {
    renderPanel(makeAlert({ availableProposalTypes: ['asset_protection'] }))

    expect(screen.getByRole('button', { name: /اقتراح حماية الأصول/ })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /اقتراح حماية العاملين/ }),
    ).not.toBeInTheDocument()
  })

  it('submits a proposal with its action and justification', async () => {
    const user = userEvent.setup()
    renderPanel(makeAlert({ availableProposalTypes: ['worker_protection'] }))

    await user.click(screen.getByRole('button', { name: /اقتراح حماية العاملين/ }))
    expect(screen.getByText(/لا يُنفَّذ ولا يُرسل أي إشعار قبل اعتماد المدير العام/)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText(/الإجراء المقترح/), 'suspend_outdoor_work')
    await user.type(screen.getByLabelText(/مبرر الاقتراح/), 'حماية الطاقم.')
    await user.click(screen.getByRole('button', { name: 'إرسال للمدير العام' }))

    await waitFor(() =>
      expect(mocks.createSafetyProposal).toHaveBeenCalledWith('alert-1', {
        decisionType: 'worker_protection',
        proposedAction: 'suspend_outdoor_work',
        notes: 'حماية الطاقم.',
        effectiveFrom: null,
        effectiveUntil: null,
        workerScope: '',
      }),
    )
  })

  it('cannot submit a proposal without an action and a justification', async () => {
    const user = userEvent.setup()
    renderPanel(makeAlert({ availableProposalTypes: ['worker_protection'] }))
    await user.click(screen.getByRole('button', { name: /اقتراح حماية العاملين/ }))

    expect(screen.getByRole('button', { name: 'إرسال للمدير العام' })).toBeDisabled()
    await user.selectOptions(screen.getByLabelText(/الإجراء المقترح/), 'monitor')
    expect(screen.getByRole('button', { name: 'إرسال للمدير العام' })).toBeDisabled()
  })

  it('shows a proposer their own pending ask without any approve control', () => {
    renderPanel(
      makeAlert({
        openProposals: [WORKER_PROPOSAL],
        availableProposalTypes: [],
      }),
    )

    expect(screen.getByText('بانتظار موافقة المدير العام')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'موافقة وإرسال القرار' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'رفض' })).not.toBeInTheDocument()
  })

  it('hides review controls from an in-scope manager who lacks authority', () => {
    renderPanel(
      makeAlert({
        openProposals: [{ ...ASSET_PROPOSAL, canReview: false }],
        availableProposalTypes: ['worker_protection'],
      }),
    )

    expect(screen.queryByRole('button', { name: 'اعتماد القرار' })).not.toBeInTheDocument()
    // Still able to raise their own kind of proposal.
    expect(screen.getByRole('button', { name: /اقتراح حماية العاملين/ })).toBeInTheDocument()
  })

  it('surfaces a server refusal instead of pretending the action succeeded', async () => {
    mocks.approveSafetyProposal.mockRejectedValue(new Error('nope'))
    const user = userEvent.setup()
    renderPanel(makeAlert({ openProposals: [{ ...WORKER_PROPOSAL, canReview: true }] }))

    await user.click(screen.getByRole('button', { name: 'موافقة وإرسال القرار' }))
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'موافقة وإرسال القرار' }),
    )

    await waitFor(() =>
      expect(mocks.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ tone: 'critical' }),
      ),
    )
  })

  it('offers the General Manager no proposal controls at all', () => {
    renderPanel(
      makeAlert({
        openProposals: [{ ...WORKER_PROPOSAL, canReview: true }],
        // The server reports an approver as able to propose nothing.
        availableProposalTypes: [],
      }),
    )

    expect(screen.queryByRole('button', { name: /اقتراح/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'موافقة وإرسال القرار' })).toBeInTheDocument()
  })

  it('approval of worker protection is a single action, not approve-then-send', async () => {
    const user = userEvent.setup()
    renderPanel(makeAlert({ openProposals: [{ ...WORKER_PROPOSAL, canReview: true }] }))

    await user.click(screen.getByRole('button', { name: 'موافقة وإرسال القرار' }))
    const dialog = within(screen.getByRole('dialog'))
    await user.click(dialog.getByRole('button', { name: 'موافقة وإرسال القرار' }))

    await waitFor(() => expect(mocks.approveSafetyProposal).toHaveBeenCalledTimes(1))
    // There is no separate "send" step anywhere in the flow.
    expect(screen.queryByRole('button', { name: /إرسال يدوي|فتح تيليجرام/ })).not.toBeInTheDocument()
  })

  it('shows the approver the effective window and worker scope', () => {
    renderPanel(
      makeAlert({
        openProposals: [
          {
            ...WORKER_PROPOSAL,
            canReview: true,
            effectiveFrom: '2026-09-20T09:00:00Z',
            effectiveUntil: '2026-09-20T13:00:00Z',
            workerScope: 'أطقم العمل في الهواء الطلق',
          },
        ],
      }),
    )

    expect(screen.getByText('سريان القرار')).toBeInTheDocument()
    expect(screen.getByText('الفئات المشمولة')).toBeInTheDocument()
    expect(screen.getByText('أطقم العمل في الهواء الطلق')).toBeInTheDocument()
  })

  it('sends the proposed window as an instant', async () => {
    const user = userEvent.setup()
    renderPanel(makeAlert({ availableProposalTypes: ['worker_protection'] }))

    await user.click(screen.getByRole('button', { name: /اقتراح حماية العاملين/ }))
    await user.selectOptions(screen.getByLabelText(/الإجراء المقترح/), 'suspend_outdoor_work')
    await user.type(screen.getByLabelText(/بداية السريان/), '2026-09-20T09:00')
    await user.type(screen.getByLabelText(/الفئات المشمولة/), 'أطقم خارجية')
    await user.type(screen.getByLabelText(/مبرر الاقتراح/), 'حماية الطاقم.')
    await user.click(screen.getByRole('button', { name: 'إرسال للمدير العام' }))

    await waitFor(() => expect(mocks.createSafetyProposal).toHaveBeenCalled())
    const [, payload] = mocks.createSafetyProposal.mock.calls[0]
    expect(payload.effectiveFrom).toMatch(/^2026-09-20T/)
    expect(payload.workerScope).toBe('أطقم خارجية')
  })

  it('never tells the approver to send anything by hand', () => {
    const { container } = renderPanel(
      makeAlert({ openProposals: [{ ...WORKER_PROPOSAL, canReview: true }] }),
    )

    const text = container.textContent ?? ''
    expect(text).not.toMatch(/انسخ|الصق|افتح تيليجرام/)
  })
})
