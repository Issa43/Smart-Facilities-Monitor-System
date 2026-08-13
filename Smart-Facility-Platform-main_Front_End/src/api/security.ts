import type { Incident, SecurityAlert, Severity } from '@/types'
import { delay, newId, notFound, nowIso } from './client'
import { clone, commit, getDb } from './db'

/* ==========================================================================
   Alerts — arriving from the external monitoring system
   ========================================================================== */

export async function listAlerts(): Promise<SecurityAlert[]> {
  await delay()
  return clone(
    getDb()
      .alerts.slice()
      .sort((a, b) => b.detectedAt.localeCompare(a.detectedAt)),
  )
}

export async function getAlert(id: string): Promise<SecurityAlert> {
  await delay()
  const alert = getDb().alerts.find((a) => a.id === id)
  return alert ? clone(alert) : notFound('التنبيه')
}

export async function setAlertStatus(
  id: string,
  status: SecurityAlert['status'],
): Promise<SecurityAlert> {
  await delay(250)
  return commit((db) => {
    const alert = db.alerts.find((a) => a.id === id)
    if (!alert) notFound('التنبيه')
    alert.status = status
    return clone(alert)
  })
}

/* ==========================================================================
   Incidents
   ========================================================================== */

export interface IncidentInput {
  facilityId: string
  alertId: string | null
  type: Incident['type']
  description: string
  location: string
  severity: Severity
  assigneeId: string
}

export async function listIncidents(): Promise<Incident[]> {
  await delay()
  return clone(
    getDb()
      .incidents.slice()
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
  )
}

export async function getIncident(id: string): Promise<Incident> {
  await delay()
  const incident = getDb().incidents.find((i) => i.id === id)
  return incident ? clone(incident) : notFound('الحادث')
}

export async function createIncident(input: IncidentInput): Promise<Incident> {
  await delay(400)
  return commit((db) => {
    const incident: Incident = {
      id: newId('inc'),
      reference: `INC-${new Date().getFullYear()}-${String(db.incidents.length + 1).padStart(4, '0')}`,
      ...input,
      status: 'new',
      notes: [],
      actions: [],
      evidence: [],
      escalatedToOperations: false,
      createdAt: nowIso(),
      closedAt: null,
      closedById: null,
      finalReport: null,
    }
    db.incidents.unshift(incident)

    // Escalating an alert links the two records in both directions.
    if (input.alertId) {
      const alert = db.alerts.find((a) => a.id === input.alertId)
      if (alert) {
        alert.status = 'escalated'
        alert.incidentId = incident.id
      }
    }

    db.notifications.unshift({
      id: newId('ntf'),
      title: 'حادث أمني جديد',
      body: `تم تسجيل الحادث ${incident.reference} — ${input.location}.`,
      category: 'security',
      tone: input.severity === 'critical' ? 'critical' : 'warning',
      read: false,
      audience: ['security_officer', 'super_admin'],
      href: null,
      createdAt: nowIso(),
    })

    return clone(incident)
  })
}

export async function updateIncident(
  id: string,
  input: Partial<Pick<Incident, 'description' | 'location' | 'severity' | 'status' | 'assigneeId'>>,
): Promise<Incident> {
  await delay()
  return commit((db) => {
    const incident = db.incidents.find((i) => i.id === id)
    if (!incident) notFound('الحادث')
    Object.assign(incident, input)
    return clone(incident)
  })
}

export async function addIncidentNote(
  id: string,
  body: string,
  authorId: string,
): Promise<Incident> {
  await delay(250)
  return commit((db) => {
    const incident = db.incidents.find((i) => i.id === id)
    if (!incident) notFound('الحادث')
    incident.notes.push({ id: newId('n'), body, authorId, createdAt: nowIso() })
    return clone(incident)
  })
}

export async function addIncidentAction(id: string, label: string): Promise<Incident> {
  await delay(250)
  return commit((db) => {
    const incident = db.incidents.find((i) => i.id === id)
    if (!incident) notFound('الحادث')
    incident.actions.push({ id: newId('a'), label, done: false, takenAt: null })
    return clone(incident)
  })
}

export async function toggleIncidentAction(id: string, actionId: string): Promise<Incident> {
  await delay(120)
  return commit((db) => {
    const incident = db.incidents.find((i) => i.id === id)
    if (!incident) notFound('الحادث')
    const action = incident.actions.find((a) => a.id === actionId)
    if (action) {
      action.done = !action.done
      action.takenAt = action.done ? nowIso() : null
    }
    return clone(incident)
  })
}

export async function addIncidentEvidence(
  id: string,
  caption: string,
  gradient: string,
): Promise<Incident> {
  await delay(300)
  return commit((db) => {
    const incident = db.incidents.find((i) => i.id === id)
    if (!incident) notFound('الحادث')
    incident.evidence.push({ id: newId('e'), caption, gradient })
    return clone(incident)
  })
}

/** Hands the incident to operations when it needs a physical repair. */
export async function escalateToOperations(id: string): Promise<Incident> {
  await delay(350)
  return commit((db) => {
    const incident = db.incidents.find((i) => i.id === id)
    if (!incident) notFound('الحادث')

    incident.escalatedToOperations = true
    incident.status = 'action_required'

    db.notifications.unshift({
      id: newId('ntf'),
      title: 'حادث محوّل لمدير التشغيل',
      body: `الحادث ${incident.reference} يتطلب إصلاحاً فنياً — ${incident.location}.`,
      category: 'security',
      tone: 'warning',
      read: false,
      audience: ['operations_manager', 'super_admin'],
      href: null,
      createdAt: nowIso(),
    })

    return clone(incident)
  })
}

export async function closeIncident(
  id: string,
  finalReport: string,
  closedById: string,
): Promise<Incident> {
  await delay(500)
  return commit((db) => {
    const incident = db.incidents.find((i) => i.id === id)
    if (!incident) notFound('الحادث')

    incident.status = 'closed'
    incident.closedAt = nowIso()
    incident.closedById = closedById
    incident.finalReport = finalReport

    return clone(incident)
  })
}
