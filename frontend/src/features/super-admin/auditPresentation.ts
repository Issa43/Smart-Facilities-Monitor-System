import type { AuditLogEntry, Tone } from '@/types'

export interface AuditPresentation {
  title: string
  entityLabel: string
  reference: string
  technical: boolean
  tone: Tone
}

const SEMANTIC_ACTIONS: Record<
  string,
  Pick<AuditPresentation, 'title' | 'entityLabel' | 'tone'>
> = {
  'material_request.reviewed': {
    title: 'مراجعة طلب توريد مواد',
    entityLabel: 'طلب توريد مواد',
    tone: 'info',
  },
  'material_request.approved': {
    title: 'اعتماد طلب توريد مواد',
    entityLabel: 'طلب توريد مواد',
    tone: 'success',
  },
  'material_request.rejected': {
    title: 'رفض طلب توريد مواد',
    entityLabel: 'طلب توريد مواد',
    tone: 'critical',
  },
  'asset.created': { title: 'إنشاء أصل', entityLabel: 'أصل', tone: 'success' },
  'asset.updated': { title: 'تحديث بيانات أصل', entityLabel: 'أصل', tone: 'info' },
  'asset.archived': { title: 'أرشفة أصل', entityLabel: 'أصل', tone: 'warning' },
  'asset.status_transitioned': {
    title: 'تغيير حالة أصل',
    entityLabel: 'أصل',
    tone: 'info',
  },
  'role.permissions.updated': {
    title: 'تحديث صلاحيات دور',
    entityLabel: 'دور وظيفي',
    tone: 'warning',
  },
  'authentication.password_reset': {
    title: 'إعادة تعيين كلمة المرور',
    entityLabel: 'حساب مستخدم',
    tone: 'warning',
  },
  'security_alert.reviewed': {
    title: 'مراجعة تنبيه أمني',
    entityLabel: 'تنبيه أمني',
    tone: 'info',
  },
  'security_alert.dismissed': {
    title: 'تصنيف تنبيه كإنذار كاذب',
    entityLabel: 'تنبيه أمني',
    tone: 'neutral',
  },
  'security_alert.converted_to_incident': {
    title: 'تحويل تنبيه إلى حادث',
    entityLabel: 'تنبيه أمني',
    tone: 'warning',
  },
  'safety_alert.created': {
    title: 'إنشاء إنذار سلامة من خطر خارجي',
    entityLabel: 'إنذار سلامة',
    tone: 'warning',
  },
  'safety_alert.escalated': {
    title: 'تصعيد خطورة إنذار سلامة',
    entityLabel: 'إنذار سلامة',
    tone: 'critical',
  },
  'safety_alert.hazard_withdrawn': {
    title: 'سحب المصدر لحدث إنذار سلامة',
    entityLabel: 'إنذار سلامة',
    tone: 'neutral',
  },
  'safety_alert.acknowledged': {
    title: 'إقرار الاطلاع على إنذار سلامة',
    entityLabel: 'إنذار سلامة',
    tone: 'info',
  },
  'safety_alert.action_decided': {
    title: 'تسجيل قرار لإنذار سلامة',
    entityLabel: 'إنذار سلامة',
    tone: 'info',
  },
  'safety_alert.dismissed': {
    title: 'استبعاد إنذار سلامة',
    entityLabel: 'إنذار سلامة',
    tone: 'neutral',
  },
  'safety_alert.closed': {
    title: 'إغلاق إنذار سلامة',
    entityLabel: 'إنذار سلامة',
    tone: 'success',
  },
  'camera_event.created': {
    title: 'إنشاء حدث كاميرا',
    entityLabel: 'حدث كاميرا',
    tone: 'success',
  },
  'security_alert.created_from_camera_event': {
    title: 'إنشاء تنبيه أمني من حدث كاميرا',
    entityLabel: 'تنبيه أمني',
    tone: 'critical',
  },
  'camera_roi.created': {
    title: 'إنشاء منطقة مراقبة',
    entityLabel: 'منطقة مراقبة',
    tone: 'success',
  },
  'camera_roi.updated': {
    title: 'تحديث منطقة مراقبة',
    entityLabel: 'منطقة مراقبة',
    tone: 'info',
  },
  'camera_roi.disabled': {
    title: 'تعطيل منطقة مراقبة',
    entityLabel: 'منطقة مراقبة',
    tone: 'warning',
  },
  'restricted_schedule.created': {
    title: 'إنشاء جدول تقييد',
    entityLabel: 'جدول تقييد',
    tone: 'success',
  },
  'restricted_schedule.updated': {
    title: 'تحديث جدول تقييد',
    entityLabel: 'جدول تقييد',
    tone: 'info',
  },
  'restricted_schedule.disabled': {
    title: 'تعطيل جدول تقييد',
    entityLabel: 'جدول تقييد',
    tone: 'warning',
  },
  'virtual_line.created': {
    title: 'إنشاء خط افتراضي',
    entityLabel: 'خط افتراضي',
    tone: 'success',
  },
  'virtual_line.updated': {
    title: 'تحديث خط افتراضي',
    entityLabel: 'خط افتراضي',
    tone: 'info',
  },
  'virtual_line.disabled': {
    title: 'تعطيل خط افتراضي',
    entityLabel: 'خط افتراضي',
    tone: 'warning',
  },
  'authorized_vehicle.created': {
    title: 'إنشاء مركبة مصرح بها',
    entityLabel: 'مركبة مصرح بها',
    tone: 'success',
  },
  'authorized_vehicle.updated': {
    title: 'تحديث مركبة مصرح بها',
    entityLabel: 'مركبة مصرح بها',
    tone: 'info',
  },
  'authorized_vehicle.disabled': {
    title: 'تعطيل مركبة مصرح بها',
    entityLabel: 'مركبة مصرح بها',
    tone: 'warning',
  },
  'camera_ai_model.enabled': {
    title: 'تفعيل نموذج ذكاء اصطناعي',
    entityLabel: 'إعداد نموذج ذكاء اصطناعي',
    tone: 'success',
  },
  'camera_ai_model.disabled': {
    title: 'تعطيل نموذج ذكاء اصطناعي',
    entityLabel: 'إعداد نموذج ذكاء اصطناعي',
    tone: 'warning',
  },
  'ai_ingestion_credential.created': {
    title: 'إنشاء بيانات اعتماد AI',
    entityLabel: 'بيانات اعتماد AI',
    tone: 'success',
  },
  'ai_ingestion_credential.rotated': {
    title: 'تدوير بيانات اعتماد AI',
    entityLabel: 'بيانات اعتماد AI',
    tone: 'warning',
  },
  'ai_ingestion_credential.revoked': {
    title: 'إلغاء بيانات اعتماد AI',
    entityLabel: 'بيانات اعتماد AI',
    tone: 'critical',
  },
  'ai_ingestion_credential.scope_added': {
    title: 'إضافة نطاق كاميرا AI',
    entityLabel: 'نطاق كاميرا AI',
    tone: 'success',
  },
  'ai_ingestion_credential.scope_removed': {
    title: 'إزالة نطاق كاميرا AI',
    entityLabel: 'نطاق كاميرا AI',
    tone: 'warning',
  },
}

