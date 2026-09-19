import { z } from 'zod'

const COMMON_PASSWORDS = new Set([
  'admin',
  'letmein',
  'password',
  'password1',
  'password123',
  'qwerty',
  'qwerty123',
  'welcome',
])

function quickSimilarity(left: string, right: string): number {
  if (!left.length && !right.length) return 1
  const remaining = new Map<string, number>()
  for (const character of right) {
    remaining.set(character, (remaining.get(character) ?? 0) + 1)
  }
  let matches = 0
  for (const character of left) {
    const count = remaining.get(character) ?? 0
    if (count > 0) {
      matches += 1
      remaining.set(character, count - 1)
    }
  }
  return (2 * matches) / (left.length + right.length)
}

function exceedsMaximumLengthRatio(password: string, value: string): boolean {
  const maxSimilarity = 0.7
  const lengthBoundSimilarity = (maxSimilarity / 2) * password.length
  return password.length >= 10 * value.length && value.length < lengthBoundSimilarity
}

function isTooSimilar(password: string, values: { username: string; email: string }): boolean {
  const normalizedPassword = password.toLowerCase()
  return [values.username, values.email].some((attribute) => {
    const normalizedAttribute = attribute.toLowerCase()
    const parts = [...normalizedAttribute.split(/\W+/).filter(Boolean), normalizedAttribute]
    return parts.some(
      (part) =>
        !exceedsMaximumLengthRatio(normalizedPassword, part) &&
        quickSimilarity(normalizedPassword, part) >= 0.7,
    )
  })
}

export const createUserSchema = z
  .object({
    fullName: z.string().trim().min(3, 'أدخل الاسم الكامل'),
    email: z.string().trim().min(1, 'أدخل البريد الإلكتروني').email('صيغة البريد غير صحيحة'),
    phone: z
      .string()
      .trim()
      .regex(/^05\d{8}$/, 'رقم الجوال يجب أن يبدأ بـ 05 ويتكون من 10 أرقام'),
    username: z
      .string()
      .trim()
      .min(3, 'اسم المستخدم يجب ألا يقل عن 3 أحرف')
      .regex(/^[a-zA-Z0-9._-]+$/, 'يُسمح بالحروف اللاتينية والأرقام والنقطة والشرطة فقط'),
    password: z.string().min(8, 'كلمة المرور يجب ألا تقل عن 8 أحرف'),
    role: z.string().min(1, 'اختر الدور الوظيفي'),
    status: z.string().min(1, 'اختر حالة الحساب'),
  })
  .superRefine((values, context) => {
    const normalizedPassword = values.password.toLowerCase()
    if (/^\d+$/.test(values.password)) {
      context.addIssue({
        code: 'custom',
        path: ['password'],
        message: 'كلمة المرور لا يمكن أن تتكون من أرقام فقط',
      })
    }
    if (COMMON_PASSWORDS.has(normalizedPassword)) {
      context.addIssue({
        code: 'custom',
        path: ['password'],
        message: 'كلمة المرور شائعة جداً؛ اختر كلمة أقوى',
      })
    }
    if (isTooSimilar(values.password, values)) {
      context.addIssue({
        code: 'custom',
        path: ['password'],
        message: 'كلمة المرور مشابهة جداً لاسم المستخدم أو البريد الإلكتروني',
      })
    }
  })

export type CreateUserFormValues = z.infer<typeof createUserSchema>
