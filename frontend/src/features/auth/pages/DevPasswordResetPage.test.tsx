// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { DevPasswordResetPage } from './DevPasswordResetPage'

const mocks = vi.hoisted(() => ({
  generateDevPasswordResetLink: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  generateDevPasswordResetLink: mocks.generateDevPasswordResetLink,
}))
vi.mock('@/api/client', async () => {
  const actual = await vi.importActual<typeof import('@/api/client')>('@/api/client')
  return { ...actual, API_BASE_URL: 'http://localhost:8000/api/v1' }
})
vi.mock('@/context/ToastContext', () => ({
  useToast: () => ({ showToast: mocks.showToast }),
}))

const RESET_URL =
  'http://localhost:5173/reset-password?uid=NjFhNGE5NGIt&token=df1t38-5c600e9d010cea67'

function renderPage() {
  return render(
    <MemoryRouter>
      <DevPasswordResetPage />
    </MemoryRouter>,
  )
}

/** jsdom exposes navigator.clipboard as a getter, and userEvent.setup()
 *  installs its own stub, so this must be applied after setup runs. */
function stubClipboard(writeText: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  })
}

async function generateFor(email: string) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText(/البريد الإلكتروني/), email)
  await user.click(screen.getByRole('button', { name: /إنشاء رابط إعادة التعيين/ }))
  return user
}

describe('DevPasswordResetPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.generateDevPasswordResetLink.mockResolvedValue(RESET_URL)
  })

  it('renders the form and states plainly that it is a local tool', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: /أداة تطوير/ })).toBeInTheDocument()
    expect(screen.getByText(/بيئة التطوير المحلية فقط/)).toBeInTheDocument()
    expect(screen.getByLabelText(/البريد الإلكتروني/)).toBeInTheDocument()
  })

  it('accepts an email and requests a link for it', async () => {
    renderPage()
    await generateFor('diana@example.test')
    await waitFor(() =>
      expect(mocks.generateDevPasswordResetLink).toHaveBeenCalledWith('diana@example.test'),
    )
  })

  it('shows the generated link', async () => {
    renderPage()
    await generateFor('diana@example.test')
    await waitFor(() => expect(screen.getByTestId('dev-reset-url')).toHaveTextContent(RESET_URL))
    expect(
      screen.getByText('تم إنشاء رابط إعادة تعيين كلمة المرور بنجاح.'),
    ).toBeInTheDocument()
  })

  it('never frames the operation as sending an email', async () => {
    const { container } = renderPage()
    await generateFor('diana@example.test')
    await screen.findByTestId('dev-reset-url')

    const text = container.textContent ?? ''
    // The link is generated and shown in place; the user is never sent to a
    // mail inbox to find it.
    expect(text).not.toMatch(/فشل إرسال الرابط/)
    expect(text).not.toMatch(/Mailpit/i)
    expect(text).not.toMatch(/صندوق البريد/)
    expect(text).toMatch(/لا يتم إرسال أي بريد إلكتروني/)
  })

  it('names the exact required failure wording, never a send failure', async () => {
    mocks.generateDevPasswordResetLink.mockRejectedValue(new Error('boom'))
    const { container } = renderPage()
    await generateFor('diana@example.test')

    await waitFor(() =>
      expect(screen.getByText('تعذّر إنشاء رابط إعادة تعيين كلمة المرور.')).toBeInTheDocument(),
    )
    expect(container.textContent ?? '').not.toMatch(/فشل إرسال الرابط/)
  })

  it('explains a blocked request by naming the API origin it could not reach', async () => {
    mocks.generateDevPasswordResetLink.mockRejectedValue(
      new ApiError('Failed to fetch', 0),
    )
    renderPage()
    await generateFor('diana@example.test')

    await waitFor(() =>
      expect(screen.getByText(/http:\/\/localhost:8000\/api\/v1/)).toBeInTheDocument(),
    )
    // A CORS-blocked call is the common local cause, so point at the origin.
    expect(screen.getByText(/http:\/\/localhost:5173/)).toBeInTheDocument()
    expect(screen.queryByTestId('dev-reset-url')).not.toBeInTheDocument()
  })

  it('opens the generated reset page, not a hard-coded route', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    renderPage()
    const user = await generateFor('diana@example.test')
    await screen.findByTestId('dev-reset-url')

    await user.click(screen.getByRole('button', { name: /فتح صفحة إعادة التعيين/ }))
    expect(open).toHaveBeenCalledWith(RESET_URL, '_self')
    open.mockRestore()
  })

  it('copies the link to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    renderPage()
    const user = await generateFor('diana@example.test')
    await screen.findByTestId('dev-reset-url')
    stubClipboard(writeText)

    await user.click(screen.getByRole('button', { name: /نسخ الرابط/ }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(RESET_URL))
    expect(mocks.showToast).toHaveBeenCalledWith(
      expect.objectContaining({ tone: 'success' }),
    )
  })

  it('survives a blocked clipboard without losing the link', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    renderPage()
    const user = await generateFor('diana@example.test')
    await screen.findByTestId('dev-reset-url')
    stubClipboard(writeText)

    await user.click(screen.getByRole('button', { name: /نسخ الرابط/ }))
    await waitFor(() =>
      expect(mocks.showToast).toHaveBeenCalledWith(
        expect.objectContaining({ tone: 'critical' }),
      ),
    )
    expect(screen.getByTestId('dev-reset-url')).toHaveTextContent(RESET_URL)
  })

  it('reports a backend refusal instead of showing a link', async () => {
    mocks.generateDevPasswordResetLink.mockRejectedValue(
      new Error('No eligible active account for that email.'),
    )
    renderPage()
    await generateFor('nobody@example.test')

    await waitFor(() =>
      expect(screen.getByText(/No eligible active account for that email\./)).toBeInTheDocument(),
    )
    expect(screen.queryByTestId('dev-reset-url')).not.toBeInTheDocument()
  })

  it('validates the email before calling the backend', async () => {
    renderPage()
    await generateFor('not-an-email')
    await waitFor(() =>
      expect(screen.getByText(/صيغة البريد الإلكتروني غير صحيحة/)).toBeInTheDocument(),
    )
    expect(mocks.generateDevPasswordResetLink).not.toHaveBeenCalled()
  })
})
