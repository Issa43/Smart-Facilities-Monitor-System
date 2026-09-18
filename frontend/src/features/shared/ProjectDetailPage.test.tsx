// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectDetailPage } from './ProjectDetailPage'

const mocks = vi.hoisted(() => ({
  completeProject: vi.fn(),
  convertProjectToFacility: vi.fn(),
  getProject: vi.fn(),
  listDailyReports: vi.fn(),
  listDocuments: vi.fn(),
  listInspections: vi.fn(),
  listMaterialRequests: vi.fn(),
  listMaterials: vi.fn(),
  listSitePhotos: vi.fn(),
  listStages: vi.fn(),
  showToast: vi.fn(),
  startProject: vi.fn(),
  updateAssignedProject: vi.fn(),
}))

vi.mock('@/api/construction', () => ({
  completeProject: mocks.completeProject,
  convertProjectToFacility: mocks.convertProjectToFacility,
  getProject: mocks.getProject,
  listDailyReports: mocks.listDailyReports,
  listDocuments: mocks.listDocuments,
  listInspections: mocks.listInspections,
  listMaterialRequests: mocks.listMaterialRequests,
  listMaterials: mocks.listMaterials,
  listSitePhotos: mocks.listSitePhotos,
  listStages: mocks.listStages,
  startProject: mocks.startProject,
  updateAssignedProject: mocks.updateAssignedProject,
}))
vi.mock('@/context/AuthContext', () => ({
  useCurrentUser: () => ({ id: 'manager-1', role: 'construction_manager' }),
}))
vi.mock('@/context/ToastContext', () => ({ useToast: () => ({ showToast: mocks.showToast }) }))

const project = {
  id: 'project-1',
  name: 'مشروع الاختبار',
  facilityType: 'commercial' as const,
  description: 'وصف المشروع الحالي',
  location: 'القاهرة',
  startDate: '2026-08-01',
  expectedEndDate: '2026-12-01',
  status: 'in_progress' as const,
  imageUrl: null,
  constructionManagerId: 'manager-1',
  constructionManagerName: 'Scoped Project Manager',
  progressPercent: 25,
  currentStageName: 'الأساسات',
  updatedAt: '2026-08-24T10:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/construction/projects/project-1']}>
        <Routes>
          <Route
            path="/construction/projects/:projectId"
            element={<ProjectDetailPage basePath="/construction" role="construction_manager" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Construction Manager project detail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getProject.mockResolvedValue(project)
    for (const mock of [
      mocks.listDailyReports,
      mocks.listDocuments,
      mocks.listInspections,
      mocks.listMaterialRequests,
      mocks.listMaterials,
      mocks.listSitePhotos,
      mocks.listStages,
    ]) {
      mock.mockResolvedValue([])
    }
    mocks.updateAssignedProject.mockImplementation(async (_id, input) => ({
      ...project,
      ...input,
    }))
    mocks.completeProject.mockResolvedValue({ ...project, status: 'completed' })
  })

  it('exposes the assigned-project metadata editor without assignment controls', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /تعديل البيانات/ }))
    const dialog = screen.getByRole('dialog', { name: 'تعديل بيانات المشروع' })
    const name = within(dialog).getByLabelText(/اسم المشروع/)
    expect(name).toHaveValue('مشروع الاختبار')
    expect(within(dialog).queryByLabelText(/مدير الإنشاءات/)).not.toBeInTheDocument()
  })

  it('exposes project completion to the assigned Construction Manager', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: /إكمال المشروع/ }))

    await waitFor(() =>
      expect(mocks.completeProject).toHaveBeenCalledWith('project-1', expect.any(String)),
    )
  })

  it('renders actor names delivered by scoped Construction resources', async () => {
    const user = userEvent.setup()
    mocks.listInspections.mockResolvedValue([
      {
        id: 'inspection-1',
        projectId: 'project-1',
        stageId: 'phase-1',
        title: 'Inspection',
        inspectorId: 'manager-2',
        inspectorName: 'Scoped Inspector',
        score: 90,
        result: 'passed',
        notes: '',
        inspectedAt: '2026-09-06T10:00:00Z',
      },
    ])
    mocks.listDailyReports.mockResolvedValue([
      {
        id: 'report-1',
        projectId: 'project-1',
        title: 'Report',
        summary: 'Summary',
        progressPercent: 25,
        workforceCount: 10,
        photoCount: 0,
        authorId: 'manager-2',
        authorName: 'Scoped Author',
        reportDate: '2026-09-06',
      },
    ])
    mocks.listDocuments.mockResolvedValue([
      {
        id: 'document-1',
        projectId: 'project-1',
        name: 'Drawing',
        category: 'drawing',
        fileType: 'pdf',
        sizeKb: 1,
        uploadedById: 'manager-2',
        uploadedByName: 'Scoped Uploader',
        uploadedAt: '2026-09-06T10:00:00Z',
      },
    ])

    renderPage()

    expect(await screen.findByText('Scoped Project Manager')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /الجودة/ }))
    expect(await screen.findByText('Scoped Inspector')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /التقارير اليومية/ }))
    expect(await screen.findByText('Scoped Author')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /الوثائق/ }))
    expect(await screen.findByText('Scoped Uploader')).toBeInTheDocument()
  })
})
