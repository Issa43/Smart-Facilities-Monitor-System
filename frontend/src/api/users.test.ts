import { afterEach, describe, expect, it, vi } from 'vitest'

const canonicalUser = (overrides: Record<string, unknown> = {}) => ({
  id: 'user-1',
  full_name: 'Test User',
  email: 'user@sflms.test',
  phone: '0500000000',
  username: 'test_user',
  role: 'role-1',
  role_name: 'construction_manager',
  profile_image: null,
  status: 'active',
  last_login: null,
  created_at: '2026-08-17T01:00:00Z',
  updated_at: '2026-08-17T01:00:00Z',
  ...overrides,
})

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

const rolePage = (name = 'operations_manager') => ({
  count: 1,
  total_pages: 1,
  current_page: 1,
  page_size: 20,
  next: null,
  previous: null,
  results: [
    {
      id: 'role-1',
      name,
      name_display: 'Role',
      description: '',
      created_at: '2026-08-17T00:00:00Z',
      permissions: [],
    },
  ],
})

const emptyUserPage = {
  count: 0,
  total_pages: 1,
  current_page: 1,
  page_size: 20,
  next: null,
  previous: null,
  results: [],
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('user API contracts', () => {
  it('surfaces a field-specific validation error instead of the generic envelope message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            success: false,
            error: {
              code: 400,
              message: 'Request failed.',
              details: {
                username: ['A user with that username already exists.'],
              },
            },
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const { apiRequest } = await import('./client')

    await expect(apiRequest('/users/')).rejects.toMatchObject({
      message: 'username: A user with that username already exists.',
      status: 400,
      details: { username: ['A user with that username already exists.'] },
    })
  })

  it('surfaces the backend password reason for a numeric password', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            success: false,
            error: {
              code: 400,
              message: 'Request failed.',
              details: {
                password: ['This password is too common.', 'This password is entirely numeric.'],
              },
            },
          }),
          { status: 400, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const { apiRequest } = await import('./client')

    await expect(apiRequest('/users/')).rejects.toMatchObject({
      message: 'password: This password is too common. This password is entirely numeric.',
      status: 400,
    })
  })

  it('creates a user and maps the canonical read response', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            count: 4,
            total_pages: 1,
            current_page: 1,
            page_size: 20,
            next: null,
            previous: null,
            results: [
              {
                id: 'role-1',
                name: 'construction_manager',
                name_display: 'Construction Manager',
                description: '',
                created_at: '2026-08-17T00:00:00Z',
                permissions: [],
              },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 'user-1',
            full_name: 'Phase Two User',
            email: 'phase-two@sflms.test',
            phone: '0500000000',
            username: 'phase_two_user',
            role: 'role-1',
            role_name: 'construction_manager',
            profile_image: null,
            status: 'active',
            last_login: null,
            created_at: '2026-08-17T01:00:00Z',
            updated_at: '2026-08-17T01:00:00Z',
          }),
          { status: 201, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)
    const { createUser } = await import('./users')

    const user = await createUser({
      fullName: 'Phase Two User',
      email: 'phase-two@sflms.test',
      phone: '0500000000',
      username: 'phase_two_user',
      role: 'construction_manager',
      status: 'active',
      password: 'StrongPass123!',
    })

    expect(user).toMatchObject({
      id: 'user-1',
      fullName: 'Phase Two User',
      role: 'construction_manager',
      lastLoginAt: null,
      createdAt: '2026-08-17T01:00:00Z',
    })
    const [url, request] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(url).toContain('/users/')
    expect(request.method).toBe('POST')
    expect(JSON.parse(String(request.body))).toMatchObject({
      role: 'role-1',
      password: 'StrongPass123!',
      confirm_password: 'StrongPass123!',
    })
  })

  it('edits an existing user and changes the role through the canonical PATCH contract', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(rolePage()))
      .mockResolvedValueOnce(
        jsonResponse(
          canonicalUser({
            full_name: 'Edited User',
            phone: '0511111111',
            role_name: 'operations_manager',
          }),
        ),
      )
    vi.stubGlobal('fetch', fetchMock)
    const { updateUser } = await import('./users')

    const updated = await updateUser('user-1', {
      fullName: 'Edited User',
      phone: '0511111111',
      role: 'operations_manager',
    })

    expect(updated).toMatchObject({
      id: 'user-1',
      fullName: 'Edited User',
      phone: '0511111111',
      role: 'operations_manager',
    })
    const [url, request] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(url).toContain('/users/user-1/')
    expect(request.method).toBe('PATCH')
    expect(JSON.parse(String(request.body))).toEqual({
      full_name: 'Edited User',
      phone: '0511111111',
      role: 'role-1',
    })
  })

  it('uploads a profile image through multipart PATCH', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(canonicalUser({ profile_image: '/media/avatar.png' })))
    vi.stubGlobal('fetch', fetchMock)
    const { updateUser } = await import('./users')
    const image = new File(['avatar'], 'avatar.png', { type: 'image/png' })

    const updated = await updateUser('user-1', { fullName: 'Test User', profileImage: image })

    expect(updated.profileImageUrl).toBe('http://localhost:8000/media/avatar.png')
    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(request.method).toBe('PATCH')
    expect(request.body).toBeInstanceOf(FormData)
    expect((request.body as FormData).get('full_name')).toBe('Test User')
    expect((request.body as FormData).get('profile_image')).toBeInstanceOf(File)
    expect(new Headers(request.headers).has('Content-Type')).toBe(false)
  })

  it('activates and suspends without optimistic local state', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(canonicalUser({ status: 'suspended' })))
      .mockResolvedValueOnce(jsonResponse(canonicalUser({ status: 'active' })))
    vi.stubGlobal('fetch', fetchMock)
    const { setUserStatus } = await import('./users')

    const suspended = await setUserStatus('user-1', 'suspended')
    const active = await setUserStatus('user-1', 'active')

    expect(suspended.status).toBe('suspended')
    expect(active.status).toBe('active')
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      status: 'suspended',
    })
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({ status: 'active' })
  })

  it('maps and labels the backend inactive account state', async () => {
    const { userFromDto } = await import('./adapters/users')
    const { ACCOUNT_STATUS_LABELS, ACCOUNT_STATUS_TONE } = await import('@/types')

    const inactive = userFromDto(canonicalUser({ status: 'inactive' }) as never)

    expect(inactive.status).toBe('inactive')
    expect(ACCOUNT_STATUS_LABELS[inactive.status]).toBeTruthy()
    expect(ACCOUNT_STATUS_TONE[inactive.status]).toBe('neutral')
  })

  it('fails safely when a legacy account has no role assignment', async () => {
    const { userFromDto } = await import('./adapters/users')

    expect(() => userFromDto(canonicalUser({ role_name: null }) as never)).toThrow(
      'This account has no assigned role.',
    )
  })

  it('sends status filtering and ordering to the paginated backend', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(emptyUserPage))
    vi.stubGlobal('fetch', fetchMock)
    const { listUsersPage } = await import('./users')

    await listUsersPage({
      page: 3,
      search: 'manager',
      status: 'inactive',
      ordering: 'full_name',
    })

    const [url] = fetchMock.mock.calls[0] as [string]
    const parsed = new URL(url)
    expect(parsed.searchParams.get('page')).toBe('3')
    expect(parsed.searchParams.get('search')).toBe('manager')
    expect(parsed.searchParams.get('status')).toBe('inactive')
    expect(parsed.searchParams.get('ordering')).toBe('full_name')
  })
})
