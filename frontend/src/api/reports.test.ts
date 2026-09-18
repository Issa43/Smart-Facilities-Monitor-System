import { afterEach, describe, expect, it, vi } from 'vitest'

import { clearAuthTokens, downloadProtectedFile } from './client'
import { generateReport, listGeneratedReports, retryGeneratedReport } from './reports'
import { updateSystemSetting } from './settings'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  clearAuthTokens()
})

describe('API contracts', () => {
  it.each(['pdf', 'excel'] as const)(
    'submits the frozen Construction Project Report v1 scope for %s',
    async (format) => {
      const fetchMock = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            id: `construction-${format}`,
            type: 'construction',
            module: 'construction',
            parameters: {
              project_id: 'project-1',
              date_from: '2026-01-01',
              date_to: '2026-01-31',
              period_label: 'January 2026',
            },
            format,
            status: 'queued',
            failure_details: null,
            download_available: false,
            file_size: null,
            created_by_id: 'user-1',
            created_at: '2026-01-31T00:00:00Z',
          }),
          { status: 202, headers: { 'Content-Type': 'application/json' } },
        ),
      )
      vi.stubGlobal('fetch', fetchMock)

      await generateReport({
        kind: 'construction',
        format,
        periodLabel: 'January 2026',
        projectId: 'project-1',
        dateFrom: '2026-01-01',
        dateTo: '2026-01-31',
        generatedById: 'user-1',
      })

      const [, request] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(JSON.parse(String(request.body))).toEqual({
        type: 'construction',
        module: 'construction',
        format,
        parameters: {
          period_label: 'January 2026',
          project_id: 'project-1',
          date_from: '2026-01-01',
          date_to: '2026-01-31',
        },
      })
    },
  )

  it('maps operational fault reports to the faults module and preserves facility scope', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'report-1',
          type: 'faults',
          module: 'faults',
          parameters: { period_label: '30 days', facility_id: 'facility-1' },
          format: 'pdf',
          status: 'queued',
          failure_details: null,
          download_available: false,
          file_size: null,
          created_by_id: 'user-1',
          created_at: '2026-08-16T00:00:00Z',
        }),
        { status: 202, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await generateReport({
      kind: 'faults',
      format: 'pdf',
      periodLabel: '30 days',
      facilityId: 'facility-1',
      generatedById: 'user-1',
    })

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(request.body))).toMatchObject({
      module: 'faults',
      parameters: { period_label: '30 days', facility_id: 'facility-1' },
    })
  })

  it('maps the serialized report byte size to the displayed kilobytes', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 'report-1',
              type: 'construction',
              module: 'construction',
              parameters: { period_label: '30 days' },
              format: 'excel',
              status: 'completed',
              failure_details: null,
              download_available: true,
              file_size: 1517,
              created_by_id: 'user-1',
              created_at: '2026-08-16T00:00:00Z',
            },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(listGeneratedReports()).resolves.toEqual([
      expect.objectContaining({ id: 'report-1', sizeKb: 2 }),
    ])
  })

  it('reads the API-provided filename and binary response for a report download', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('valid-report-bytes', {
        status: 200,
        headers: {
          'Content-Type': 'application/pdf',
          'Content-Disposition': 'attachment; filename="report-report-1.pdf"',
          'Content-Length': '18',
        },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const file = await downloadProtectedFile('/reports/requests/report-1/download/')

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/reports/requests/report-1/download/')
    expect(file.filename).toBe('report-report-1.pdf')
    expect(file.blob.size).toBe(18)
    expect(file.blob.type).toBe('application/pdf')
  })

  it('sends optimistic version data when changing a system setting', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'setting-1',
          key: 'workflow.autoIncident',
          value: true,
          description: '',
          version: 4,
          updated_at: '2026-08-16T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await updateSystemSetting(
      {
        id: 'setting-1',
        key: 'workflow.autoIncident',
        value: false,
        description: '',
        version: 3,
        updated_at: '2026-08-15T00:00:00Z',
      },
      true,
    )

    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/settings/workflow.autoIncident/')
    expect(JSON.parse(String(request.body))).toEqual({ value: true, version: 3 })
  })

  it('retries a failed report through the canonical action', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'report-1',
          type: 'construction',
          module: 'construction',
          parameters: { period_label: '30 days' },
          format: 'pdf',
          status: 'queued',
          failure_details: null,
          download_available: false,
          file_size: null,
          created_by_id: 'user-1',
          created_at: '2026-08-16T00:00:00Z',
        }),
        { status: 202, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await retryGeneratedReport('report-1')

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/reports/requests/report-1/retry/')
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('POST')
  })
})
