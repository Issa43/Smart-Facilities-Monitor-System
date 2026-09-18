import type { AuditLogEntry } from '@/types'

export interface ProfileActivityEntry extends AuditLogEntry {
  title: string
  body: string
}

const ASSET_ACTIVITY: Record<string, { title: string; verb: string }> = {
  'asset.created': { title: 'إنشاء أصل', verb: 'تم إنشاء' },
  'asset.updated': { title: 'تحديث أصل', verb: 'تم تحديث' },
  'asset.archived': { title: 'أرشفة أصل', verb: 'تمت أرشفة' },
  'asset.status_transitioned': { title: 'تغيير حالة أصل', verb: 'تم تغيير حالة' },
}

function isApiEnvelope(entry: AuditLogEntry): boolean {
  return entry.entity === 'api_endpoint' || entry.action.startsWith('api.')
}

function isDuplicateAssetEnvelope(entry: AuditLogEntry): boolean {
  return isApiEnvelope(entry) && entry.entityRef.startsWith('/api/v1/assets/')
}

function describeApiActivity(entry: AuditLogEntry): Pick<ProfileActivityEntry, 'title' | 'body'> {
  const path = entry.entityRef

  if (/^\/api\/v1\/reports\/requests\/[^/]+\/retry\/$/.test(path)) {
    return {
      title: 'إعادة محاولة إنشاء تقرير',
      body: 'تمت إعادة إرسال طلب التقرير للمعالجة.',
    }
  }
  if (/^\/api\/v1\/reports\/requests\/$/.test(path) && entry.action === 'api.post') {
    return {
      title: 'طلب إنشاء تقرير',
      body: 'تم إرسال طلب جديد لإنشاء تقرير.',
    }
  }
  if (/^\/api\/v1\/faults\/$/.test(path) && entry.action === 'api.post') {
    return { title: 'تسجيل عطل', body: 'تم تسجيل عطل جديد داخل النظام.' }
  }
  if (/^\/api\/v1\/faults\/[^/]+\/(investigate|resolve|close)\/$/.test(path)) {
    return { title: 'تحديث حالة عطل', body: 'تم تنفيذ إجراء على دورة معالجة أحد الأعطال.' }
  }
  if (/^\/api\/v1\/faults\/[^/]+\/$/.test(path) && entry.action === 'api.patch') {
    return { title: 'تحديث بيانات عطل', body: 'تم تحديث بيانات أحد الأعطال.' }
  }
  if (/^\/api\/v1\/maintenance\/orders\/$/.test(path) && entry.action === 'api.post') {
    return { title: 'إنشاء أمر صيانة', body: 'تم إنشاء أمر صيانة جديد.' }
  }
  if (/^\/api\/v1\/maintenance\/orders\/[^/]+\//.test(path)) {
    return { title: 'تحديث أمر صيانة', body: 'تم تنفيذ إجراء على أحد أوامر الصيانة.' }
  }
  if (/^\/api\/v1\/users\/me\/$/.test(path) && entry.action === 'api.patch') {
    return { title: 'تحديث الملف الشخصي', body: 'تم حفظ تعديلات الملف الشخصي.' }
  }

  return {
    title: 'نشاط داخل النظام',
    body: 'تم تنفيذ عملية مسجلة داخل النظام.',
  }
}

function presentActivity(entry: AuditLogEntry): ProfileActivityEntry {
  const assetActivity = ASSET_ACTIVITY[entry.action]
  if (assetActivity) {
    const assetReference = entry.entityRef.trim() || 'الأصل المحدد'
    return {
      ...entry,
      title: assetActivity.title,
      body: `${assetActivity.verb} الأصل ${assetReference}.`,
    }
  }

  const presentation = isApiEnvelope(entry)
    ? describeApiActivity(entry)
    : {
        title: 'نشاط داخل النظام',
        body: 'تم تنفيذ إجراء مسجل داخل النظام.',
      }
  return { ...entry, ...presentation }
}

export function selectProfileActivities(
  entries: AuditLogEntry[],
  actorId: string,
): ProfileActivityEntry[] {
  return entries
    .filter((entry) => entry.actorId === actorId)
    .filter((entry) => !isDuplicateAssetEnvelope(entry))
    .map(presentActivity)
}
