// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest'

const jsonResponse = (body: unknown, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('construction record contracts', () => {
  it('uses scoped detail and patch endpoints for daily reports', async () => {
    const dto = {
      id: 'report-1',
      project_id: 'project-1',
      title: 'Daily report',
      summary: 'Completed scheduled work',
      progress_percentage: '25.00',
      workforce_count: 12,
      photo_count: 1,
      author_id: 'manager-1',
      author_name: 'Scoped Author',
      report_date: '2026-09-06',
    }
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(dto)))
    vi.stubGlobal('fetch', fetchMock)
    const { getDailyReport, updateDailyReport } = await import('./construction')

    const detail = await getDailyReport('report-1')
    const updated = await updateDailyReport('report-1', {
      title: 'Updated daily report',
      progressPercent: 35,
    })

    expect(detail.authorName).toBe('Scoped Author')
    expect(updated.id).toBe('report-1')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/construction/daily-reports/report-1/')
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBeUndefined()
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/construction/daily-reports/report-1/')
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe('PATCH')
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      title: 'Updated daily report',
      progress_percentage: 35,
    })
  })

  it('uses canonical scoped delete endpoints for every record workflow', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(null, 204))
    vi.stubGlobal('fetch', fetchMock)
    const { deleteDailyReport, deleteDocument, deleteInspection, deleteSitePhoto } =
      await import('./construction')

    await deleteDailyReport('report-1')
    await deleteInspection('inspection-1')
    await deleteDocument('document-1')
    await deleteSitePhoto('photo-1')

    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual(
      expect.arrayContaining([
        expect.stringContaining('/construction/daily-reports/report-1/'),
        expect.stringContaining('/construction/quality-inspections/inspection-1/'),
        expect.stringContaining('/construction/documents/document-1/'),
        expect.stringContaining('/construction/site-photos/photo-1/'),
      ]),
    )
    expect(fetchMock.mock.calls.every(([, init]) => init?.method === 'DELETE')).toBe(true)
  })

  it('downloads documents only through the protected API action', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('protected', {
        status: 200,
        headers: { 'Content-Type': 'application/pdf' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:protected-document')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const { setAuthTokens } = await import('./client')
    const { downloadDocument } = await import('./construction')
    setAuthTokens({ access: 'access-1', refresh: 'refresh-1' })

    await downloadDocument('document-1', 'approved.pdf')

    expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
      '/construction/documents/document-1/download/',
    )
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers)
    expect(headers.get('Authorization')).toBe('Bearer access-1')
  })

  it('maps actor display names supplied by scoped Construction responses', async () => {
    const page = (results: unknown[]) => ({ count: results.length, next: null, results })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          page([
            {
              id: 'inspection-1',
              project_id: 'project-1',
              phase_id: 'phase-1',
              title: 'Concrete inspection',
              inspector_id: 'manager-1',
              inspector_name: 'Scoped Inspector',
              score: '92.00',
              result: 'passed',
              notes: '',
              inspected_at: '2026-09-06T10:00:00Z',
            },
          ]),
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          page([
            {
              id: 'report-1',
              project_id: 'project-1',
              title: 'Daily report',
              summary: 'Completed work',
              progress_percentage: '25.00',
              workforce_count: 12,
              photo_count: 1,
              author_id: 'manager-1',
              author_name: 'Scoped Author',
              report_date: '2026-09-06',
            },
          ]),
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          page([
            {
              id: 'document-1',
              project_id: 'project-1',
              title: 'Approved drawing',
              document_type: 'drawing',
              original_file_name: 'drawing.pdf',
              mime_type: 'application/pdf',
              file_size: 1024,
              uploaded_by_id: 'manager-1',
              uploaded_by_name: 'Scoped Uploader',
              uploaded_at: '2026-09-06T10:00:00Z',
              download_url: '/api/v1/construction/documents/document-1/download/',
            },
          ]),
        ),
      )
    vi.stubGlobal('fetch', fetchMock)
    const { listDailyReports, listDocuments, listInspections } = await import('./construction')

    const inspections = await listInspections('project-1')
    const reports = await listDailyReports('project-1')
    const documents = await listDocuments('project-1')

    expect(inspections[0]?.inspectorName).toBe('Scoped Inspector')
    expect(reports[0]?.authorName).toBe('Scoped Author')
    expect(documents[0]?.uploadedByName).toBe('Scoped Uploader')
  })
})
