import { afterEach, describe, expect, it, vi } from 'vitest'

const canonicalUser = (overrides: Record<string, unknown> = {}) => ({
  id: 'user-1',
  full_name: 'Test User',
  email: 'user@sflms.test',
  phone: '0500000000',
  username: 'test-user',
  role: 'role-1',
  role_name: 'construction_manager',
  profile_image: null,
  status: 'active',
  last_login: null,
  created_at: '2026-08-23T10:00:00Z',
  updated_at: '2026-08-23T10:00:00Z',
  ...overrides,
})

const response = (body: unknown, status = 200) =>
  new Response(status === 205 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

afterEach(async () => {
  const { clearAuthTokens } = await import('./client')
  clearAuthTokens()
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('authentication API', () => {
  it('logs in and resolves the canonical current user', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ access: 'access-1', refresh: 'refresh-1' }))
      .mockResolvedValueOnce(response(canonicalUser()))
    vi.stubGlobal('fetch', fetchMock)
    const { login } = await import('./auth')

    const user = await login(' USER@SFLMS.TEST ', 'StrongPass123!')

    expect(user).toMatchObject({ id: 'user-1', role: 'construction_manager' })
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      email: 'user@sflms.test',
      password: 'StrongPass123!',
    })
  })

  it('clears newly issued tokens when the account has no role', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(response({ access: 'access-1', refresh: 'refresh-1' }))
        .mockResolvedValueOnce(response(canonicalUser({ role: null, role_name: null }))),
    )
    const { login } = await import('./auth')
    const { hasStoredSession } = await import('./client')

    await expect(login('roleless@sflms.test', 'StrongPass123!')).rejects.toThrow(
      'This account has no assigned role.',
    )
    expect(hasStoredSession()).toBe(false)
  })

  it('rotates refresh tokens and retries the original request once', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(response({ access: 'access-2', refresh: 'refresh-2' }))
      .mockResolvedValueOnce(response({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    const { apiRequest, getRefreshToken, setAuthTokens } = await import('./client')
    setAuthTokens({ access: 'access-1', refresh: 'refresh-1' })

    await expect(apiRequest('/protected/')).resolves.toEqual({ ok: true })

    expect(getRefreshToken()).toBe('refresh-2')
    const retryHeaders = new Headers(fetchMock.mock.calls[2]?.[1]?.headers)
    expect(retryHeaders.get('Authorization')).toBe('Bearer access-2')
  })

  it('clears the session and notifies listeners when refresh fails', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(response({ detail: 'invalid refresh' }, 401))
    vi.stubGlobal('fetch', fetchMock)
    const { apiRequest, hasStoredSession, onUnauthorized, setAuthTokens } = await import('./client')
    const unauthorized = vi.fn()
    onUnauthorized(unauthorized)
    setAuthTokens({ access: 'access-1', refresh: 'refresh-1' })

    await expect(apiRequest('/protected/')).rejects.toMatchObject({ status: 401 })

    expect(hasStoredSession()).toBe(false)
    expect(unauthorized).toHaveBeenCalledOnce()
  })

  it('logs out with the refresh token and always clears local state', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(null, 205))
    vi.stubGlobal('fetch', fetchMock)
    const { logout } = await import('./auth')
    const { hasStoredSession, setAuthTokens } = await import('./client')
    setAuthTokens({ access: 'access-1', refresh: 'refresh-1' })

    await logout()

    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ refresh: 'refresh-1' })
    expect(hasStoredSession()).toBe(false)
  })

  it('uploads a profile image through the self-profile multipart contract', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(response(canonicalUser({ profile_image: '/media/users/avatar.png' })))
    vi.stubGlobal('fetch', fetchMock)
    const { updateCurrentUser } = await import('./auth')
    const image = new File(['avatar'], 'avatar.png', { type: 'image/png' })

    const user = await updateCurrentUser({
      fullName: 'Test User',
      phone: '0500000000',
      profileImage: image,
    })

    expect(user.profileImageUrl).toMatch(/\/media\/users\/avatar\.png$/)
    const body = fetchMock.mock.calls[0]?.[1]?.body as FormData
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('profile_image')).toBeInstanceOf(File)
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has('Content-Type')).toBe(false)
  })

  it('sends reset uid and token separately to the confirm endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ detail: 'updated' }))
    vi.stubGlobal('fetch', fetchMock)
    const { resetPassword } = await import('./auth')

    await resetPassword('uid-1:token-1', 'ChangedPass456!')

    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      uid: 'uid-1',
      token: 'token-1',
      new_password: 'ChangedPass456!',
      confirm_password: 'ChangedPass456!',
    })
  })
})