const ENTITY_LABELS: Record<string, string> = {
  api_endpoint: 'سجلات تقنية',
  'materials.materialrequest': 'طلب توريد مواد',
  'assets.asset': 'أصل',
  'users.role': 'دور وظيفي',
  'users.user': 'حساب مستخدم',
  'security.securityalert': 'تنبيه أمني',
  'security.cameraevent': 'حدث كاميرا',
  'security.cameraroi': 'منطقة مراقبة',
  'security.restrictedzoneschedule': 'جدول تقييد',
  'security.virtualline': 'خط افتراضي',
  'security.authorizedvehicle': 'مركبة مصرح بها',
  'security.cameraaimodel': 'إعداد نموذج ذكاء اصطناعي',
  'security.aiingestioncredential': 'بيانات اعتماد AI',
  'security.aiingestioncamerascope': 'نطاق كاميرا AI',
  'safety.projectsafetyalert': 'إنذار سلامة',
}

export function auditEntityLabel(entity: string): string {
  return ENTITY_LABELS[entity] ?? 'سجل أعمال'
}

function isTechnical(entry: AuditLogEntry): boolean {
  return entry.entity === 'api_endpoint' || entry.action.startsWith('api.')
}

function genericPresentation(entry: AuditLogEntry): AuditPresentation {
  const path = entry.entityRef

  if (/^\/api\/v1\/reports\/requests\/$/.test(path) && entry.action === 'api.post') {
    return {
      title: 'طلب إنشاء تقرير',
      entityLabel: '—',
      reference: 'إرسال تقرير جديد للمعالجة',
      technical: true,
      tone: 'info',
    }
  }
  if (/^\/api\/v1\/construction\/material-requests\/$/.test(path)) {
    return {
      title: 'إنشاء طلب توريد مواد',
      entityLabel: '—',
      reference: 'طلب جديد ضمن مشروع إنشائي',
      technical: true,
      tone: 'info',
    }
  }
  if (/^\/api\/v1\/construction\/materials\/[^/]+\/consumption\/$/.test(path)) {
    return {
      title: 'تسجيل استهلاك مادة',
      entityLabel: '—',
      reference: 'تحديث كمية الاستهلاك المسجلة',
      technical: true,
      tone: 'info',
    }
  }
  if (/^\/api\/v1\/construction\/materials\/[^/]+\/$/.test(path)) {
    return {
      title: 'تحديث بيانات مادة',
      entityLabel: '—',
      reference: 'تعديل سجل مادة في مشروع',
      technical: true,
      tone: 'info',
    }
  }

  return {
    title: 'عملية تقنية',
    entityLabel: '—',
    reference: 'التفاصيل التقنية متاحة في سجل العملية',
    technical: true,
    tone: 'neutral',
  }
}

