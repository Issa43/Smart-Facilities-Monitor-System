// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminUsersPage } from './AdminUsersPage'

const mocks = vi.hoisted(() => ({
  createUser: vi.fn(),
  listUsersPage: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('@/api/users', () => ({
  createUser: mocks.createUser,
  listUsersPage: mocks.listUsersPage,
}))

vi.mock('@/context/ToastContext', () => ({
  useToast: () => ({ showToast: mocks.showToast }),
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({
    id: 'admin-user',
    fullName: 'Admin User',
    role: 'super_admin',
  }),
}))

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminUsersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AdminUsersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listUsersPage.mockResolvedValue({
      items: [],
      count: 0,
      page: 1,
      pageSize: 20,
      totalPages: 1,
    })
    mocks.createUser.mockResolvedValue({
      id: 'new-user',
      fullName: 'مستخدم اختبار',
      email: 'new.user@sflms.test',
      phone: '0500000000',
      username: 'new_user',
      role: 'construction_manager',
      status: 'active',
      profileImageUrl: null,
      initials: 'ما',
      lastLoginAt: null,
      createdAt: '2026-08-24T00:00:00Z',
      hasOperationalRecords: null,
    })
  })

  it('submits the create-user form through the component', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /مستخدم جديد/ }))
    await user.type(screen.getByLabelText(/^الاسم الكامل/), 'مستخدم اختبار')
    await user.selectOptions(screen.getByLabelText(/^الدور الوظيفي/), 'construction_manager')
    await user.type(screen.getByLabelText(/^البريد الإلكتروني/), 'new.user@sflms.test')
    await user.type(screen.getByLabelText(/^رقم الجوال/), '0500000000')
    await user.type(screen.getByLabelText(/^اسم المستخدم/), 'new_user')
    await user.type(screen.getByLabelText(/^كلمة المرور/), 'StrongPass123!')
    await user.click(screen.getByRole('button', { name: 'إنشاء الحساب' }))

    await waitFor(() =>
      expect(mocks.createUser).toHaveBeenCalledWith({
        fullName: 'مستخدم اختبار',
        email: 'new.user@sflms.test',
        phone: '0500000000',
        username: 'new_user',
        role: 'construction_manager',
        status: 'active',
        password: 'StrongPass123!',
      }),
    )
  })
})
