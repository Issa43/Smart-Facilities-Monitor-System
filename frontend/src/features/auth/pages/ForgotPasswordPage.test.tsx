// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { ForgotPasswordPage } from './ForgotPasswordPage'

const mocks = vi.hoisted(() => ({
  generateDevPasswordResetLink: vi.fn(),
  requestPasswordReset: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  generateDevPasswordResetLink: mocks.generateDevPasswordResetLink,
  requestPasswordReset: mocks.requestPasswordReset,
}))
vi.mock('@/context/ToastContext', () => ({
  useToast: () => ({ showToast: mocks.showToast }),
}))

const UID = 'NjFhNGE5NGIt'
const TOKEN = 'df1t38-5c600e9d010cea67'
/** Exactly the shape the backend returns: absolute, same origin as the app. */
const RESET_URL = `http://localhost:3000/reset-password?uid=${UID}&token=${TOKEN}`

/** Stands in for the real reset page so the assertion is about arriving there
 *  with the link intact, not about re-testing that page's internals. */
function ResetPageProbe() {
  const [params] = useSearchParams()
  return (
    <div>
      <h1>صفحة إعادة التعيين</h1>
      <span data-testid="probe-uid">{params.get('uid')}</span>
      <span data-testid="probe-token">{params.get('token')}</span>
    </div>
  )
}

function renderFlow() {
  return render(
    <MemoryRouter initialEntries={['/forgot-password']}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPageProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function submitEmail(email: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/البريد الإلكتروني/), email)
  await user.click(screen.getByRole('button', { name: /متابعة إعادة تعيين كلمة المرور/ }))
  return user
}

describe('ForgotPasswordPage — local development direct link', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.generateDevPasswordResetLink.mockResolvedValue(RESET_URL)
    mocks.requestPasswordReset.mockResolvedValue(undefined)
  })

  it('renders the request form', () => {
    renderFlow()
    expect(screen.getByRole('heading', { name: 'نسيت كلمة المرور' })).toBeInTheDocument()
    expect(screen.getByLabelText(/البريد الإلكتروني/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /متابعة إعادة تعيين كلمة المرور/ }),
    ).toBeInTheDocument()
  })

  it('accepts typed input in the email field', async () => {
    renderFlow()
    const user = userEvent.setup()
    const field = screen.getByLabelText(/البريد الإلكتروني/)
    await user.type(field, 'diana@example.test')
    expect(field).toHaveValue('diana@example.test')
  })

  it('asks the direct-link endpoint, not the email endpoint, with the typed email', async () => {
    renderFlow()
    await submitEmail('diana@example.test')

    await waitFor(() =>
      expect(mocks.generateDevPasswordResetLink).toHaveBeenCalledWith('diana@example.test'),
    )
    expect(mocks.requestPasswordReset).not.toHaveBeenCalled()
  })

  it('navigates to the reset page by itself, carrying the exact uid and token', async () => {
    renderFlow()
    await submitEmail('diana@example.test')

    // No copying, no pasting, no clicking a displayed URL: arriving here is the
    // direct result of submitting the form.
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'صفحة إعادة التعيين' })).toBeInTheDocument(),
    )
    expect(screen.getByTestId('probe-uid')).toHaveTextContent(UID)
    expect(screen.getByTestId('probe-token')).toHaveTextContent(TOKEN)
    expect(screen.queryByRole('heading', { name: 'نسيت كلمة المرور' })).not.toBeInTheDocument()
  })

  it('never shows a mailbox screen or a raw link to copy', async () => {
    const { container } = renderFlow()
    const before = container.textContent ?? ''
    expect(before).not.toMatch(/سنرسل لك رابطاً/)

    await submitEmail('diana@example.test')
    await screen.findByRole('heading', { name: 'صفحة إعادة التعيين' })

    const after = container.textContent ?? ''
    expect(after).not.toMatch(/Mailpit/i)
    expect(after).not.toMatch(/تحقّق من بريدك الإلكتروني/)
    expect(after).not.toMatch(/نسخ الرابط/)
    expect(after).not.toContain(RESET_URL)
  })

  it('disables the button while the request is in flight and never double-submits', async () => {
    let release: (url: string) => void = () => {}
    mocks.generateDevPasswordResetLink.mockReturnValue(
      new Promise<string>((resolve) => {
        release = resolve
      }),
    )
    renderFlow()
    const user = await submitEmail('diana@example.test')

    const button = screen.getByRole('button', { name: /متابعة إعادة تعيين كلمة المرور/ })
    await waitFor(() => expect(button).toBeDisabled())
    await user.click(button)
    expect(mocks.generateDevPasswordResetLink).toHaveBeenCalledTimes(1)

    release(RESET_URL)
    await screen.findByRole('heading', { name: 'صفحة إعادة التعيين' })
  })

  it('stays put and reports an unknown account in Arabic', async () => {
    mocks.generateDevPasswordResetLink.mockRejectedValue(
      new ApiError('No eligible active account for that email.', 404),
    )
    renderFlow()
    await submitEmail('nobody@example.test')

    await waitFor(() =>
      expect(screen.getByText('تعذّر إنشاء رابط إعادة تعيين كلمة المرور.')).toBeInTheDocument(),
    )
    expect(screen.getByRole('heading', { name: 'نسيت كلمة المرور' })).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'صفحة إعادة التعيين' }),
    ).not.toBeInTheDocument()
  })

  it('never blames a failed send, because nothing is sent', async () => {
    mocks.generateDevPasswordResetLink.mockRejectedValue(new ApiError('boom', 500))
    const { container } = renderFlow()
    await submitEmail('diana@example.test')

    await waitFor(() =>
      expect(screen.getByText('تعذّر إنشاء رابط إعادة تعيين كلمة المرور.')).toBeInTheDocument(),
    )
    expect(container.textContent ?? '').not.toMatch(/فشل إرسال الرابط/)
    expect(container.textContent ?? '').not.toMatch(/تعذّر إرسال الرابط/)
  })

  it('surfaces a backend validation error and does not navigate', async () => {
    mocks.generateDevPasswordResetLink.mockRejectedValue(
      new ApiError('Enter a valid email address.', 400),
    )
    renderFlow()
    await submitEmail('diana@example.test')

    await waitFor(() =>
      expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument(),
    )
    expect(screen.getByRole('heading', { name: 'نسيت كلمة المرور' })).toBeInTheDocument()
  })

  it('validates the email locally before calling the backend', async () => {
    renderFlow()
    await submitEmail('not-an-email')

    await waitFor(() =>
      expect(screen.getByText(/صيغة البريد الإلكتروني غير صحيحة/)).toBeInTheDocument(),
    )
    expect(mocks.generateDevPasswordResetLink).not.toHaveBeenCalled()
  })

  it('re-enables the button after a failure so the user can retry', async () => {
    mocks.generateDevPasswordResetLink.mockRejectedValue(new ApiError('boom', 500))
    renderFlow()
    await submitEmail('diana@example.test')

    await screen.findByText('تعذّر إنشاء رابط إعادة تعيين كلمة المرور.')
    expect(
      screen.getByRole('button', { name: /متابعة إعادة تعيين كلمة المرور/ }),
    ).toBeEnabled()
  })
})

