// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminUserDetailPage } from './AdminUserDetailPage'

const mocks = vi.hoisted(() => ({
  currentUser: vi.fn(),
  deleteUser: vi.fn(),
  getUser: vi.fn(),
  listAuditLogs: vi.fn(),
  resetUserPassword: vi.fn(),
  setUserStatus: vi.fn(),
  showToast: vi.fn(),
  updateUser: vi.fn(),
}))

vi.mock('@/api/users', () => ({
  deleteUser: mocks.deleteUser,
  getUser: mocks.getUser,
  listAuditLogs: mocks.listAuditLogs,
  resetUserPassword: mocks.resetUserPassword,
  setUserStatus: mocks.setUserStatus,
  updateUser: mocks.updateUser,
}))

vi.mock('@/context/AuthContext', () => ({ useCurrentUser: () => mocks.currentUser() }))
vi.mock('@/context/ToastContext', () => ({
  useToast: () => ({ showToast: mocks.showToast }),
}))

const targetUser = {
  id: 'target-user',
  fullName: 'Target User',
  email: 'target@sflms.test',
  phone: '0500000000',
  username: 'target_user',
  role: 'construction_manager' as const,
  status: 'active' as const,
  profileImageUrl: null,
  initials: 'TU',
  lastLoginAt: null,
  createdAt: '2026-08-24T00:00:00Z',
  hasOperationalRecords: null,
}

const adminUser = {
  ...targetUser,
  id: 'admin-user',
  fullName: 'Admin User',
  email: 'admin@sflms.test',
  username: 'admin_user',
  role: 'super_admin' as const,
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/users/target-user']}>
        <Routes>
          <Route path="/admin/users/:userId" element={<AdminUserDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AdminUserDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.currentUser.mockReturnValue(adminUser)
    mocks.getUser.mockResolvedValue(targetUser)
    mocks.listAuditLogs.mockResolvedValue([])
    mocks.updateUser.mockImplementation(async (_id, input) => ({ ...targetUser, ...input }))
    mocks.setUserStatus.mockResolvedValue({ ...targetUser, status: 'suspended' })
  })

  it('edits fields, reassigns the role, and uploads a profile image', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /تعديل المستخدم/ }))
    const dialog = screen.getByRole('dialog', { name: 'تعديل بيانات المستخدم' })
    const fullName = within(dialog).getByLabelText(/^الاسم الكامل/)
    await user.clear(fullName)
    await user.type(fullName, 'Edited User')
    await user.selectOptions(within(dialog).getByLabelText(/^الدور الوظيفي/), 'operations_manager')
    const image = new File(['avatar'], 'avatar.png', { type: 'image/png' })
    await user.upload(within(dialog).getByLabelText('الصورة الشخصية'), image)
    await user.click(within(dialog).getByRole('button', { name: 'حفظ التغييرات' }))

    await waitFor(() =>
      expect(mocks.updateUser).toHaveBeenCalledWith('target-user', {
        fullName: 'Edited User',
        phone: '0500000000',
        role: 'operations_manager',
        status: 'active',
        profileImage: image,
      }),
    )
  })

  it('changes status only after the account switch is used', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('switch', { name: 'تفعيل أو إيقاف الحساب' }))

    await waitFor(() =>
      expect(mocks.setUserStatus).toHaveBeenCalledWith('target-user', 'suspended'),
    )
  })

  it('makes the current Super Admin role, status, and archive actions immutable', async () => {
    mocks.currentUser.mockReturnValue({ ...adminUser, id: 'target-user' })
    mocks.getUser.mockResolvedValue({ ...adminUser, id: 'target-user' })
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByRole('switch', { name: 'تفعيل أو إيقاف الحساب' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /أرشفة الحساب/ })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /تعديل المستخدم/ }))
    const dialog = screen.getByRole('dialog', { name: 'تعديل بيانات المستخدم' })
    expect(within(dialog).getByLabelText(/^الدور الوظيفي/)).toBeDisabled()
    expect(within(dialog).getByLabelText(/^حالة الحساب/)).toBeDisabled()
  })
})
