// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NotificationDrawer } from './NotificationDrawer'
import { Topbar } from './Topbar'

const mocks = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  logout: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/api/users', () => ({
  listNotifications: mocks.listNotifications,
  markAllNotificationsRead: mocks.markAllNotificationsRead,
  markNotificationRead: mocks.markNotificationRead,
}))
vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ logout: mocks.logout }),
  useCurrentUser: () => ({
    id: 'manager-1',
    fullName: 'Construction Manager',
    initials: 'CM',
    role: 'construction_manager',
  }),
}))
vi.mock('@/context/ToastContext', () => ({
  useToast: () => ({ showToast: mocks.showToast }),
}))

const notification = {
  id: 'notification-1',
  title: 'Project completion reminder',
  body: 'Project Alpha has reached its expected completion date today.',
  category: 'project' as const,
  tone: 'critical' as const,
  read: false,
  audience: ['construction_manager' as const],
  href: null,
  createdAt: '2026-09-01T08:00:00Z',
}

function renderWithClient(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('notification shell error feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.markAllNotificationsRead.mockResolvedValue(undefined)
    mocks.markNotificationRead.mockResolvedValue(undefined)
  })

  it('shows a visible and accessible Topbar failure indicator', async () => {
    mocks.listNotifications.mockRejectedValue(new Error('Notification API unavailable'))

    renderWithClient(<Topbar onOpenMobileNav={vi.fn()} onOpenNotifications={vi.fn()} />)

    const button = await screen.findByRole('button', { name: 'تعذّر تحميل الإشعارات' })
    expect(button).toHaveAttribute('title', 'تعذّر تحميل الإشعارات')
    expect(button).toHaveTextContent('!')
  })

  it('renders the notification query error and offers the existing retry action', async () => {
    mocks.listNotifications.mockRejectedValue(new Error('Notification API unavailable'))

    renderWithClient(<NotificationDrawer onClose={vi.fn()} />)

    expect(await screen.findByText('Notification API unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إعادة المحاولة' })).toBeInTheDocument()
  })

  it('reports mark-read mutation failures honestly', async () => {
    const user = userEvent.setup()
    mocks.listNotifications.mockResolvedValue([notification])
    mocks.markNotificationRead.mockRejectedValue(new Error('Read update failed'))

    renderWithClient(<NotificationDrawer onClose={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: /Project completion reminder/ }))

    await waitFor(() =>
      expect(mocks.showToast).toHaveBeenCalledWith({
        tone: 'critical',
        title: 'تعذّر تحديث الإشعارات',
        description: 'Read update failed',
      }),
    )
  })

  it('reports mark-all mutation failures honestly', async () => {
    const user = userEvent.setup()
    mocks.listNotifications.mockResolvedValue([notification])
    mocks.markAllNotificationsRead.mockRejectedValue(new Error('Bulk update failed'))

    renderWithClient(<NotificationDrawer onClose={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: 'تعليم الكل كمقروء' }))

    await waitFor(() =>
      expect(mocks.showToast).toHaveBeenCalledWith({
        tone: 'critical',
        title: 'تعذّر تحديث الإشعارات',
        description: 'Bulk update failed',
      }),
    )
  })
})
