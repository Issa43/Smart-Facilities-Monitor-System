// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminRolesPage } from './AdminRolesPage'

const mocks = vi.hoisted(() => ({
  listRoles: vi.fn(),
  showToast: vi.fn(),
  updateRolePermissions: vi.fn(),
}))

vi.mock('@/api/users', () => ({
  listRoles: mocks.listRoles,
  updateRolePermissions: mocks.updateRolePermissions,
}))
vi.mock('@/context/ToastContext', () => ({
  useToast: () => ({ showToast: mocks.showToast }),
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'admin-user', fullName: 'Admin User', role: 'super_admin' }),
}))

const roles = [
  {
    id: 'role-super',
    name: 'super_admin',
    displayName: 'Super Admin',
    description: '',
    permissions: [],
  },
  {
    id: 'role-construction',
    name: 'construction_manager',
    displayName: 'Construction Manager',
    description: '',
    permissions: ['project.view'],
  },
  {
    id: 'role-operations',
    name: 'operations_manager',
    displayName: 'Operations Manager',
    description: '',
    permissions: [],
  },
  {
    id: 'role-security',
    name: 'security_officer',
    displayName: 'Security Officer',
    description: '',
    permissions: [],
  },
]

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminRolesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AdminRolesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listRoles.mockResolvedValue(roles)
    mocks.updateRolePermissions.mockResolvedValue(roles[1])
  })

  it('shows a loading state instead of zero permission counts', () => {
    mocks.listRoles.mockReturnValue(new Promise(() => undefined))
    renderPage()

    expect(screen.getByRole('status', { name: 'جارٍ التحميل' })).toBeInTheDocument()
    expect(screen.queryByText(/0 صلاحية ممنوحة/)).not.toBeInTheDocument()
  })

  it('shows the API error instead of an empty permission matrix', async () => {
    mocks.listRoles.mockRejectedValue(new Error('roles unavailable'))
    renderPage()

    expect(await screen.findByText('تعذّر تحميل البيانات')).toBeInTheDocument()
    expect(screen.getByText('roles unavailable')).toBeInTheDocument()
    expect(screen.queryByText(/0 صلاحية ممنوحة/)).not.toBeInTheDocument()
  })

  it('renders Super Admin as full-access, protected, and immutable', async () => {
    renderPage()

    const protectedCells = await screen.findAllByRole('button', {
      name: /المدير العام — صلاحية محمية/,
    })
    expect(protectedCells).toHaveLength(28)
    protectedCells.forEach((cell) => {
      expect(cell).toBeDisabled()
      expect(cell).toHaveAttribute('aria-pressed', 'true')
    })
    expect(screen.getByText('28 صلاحية ممنوحة')).toBeInTheDocument()
  })

  it('sends the complete persisted grant set when changing a non-admin role', async () => {
    const user = userEvent.setup()
    renderPage()

    const cell = await screen.findByRole('button', {
      name: 'إنشاء المشاريع — مدير الإنشاءات',
    })
    await user.click(cell)

    await waitFor(() =>
      expect(mocks.updateRolePermissions).toHaveBeenCalledWith(
        'construction_manager',
        expect.arrayContaining(['project.view', 'project.create']),
      ),
    )
    expect(mocks.updateRolePermissions.mock.calls[0]?.[1]).toHaveLength(2)
  })
})