export function presentAuditEntry(entry: AuditLogEntry): AuditPresentation {
  const semantic = SEMANTIC_ACTIONS[entry.action]
  if (semantic) {
    return {
      ...semantic,
      reference: entry.entityRef.trim() || '—',
      technical: false,
    }
  }
  if (isTechnical(entry)) return genericPresentation(entry)

  return {
    title: 'نشاط مسجل',
    entityLabel: auditEntityLabel(entry.entity),
    reference: entry.entityRef.trim() || '—',
    technical: false,
    tone: 'neutral',
  }
}

const CORRELATION_WINDOW_MS = 5_000

type OperationMatcher = { methods: string[]; path: RegExp }

const OPERATION_MATCHERS: Record<string, OperationMatcher> = {
  'camera_event.created': { methods: ['api.post'], path: /^\/api\/v1\/camera-events\/$/ },
  'security_alert.created_from_camera_event': {
    methods: ['api.post'],
    path: /^\/api\/v1\/camera-events\/$/,
  },
  'security_alert.reviewed': {
    methods: ['api.post'],
    path: /^\/api\/v1\/security\/alerts\/[^/]+\/review\/$/,
  },
  'security_alert.dismissed': {
    methods: ['api.post'],
    path: /^\/api\/v1\/security\/alerts\/[^/]+\/dismiss\/$/,
  },
  'security_alert.converted_to_incident': {
    methods: ['api.post'],
    path: /^\/api\/v1\/security\/alerts\/[^/]+\/convert-to-incident\/$/,
  },
  'safety_alert.acknowledged': {
    methods: ['api.post'],
    path: /^\/api\/v1\/safety\/alerts\/[^/]+\/acknowledge\/$/,
  },
  'safety_alert.action_decided': {
    methods: ['api.post'],
    path: /^\/api\/v1\/safety\/alerts\/[^/]+\/decide\/$/,
  },
  'safety_alert.dismissed': {
    methods: ['api.post'],
    path: /^\/api\/v1\/safety\/alerts\/[^/]+\/dismiss\/$/,
  },
  'safety_alert.closed': {
    methods: ['api.post'],
    path: /^\/api\/v1\/safety\/alerts\/[^/]+\/close\/$/,
  },
  'camera_roi.created': { methods: ['api.post'], path: /^\/api\/v1\/roi\/$/ },
  'camera_roi.updated': { methods: ['api.patch', 'api.put'], path: /^\/api\/v1\/roi\/[^/]+\/$/ },
  'camera_roi.disabled': { methods: ['api.delete'], path: /^\/api\/v1\/roi\/[^/]+\/$/ },
  'restricted_schedule.created': {
    methods: ['api.post'],
    path: /^\/api\/v1\/restricted-schedules\/$/,
  },
  'restricted_schedule.updated': {
    methods: ['api.patch', 'api.put'],
    path: /^\/api\/v1\/restricted-schedules\/[^/]+\/$/,
  },
  'restricted_schedule.disabled': {
    methods: ['api.delete'],
    path: /^\/api\/v1\/restricted-schedules\/[^/]+\/$/,
  },
  'virtual_line.created': { methods: ['api.post'], path: /^\/api\/v1\/virtual-lines\/$/ },
  'virtual_line.updated': {
    methods: ['api.patch', 'api.put'],
    path: /^\/api\/v1\/virtual-lines\/[^/]+\/$/,
  },
  'virtual_line.disabled': {
    methods: ['api.delete'],
    path: /^\/api\/v1\/virtual-lines\/[^/]+\/$/,
  },
  'authorized_vehicle.created': {
    methods: ['api.post'],
    path: /^\/api\/v1\/vehicles\/authorized\/$/,
  },
  'authorized_vehicle.updated': {
    methods: ['api.patch', 'api.put'],
    path: /^\/api\/v1\/vehicles\/authorized\/[^/]+\/$/,
  },
  'authorized_vehicle.disabled': {
    methods: ['api.delete'],
    path: /^\/api\/v1\/vehicles\/authorized\/[^/]+\/$/,
  },
  'camera_ai_model.enabled': {
    methods: ['api.post'],
    path: /^\/api\/v1\/cameras\/[^/]+\/active-models\/$/,
  },
  'camera_ai_model.disabled': {
    methods: ['api.delete'],
    path: /^\/api\/v1\/cameras\/[^/]+\/active-models\/[^/]+\/$/,
  },
  'ai_ingestion_credential.created': {
    methods: ['api.post'],
    path: /^\/api\/v1\/admin\/ai-ingestion-credentials\/$/,
  },
  'ai_ingestion_credential.rotated': {
    methods: ['api.post'],
    path: /^\/api\/v1\/admin\/ai-ingestion-credentials\/[^/]+\/rotate\/$/,
  },
  'ai_ingestion_credential.revoked': {
    methods: ['api.post'],
    path: /^\/api\/v1\/admin\/ai-ingestion-credentials\/[^/]+\/revoke\/$/,
  },
  'ai_ingestion_credential.scope_added': {
    methods: ['api.post'],
    path: /^\/api\/v1\/admin\/ai-ingestion-credentials\/[^/]+\/scopes\/$/,
  },
  'ai_ingestion_credential.scope_removed': {
    methods: ['api.delete'],
    path: /^\/api\/v1\/admin\/ai-ingestion-credentials\/[^/]+\/scopes\/[^/]+\/$/,
  },
}

