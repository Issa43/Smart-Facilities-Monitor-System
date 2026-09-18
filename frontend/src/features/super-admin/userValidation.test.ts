import { describe, expect, it } from 'vitest'

import { createUserSchema } from './userValidation'

const validInput = {
  fullName: 'Phase Two User',
  email: 'phase-two@sflms.test',
  phone: '0500000000',
  username: 'phase_two_user',
  password: 'StrongPass123!',
  role: 'construction_manager',
  status: 'active',
}

describe('create-user password validation', () => {
  it.each(['password', '12345678', 'Short1!', 'phase_two_user'])(
    'rejects %s before submission',
    (password) => {
      const result = createUserSchema.safeParse({ ...validInput, password })
      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues.some((issue) => issue.path[0] === 'password')).toBe(true)
      }
    },
  )

  it('accepts a strong password for server-side validation', () => {
    expect(createUserSchema.safeParse(validInput).success).toBe(true)
  })
})