describe('ForgotPasswordPage — production behaviour is unchanged', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  /** The page reads `import.meta.env.DEV` once at module load, so the
   *  production build is exercised by reloading the module with it stubbed off. */
  async function renderProductionPage() {
    vi.stubEnv('DEV', false)
    vi.resetModules()
    const { ForgotPasswordPage: ProdPage } = await import('./ForgotPasswordPage')
    return render(
      <MemoryRouter initialEntries={['/forgot-password']}>
        <Routes>
          <Route path="/forgot-password" element={<ProdPage />} />
          <Route path="/reset-password" element={<ResetPageProbe />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mocks.requestPasswordReset.mockResolvedValue(undefined)
    mocks.generateDevPasswordResetLink.mockResolvedValue(RESET_URL)
  })

  it('still posts to the enumeration-safe email endpoint', async () => {
    await renderProductionPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/البريد الإلكتروني/), 'diana@example.test')
    await user.click(screen.getByRole('button', { name: 'إرسال رابط إعادة التعيين' }))

    await waitFor(() =>
      expect(mocks.requestPasswordReset).toHaveBeenCalledWith('diana@example.test'),
    )
    expect(mocks.generateDevPasswordResetLink).not.toHaveBeenCalled()
  })

  it('still shows the check-your-email screen and never auto-navigates', async () => {
    await renderProductionPage()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/البريد الإلكتروني/), 'diana@example.test')
    await user.click(screen.getByRole('button', { name: 'إرسال رابط إعادة التعيين' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'تحقّق من بريدك الإلكتروني' })).toBeInTheDocument(),
    )
    expect(screen.queryByRole('heading', { name: 'صفحة إعادة التعيين' })).not.toBeInTheDocument()
  })

  it('still keeps the send-oriented wording', async () => {
    await renderProductionPage()
    expect(screen.getByText(/سنرسل لك رابطاً لإعادة تعيين كلمة المرور/)).toBeInTheDocument()
  })
})