function representsSameOperation(generic: AuditLogEntry, semantic: AuditLogEntry): boolean {
  if (!isTechnical(generic) || generic.actorId !== semantic.actorId) return false
  const elapsed = Date.parse(generic.createdAt) - Date.parse(semantic.createdAt)
  if (!Number.isFinite(elapsed) || elapsed < 0 || elapsed > CORRELATION_WINDOW_MS) return false

  const action = semantic.action
  const path = generic.entityRef
  if (action === 'material_request.reviewed')
    return generic.action === 'api.post' && /\/material-requests\/[^/]+\/review\/$/.test(path)
  if (action === 'material_request.approved')
    return generic.action === 'api.post' && /\/material-requests\/[^/]+\/approve\/$/.test(path)
  if (action === 'material_request.rejected')
    return generic.action === 'api.post' && /\/material-requests\/[^/]+\/reject\/$/.test(path)
  if (action === 'asset.created') return generic.action === 'api.post' && /\/assets\/$/.test(path)
  if (action === 'asset.updated')
    return /^api\.(patch|put)$/.test(generic.action) && /\/assets\/[^/]+\/$/.test(path)
  if (action === 'asset.archived')
    return generic.action === 'api.delete' && /\/assets\/[^/]+\/$/.test(path)
  if (action === 'asset.status_transitioned')
    return generic.action === 'api.post' && /\/assets\/[^/]+\/transition-status\/$/.test(path)
  if (action === 'role.permissions.updated')
    return (
      /^api\.(patch|put)$/.test(generic.action) &&
      /\/users\/roles\/[^/]+\/permissions\/$/.test(path)
    )

  const matcher = OPERATION_MATCHERS[action]
  return Boolean(matcher?.methods.includes(generic.action) && matcher.path.test(path))
}

export function selectLatestOperations(entries: AuditLogEntry[], limit = 8): AuditLogEntry[] {
  const semanticEntries = entries.filter((entry) => !isTechnical(entry))
  const matchedSemantics = new Set<AuditLogEntry>()
  const suppressedEnvelopes = new Set<AuditLogEntry>()

  for (const envelope of entries.filter(isTechnical)) {
    const match = semanticEntries
      .filter((semantic) => !matchedSemantics.has(semantic))
      .filter((semantic) => representsSameOperation(envelope, semantic))
      .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))[0]
    if (match) {
      matchedSemantics.add(match)
      suppressedEnvelopes.add(envelope)
    }
  }

  return entries.filter((entry) => !suppressedEnvelopes.has(entry)).slice(0, limit)
}
