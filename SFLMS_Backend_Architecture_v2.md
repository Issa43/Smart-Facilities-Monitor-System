# Smart Facility Lifecycle Management System (SFLMS)
## Complete Backend Architecture — v2.0 (Final, Pre-Coding Review)

---

## 0. Resolution Log — كيف اتطبقت الـ 10 قرارات

| # | القرار | التطبيق |
|---|---|---|
| 1 | Facility/Project Lifecycle | `Project.facility` (nullable FK) + `Facility.created_from_project` (nullable OneToOne) — تفاصيل في §3.1 |
| 2 | Assignment Tables | `ProjectAssignment`, `FacilityAssignment` بدل FK مباشر، بحقل `role_type` يسمح بأكتر من مستخدم |
| 3 | RBAC + Object-Level | كل `views.py` هيستخدم `get_queryset()` مفلترة عبر Assignment tables — تفاصيل §6 |
| 4 | Maintenance Order + Execution | `MaintenanceOrder` (workflow) + `WorkExecutionLog` (تنفيذ متعدد) بدل سجل واحد |
| 5 | AI خارجي | خدمة AI خارج Django تقرأ الإعدادات وترسل الأحداث النهائية فقط عبر REST؛ التفاصيل الحالية في §7 |
| 6 | Real-Time | Django Channels + WebSockets + Redis للأحداث الأمنية المحفوظة، بمسار مستقل عن Notification/FCM |
| 7 | Storage | MEDIA_ROOT + abstraction layer قابلة للتبديل لـ Cloud لاحقًا |
| 8 | Database | PostgreSQL + Django ORM |
| 9 | Apps Structure | حسب القائمة المطلوبة بالضبط + إضافة واحدة موضحة في §2 |
| 10 | لا كود قبل الاعتماد | هذا المستند بالكامل تحليل معماري فقط |

---

## 1. Facility/Project Lifecycle — التفصيل الكامل

```
[Project created]  (status: Planning)
        │
        │  Phases execute, DailyReports, Materials consumed...
        ▼
[Project status → Completed]
        │
        │  Manual action by Super Admin/Construction Manager:
        │  "Convert to Facility"  (service function, not automatic signal)
        ▼
[Facility created]
    facility.created_from_project = Project (OneToOne, traceability)
    project.facility = Facility (back-reference set)
        │
        ▼
[Facility enters Operations & Maintenance lifecycle]
        │
        │  Later: need expansion/renovation?
        ▼
[New Project created WITH facility = existing Facility from day 1]
   (this Project's `facility` FK is set at creation, not via conversion)
```

**قاعدة العمل (Business Rule) في `services.py` الخاص بـ projects app:**
- Project عادي (بناء جديد): `facility = null` عند الإنشاء، ويتم ربطه بـ Facility جديدة فقط عبر `convert_project_to_facility()` service function بعد `status = Completed`.
- Project توسعة (Expansion): `facility` يتحدد يدويًا عند الإنشاء لأنه أصلاً مرتبط بمنشأة موجودة، ولا يمر بعملية Conversion.
- `Facility.created_from_project` بيفضل يشاور بس على الـ "genesis project" — مش كل مشاريع التوسعة.

**النتيجة:** Facility كيان مستقل تمامًا بعد إنشائه، وممكن يعيش بدون أي Project مرتبط بيه مباشرة في لحظة معينة (لو الـ genesis project اتمسح/اتأرشف)، وده بيحقق "Facility لا تعتمد على Project للأبد" بالظبط زي ما طلبت.

---

## 2. Django Apps Structure

طابقت القائمة المطلوبة بالحرف، مع **إضافة واحدة فقط** ضرورية لازم أوضحها:

> **إضافة:** app اسمه `attachments` — مش موجود في قائمتك، لكن Section 11 (File Management) في طلبك عرّف موديل `Attachment` عام (`entity_type`, `entity_id`) لازم يتخزن في مكان مركزي مستقل، مش منطقي يتكرر جوه كل app. لو تفضل يبقى جزء من `common/` بدل app مستقل قولّي، التسمية مش مهمة بس الوظيفة لازم تكون مركزية.

```
sflms/
├── config/                      # settings (base/dev/prod), celery.py, asgi.py (Channels)
├── apps/
│   ├── authentication/          # JWT login/refresh/logout, password reset
│   ├── users/                   # User, Role, Permission
│   ├── projects/                # Project, ProjectPhase, PhaseProgressLog,
│   │                             # ProjectDocument, ProjectAssignment
│   ├── construction/             # DailyReport, execution-level construction records
│   ├── materials/               # Material, MaterialRequest, MaterialConsumptionRecord
│   ├── facilities/              # Facility, FacilityAssignment
│   ├── assets/                  # Asset, AssetHistory
│   ├── maintenance/              # MaintenanceOrder, WorkExecutionLog, MaintenanceChecklist,
│   │                             # MaintenanceCalendarEvent, Fault, FaultTimeline
│   ├── security/                # Camera/Event/Alert/Incident + Channels live delivery
│   ├── ai_engine/               # placeholder only; inference remains external
│   ├── notifications/           # durable Notification/Celery; future FCM
│   ├── reports/                 # Report, PDF/Excel generation services (Celery)
│   ├── audit/                   # AuditLog, middleware/signal listeners
│   ├── attachments/              # Attachment (generic file registry) — see note above
│   └── common/                   # BaseModel, shared permissions base, pagination, exceptions
```

**كل app (فيما عدا `common`) يحتوي بالضبط على:**
`models.py` · `serializers.py` · `views.py` · `urls.py` · `permissions.py` · `filters.py` · `services.py`

`services.py` بيحمل الـ business logic اللي مش لازم يعيش جوه الـ View مباشرة (زي `convert_project_to_facility()`, `escalate_alert_to_incident()`, `generate_report_file()`) — ده بيخلي الـ Views رفيعة (thin) والمنطق قابل لإعادة الاستخدام في Celery tasks كمان.

---

## 3. Database Models — كامل بالتفصيل

### 3.1 users app

**Role**: `id`, `name` (unique, choices: `super_admin`/`construction_manager`/`operations_manager`/`security_officer`), `description`, `created_at`

**Permission**: `id`, `role` FK, `permission_name` (CharField, مثال: `project.create`, `incident.close`)
> Index: `unique_together(role, permission_name)`

**User**: `id`, `full_name`, `email` (unique, login field), `phone`, `username` (unique), `password` (Django's hasher, لا نخزن `password_hash` كحقل يدوي — بنستخدم `AbstractBaseUser` القياسي)، `role` FK, `profile_image`, `status` (choices: `active`/`inactive`/`suspended`), `last_login`, `created_at`, `updated_at`
> Indexes: `email`, `username`, `role_id`

---

### 3.2 projects app

**Project**: `id`, `name`, `facility` FK(nullable, → facilities.Facility)، `facility_type`, `description`, `location`, `latitude`, `longitude`, `image`, `start_date`, `expected_end_date`, `actual_end_date`, `status` (`Planning`/`In Progress`/`Completed`/`Operational`), `created_by` FK(User), `created_at`, `updated_at`
> ملاحظة: حذفنا `construction_manager_id` المباشر (قرار #2) — الإسناد بيتم عبر `ProjectAssignment`.
> Indexes: `status`, `facility_id`

**ProjectAssignment**: `id`, `project` FK, `user` FK, `role_type` (choices: `primary_manager`/`engineer`/`supervisor`/`viewer`), `assigned_at`
> Constraint: `unique_together(project, user, role_type)`
> Index: composite `(user_id, project_id)` — أهم query لفلترة الـ queryset

**ProjectPhase**: `id`, `project` FK, `name`, `description`, `sequence_number`, `start_date`, `expected_end_date`, `initial_progress`, `current_progress`, `priority` (`low`/`medium`/`high`), `status` (`Not Started`/`In Progress`/`Completed`/`Rejected`/`Needs Modification`), `approved_by` FK(User, null), `approved_at`
> Constraint: `unique_together(project, sequence_number)`

**PhaseProgressLog**: `id`, `phase` FK, `progress_percentage`, `work_completed` (TextField), `notes`, `updated_by` FK(User), `updated_at`
> (المرفقات بتاعت هذا الـ log بتتسجل في `attachments.Attachment` عبر `entity_type='phase_progress_log'`)

**ProjectDocument**: `id`, `project` FK, `file_name`, `file_type`, `file_path` (FileField)، `uploaded_by` FK(User), `uploaded_at`

---

### 3.3 construction app

**DailyReport**: `id`, `project` FK, `phase` FK(nullable), `report_date`, `weather_condition`, `workers_count`, `equipment_used` (TextField/JSON — قائمة معدات)، `report_content`, `issues`, `created_by` FK(User), `created_at`
> Constraint: `unique_together(project, report_date, created_by)`
> Index: `(project_id, report_date)`

---

### 3.4 materials app

**Material**: `id`, `project` FK, `name`, `category`, `unit`, `quantity_required`, `quantity_used`, `quantity_remaining`, `min_stock_threshold`, `supplier`, `created_at`
> Index: composite `(project_id, quantity_remaining)` — لدعم AI low-stock prediction queries

**MaterialRequest**: `id`, `project` FK, `material` FK, `quantity_requested`, `reason`, `priority` (`low`/`medium`/`high`/`urgent`), `status` (`Submitted`/`Reviewed`/`Approved`/`Rejected`/`Completed`), `requested_by` FK(User), `reviewed_by` FK(User, null), `approved_by` FK(User, null), `created_at`

**MaterialConsumptionRecord**: `id`, `material` FK, `quantity_used`, `usage_date`, `phase` FK(nullable), `created_by` FK(User)
> هذا الجدول هو الـ historical feed لـ AI Material Prediction module.

---

### 3.5 facilities app

**Facility**: `id`, `created_from_project` OneToOne(nullable → projects.Project), `name`, `type`, `location`, `status` (`operational`/`under_maintenance`/`decommissioned`), `created_at`
> ملاحظة: حذفنا `manager_id` المباشر (قرار #2) — الإسناد عبر `FacilityAssignment`.

**FacilityAssignment**: `id`, `facility` FK, `user` FK, `role_type` (choices: `operations_manager`/`security_officer`/`viewer`), `assigned_at`
> Constraint: `unique_together(facility, user, role_type)`
> Index: composite `(user_id, facility_id)`

---

### 3.6 assets app

**Asset**: `id`, `facility` FK, `name`, `asset_type`, `category`, `serial_number` (unique), `manufacturer`, `model`, `location_inside_facility`, `installation_date`, `operation_date`, `current_status` (`Operational`/`Under Maintenance`/`Out Of Service`), `health_score` (DecimalField 0-100، مُحسّن عبر AI/rules)، `remaining_useful_life` (IntegerField, بالأيام)، `last_maintenance_date`, `notes`
> Indexes: `facility_id`, `current_status`, `serial_number`

**AssetHistory**: `id`, `asset` FK, `event_type` (`installed`/`serviced`/`relocated`/`status_changed`/`decommissioned`), `description`, `performed_by` FK(User), `date`

---

### 3.7 maintenance app

**MaintenanceOrder** (الـ Workflow/Request):
`id`, `asset` FK, `type` (`Preventive`/`Corrective`/`Emergency`), `priority`, `description`, `reason`, `assigned_to` FK(User) *(المسؤول الأساسي حاليًا، لكن التنفيذ الفعلي بيتسجل في WorkExecutionLog)*, `created_by` FK(User), `expected_execution_date`, `actual_completion_date`, `status` (`Open`/`Assigned`/`In Progress`/`Completed`/`Closed`)
> Index: `(asset_id, status)`

**WorkExecutionLog** (تنفيذ فعلي — قرار #4، يسمح بأكتر من محاولة/فني):
`id`, `maintenance_order` FK `related_name="execution_logs"`, `technician` FK(User), `action_taken` (TextField), `progress_percentage`, `started_at`, `ended_at`, `notes`, `logged_at`

**MaintenanceChecklist**: `id`, `maintenance_order` FK, `task`, `completed` (Boolean), `completed_by` FK(User, null), `completed_at`

**MaintenanceCalendarEvent**: `id`, `asset` FK, `maintenance_order` FK(nullable), `scheduled_date`, `type` (`preventive_due`/`inspection`/`follow_up`)
> Index: `scheduled_date` (لجدولة Celery beat)

**Fault**: `id`, `asset` FK, `fault_type`, `description`, `severity` (`minor`/`moderate`/`major`/`critical`), `discovery_time`, `reported_by` FK(User), `assigned_engineer` FK(User, null), `root_cause` (TextField, null), `resolution` (TextField, null), `status` (`Reported`/`Investigating`/`Resolved`/`Closed`)

**FaultTimeline**: `id`, `fault` FK `related_name="timeline"`, `action`, `performed_by` FK(User), `timestamp`

---

### 3.8 security app

**Camera**: `id`, `facility` FK, `name`, `location`, `camera_type`, `ip_address`, `stream_url` (RTSP)، `status` (`online`/`offline`/`error`), `last_connection`

**SecurityAlert**: `id`, `facility` FK, `camera` FK(nullable), `alert_type` (`Fire`/`Smoke`/`Intrusion`/`Motion`/`Vehicle`), `location`, `severity_level`, `source` (`ai_detection`/`manual`/`sensor`), `confidence_score` (nullable, من AI)، `snapshot_image`, `status` (`New`/`Reviewed`/`Converted`/`Dismissed`), `created_at`
> Index: `(facility_id, status)`, `created_at` DESC

**Incident**: `id`, `incident_number` (unique, auto-generated)، `facility` FK, `alert` FK(nullable → SecurityAlert), `incident_type`, `description`, `location`, `severity_level`, `assigned_to` FK(User, null), `status` (`Open`/`Investigation`/`Transferred`/`Closed`), `final_report` (TextField, null), `created_by` FK(User), `closed_by` FK(User, null), `created_at`, `closed_at`
> Index: `(facility_id, status)`, `incident_number`

**IncidentAction**: `id`, `incident` FK `related_name="actions"`, `action_taken`, `notes`, `taken_by` FK(User), `taken_at`

---

### 3.9 ai_engine app

**AIModel**: `id`, `name`, `type` (`fire_detection`/`intrusion`/`vehicle_recognition`...)، `version`, `status` (`active`/`inactive`/`testing`)

**CameraDetectionEvent**: `id`, `camera` FK, `model` FK(→ AIModel), `event_type` (`Fire`/`Smoke`/`Intrusion`/`Vehicle`), `confidence_score`, `detected_objects` (JSONField — bounding boxes + labels)، `image_snapshot`, `video_reference` (FileField, null), `created_at`, `converted_to_alert` FK(nullable → security.SecurityAlert)
> Index: `(camera_id, event_type)`, `created_at`

**VehicleRecognition**: `id`, `camera` FK, `plate_number`, `vehicle_type`, `entry_time`, `exit_time` (nullable)، `confidence`

---

### 3.10 notifications app

**Notification**: `id`, `recipient` FK، `title`, `body`, `category` (`project`/`material`/`maintenance`/`security`/`system`)، `tone` (`neutral`/`info`/`success`/`warning`/`critical`)، `href` (nullable)، `source_type` (nullable)، `source_id` (nullable)، `deduplication_key` (nullable/unique)، `read_at` (nullable)، وحقول `BaseModel`
> كل سجل يخص مستلمًا واحدًا؛ `is_read` خاصية مشتقة من `read_at`. Indexes: `(recipient_id, read_at, created_at)` و`(source_type, source_id)`

---

### 3.11 reports app

**Report**: `id`, `type`, `module` (`construction`/`materials`/`assets`/`maintenance`/`security`)، `created_by` FK(User), `parameters` (JSONField — الفلاتر المستخدمة)، `file_path` (FileField, null إلى أن ينتهي Celery task)، `format` (`PDF`/`Excel`), `status` (`queued`/`processing`/`completed`/`failed` — إضافة ضرورية لتتبع التوليد الغير-متزامن)، `created_at`

---

### 3.12 audit app

**AuditLog**: `id`, `user` FK(nullable), `action` (`create`/`update`/`delete`/`login`/`export`...)، `module`, `table_name`, `record_id`, `old_values` (JSONField)، `new_values` (JSONField)، `ip_address`, `timestamp`
> Append-only، لا update/delete مسموح حتى للـ Super Admin.
> Indexes: `user_id`, `timestamp`, `(table_name, record_id)`

---

### 3.13 attachments app *(الإضافة الموضحة في §2)*

**Attachment**: `id`, `entity_type` (CharField — اسم الموديل كنص، أبسط من ContentType framework لو حابب نتجنب الـ dependency، أو GenericForeignKey لو تفضل type-safety كامل — قرار مفتوح، انظر §11)، `entity_id` (UUID)، `file_name`, `file_path` (FileField)، `file_type` (`image`/`pdf`/`video`/`document`)، `uploaded_by` FK(User), `uploaded_at`
> Index: composite `(entity_type, entity_id)`

---

## 4. Entity Relationship Map (كامل)

```
User ──< ProjectAssignment >── Project
User ──< FacilityAssignment >── Facility

Project (0..1) ──> Facility            [Project.facility, nullable]
Facility (0..1) ──> Project            [Facility.created_from_project, "genesis" only]

Project (1) ──< ProjectPhase (M) ──< PhaseProgressLog (M)
Project (1) ──< DailyReport (M) ──> ProjectPhase (0..1)
Project (1) ──< ProjectDocument (M)
Project (1) ──< Material (M) ──< MaterialRequest (M)
Material (1) ──< MaterialConsumptionRecord (M) ──> ProjectPhase (0..1)

Facility (1) ──< Asset (M) ──< AssetHistory (M)
Asset (1) ──< MaintenanceOrder (M) ──< WorkExecutionLog (M)
MaintenanceOrder (1) ──< MaintenanceChecklist (M)
Asset (1) ──< MaintenanceCalendarEvent (M) ──> MaintenanceOrder (0..1)
Asset (1) ──< Fault (M) ──< FaultTimeline (M)

Facility (1) ──< Camera (M)
Camera (1) ──< CameraDetectionEvent (M) ──> AIModel
Camera (1) ──< VehicleRecognition (M)
CameraDetectionEvent (0..1) ──> SecurityAlert (1)   [converted_to_alert]
Facility (1) ──< SecurityAlert (M)
SecurityAlert (0..1) ──> Incident (1)               [alert FK]
Incident (1) ──< IncidentAction (M)

User (1) ──< Notification (M)
* (any entity) ──< Attachment (M)  [entity_type + entity_id]
User (1) ──< AuditLog (M)
User (1) ──< Report (M)
```

---

## 5. API Endpoint Map

نمط موحّد لكل الـ Resources (ViewSet-based، DRF Router):
`GET /list/` · `POST /create/` · `GET /{id}/` · `PUT/PATCH /{id}/` · `DELETE /{id}/`
+ `pagination` (PageNumberPagination, page_size=20 افتراضي) + `filter_backends` (DjangoFilterBackend + SearchFilter + OrderingFilter) على كل الـ list endpoints.

| Module | Base Path | أهم Custom Actions (غير الـ CRUD القياسي) |
|---|---|---|
| Auth | `/api/auth/` | `login/`, `refresh/`, `logout/`, `password-reset/` |
| Users | `/api/users/` | `me/` (بيانات المستخدم الحالي) |
| Roles/Permissions | `/api/roles/`, `/api/permissions/` | — |
| Projects | `/api/projects/` | `{id}/convert-to-facility/` (POST), `{id}/assignments/` |
| Phases | `/api/projects/{project_id}/phases/` | `{id}/approve/`, `{id}/progress-logs/` |
| Daily Reports | `/api/construction/daily-reports/` | filter by `project`, `date_range` |
| Materials | `/api/materials/` | `{id}/consumption-history/`, `low-stock/` |
| Material Requests | `/api/materials/requests/` | `{id}/approve/`, `{id}/reject/` |
| Facilities | `/api/facilities/` | `{id}/assignments/` |
| Assets | `/api/assets/` | `{id}/history/`, `{id}/health-report/` |
| Maintenance Orders | `/api/maintenance/orders/` | `{id}/assign/`, `{id}/execution-logs/`, `{id}/checklist/` |
| Calendar | `/api/maintenance/calendar/` | filter by `date_range`, `asset` |
| Faults | `/api/faults/` | `{id}/timeline/`, `{id}/resolve/` |
| Cameras | `/api/security/cameras/` | `{id}/status/` |
| Security Alerts | `/api/security/alerts/` | `{id}/acknowledge/`, `{id}/convert-to-incident/`, `{id}/dismiss/` |
| Incidents | `/api/security/incidents/` | `{id}/actions/`, `{id}/close/` |
| AI Detection Events | `/api/ai/detection-events/` | read-only (Celery-generated), filter by `camera`, `event_type` |
| Vehicle Recognition | `/api/ai/vehicle-recognition/` | read-only |
| Notifications | `/api/notifications/` | `{id}/mark-read/`, `mark-all-read/`, `unread-count/` |
| Reports | `/api/reports/` | `generate/` (POST → queues Celery job), `{id}/download/` |
| Audit Logs | `/api/audit/` | read-only، Super Admin فقط |
| WebSocket | `/ws/security/events/` | بث أحداث أمنية محفوظة عبر Channels، مع JWT access token ضمن WebSocket subprotocol؛ لا يقبل AIKey ولا query-string token |

كل Endpoint هيتوثّق تلقائيًا عبر **drf-spectacular** (Swagger/OpenAPI) زي ما طلبت في المواصفة الأولى.

---

## 6. Permission Matrix

| Module | Super Admin | Construction Manager | Operations Manager | Security Officer |
|---|---|---|---|---|
| Projects | Full CRUD (كل المشاريع) | CRUD على المشاريع المُسندة فقط (عبر ProjectAssignment) | لا وصول | لا وصول |
| Phases/DailyReports/Materials | Full | فقط ضمن مشاريعه المُسندة | لا وصول | لا وصول |
| Facilities | Full CRUD | قراءة فقط (لمشاريعه اللي اتحولت) | CRUD محدود على المُسندة فقط | قراءة فقط للمُسندة |
| Assets/Maintenance/Faults | Full | لا وصول | Full على منشآته المُسندة (FacilityAssignment) | قراءة فقط (سياق أمني) |
| Cameras/Alerts/Incidents | Full | لا وصول | قراءة فقط | Full على منشآته المُسندة |
| AI Detection Events | Full (قراءة) | لا وصول | لا وصول (إلا لو مرتبطة بأصل) | قراءة كاملة |
| Reports | Full | توليد تقارير Construction فقط | توليد تقارير Operations فقط | توليد تقارير Security فقط |
| Notifications | كل الإشعارات (Admin view) | الخاصة به | الخاصة به | الخاصة به |
| Audit Logs | قراءة كاملة فقط | لا وصول | لا وصول | لا وصول |
| Users/Roles | Full CRUD | لا وصول | لا وصول | لا وصول |

**آلية التنفيذ:** كل `permissions.py` فيه custom `BasePermission` بيعمل:
1. `has_permission()` — فحص الـ Role العام (هل مسموحله يوصل للـ endpoint أصلاً).
2. الـ `get_queryset()` في الـ View بيستخدم فلترة عبر `ProjectAssignment`/`FacilityAssignment` — بمعنى إن Construction Manager أصلاً مش هيشوف في الـ `list` إلا المشاريع اللي هو Assigned عليها، مش هيحصل عليها Permission Denied لكل واحدة على حدة.
3. `has_object_permission()` — كطبقة حماية إضافية عند الوصول المباشر بـ `{id}/` لمنع تخمين الـ IDs.

---

## 7. AI Integration Architecture — Current Approved Boundary

```
External AI service
  → AIKey-authenticated REST configuration reads
  → external inference/tracking/OCR
  → idempotent final CameraEvent REST ingestion
  → optional SecurityAlert persisted in the same transaction
  → post-commit Channels delivery to authorized human dashboards

Independent durable/mobile path:
SecurityAlert → Notification → Celery → future FCM
```

Django does not capture frames or run YOLO, OCR, ByteTrack, OpenCV, temporal
filtering, line crossing, or tamper inference. It stores current configuration
and final persisted domain events only. WebSocket delivery never accepts
AIKey and never substitutes for REST persistence or initial state.

---

## 8. Development Phases (خطة التنفيذ المقترحة)

| Phase | المحتوى |
|---|---|
| **Phase 1 — Foundation** | `config/`, `common/`, PostgreSQL setup, Custom User model, JWT auth, Role/Permission base, Swagger setup |
| **Phase 2 — Core RBAC** | `users`, `attachments`, Assignment tables + permission classes + queryset filtering framework (يُبنى مرة واحدة ويُعاد استخدامه في كل app) |
| **Phase 3 — Construction Domain** | `projects`, `construction`, `materials` كاملة بـ APIs |
| **Phase 4 — Operations Domain** | `facilities`, `assets`, `maintenance` كاملة، + service الـ `convert_project_to_facility` |
| **Phase 5 — Security Domain (بدون AI)** | `security` app كامل (Camera, Alert, Incident) بإدخال يدوي أولاً لضمان الـ workflow سليم قبل ربط AI |
| **Phase 6 — External AI Contracts** | AIKey/camera scope، CameraEvent final ingestion، camera configuration APIs؛ inference خارج Django |
| **Phase 7 — Real-Time Layer** | `/ws/security/events/` + JWT subprotocol + post-commit Channels delivery مستقلة عن Notification |
| **Phase 8 — Reporting** | `reports` app + PDF/Excel generation عبر Celery |
| **Phase 9 — Audit & Hardening** | `audit` app، Audit middleware/signals، مراجعة أمنية شاملة لكل الـ Permission classes |
| **Phase 10 — Integration Testing** | ربط كامل مع الـ Frontend الموجود، اختبار كل الـ workflows end-to-end |

---

## 9. Addendum — Final Approved Additions (v2.1 — FINAL, no further redesign)

المستند بالكامل (§0–§8) **معتمد كما هو**. الإضافات التالية فقط اتضافت فوقه، من غير حذف أو تعديل لأي موديل/علاقة/صلاحية سابقة:

**9.1 `AssetHealthHistory`** (assets app) — تتبع تاريخي لصحة الأصل لدعم شارت Asset Health Center + AI trends:
`id`, `asset` FK `related_name="health_history"`, `health_score`, `risk_level` (`low`/`medium`/`high`/`critical`), `remaining_useful_life`, `prediction_source` (`manual`/`ai_model`/`rule_based`), `created_at`
> Index: `(asset_id, created_at)`

**9.2 `Notification`** (notifications app) — إضافة حقل:
`facility` FK(nullable → facilities.Facility) — لدعم Facility-level broadcast (إشعار لكل المُسندين على منشأة بدل مستخدم واحد). `user` يفضل nullable-compatible في هذه الحالة (broadcast = `user=null, facility=<x>`؛ إشعار شخصي = `user=<x>, facility=null` غالبًا).

**9.3 `CameraRecording`** (security app) — جديد:
`id`, `camera` FK `related_name="recordings"`, `video_file`, `start_time`, `end_time`, `event_related_id` (nullable UUID — يشاور على `CameraDetectionEvent` أو `SecurityAlert` بدون FK صارم لمرونة الربط بمصادر مختلفة)

**9.4 `SecurityAlert`** (security app) — إضافة حقول:
`is_false_positive` (Boolean, default=False), `reviewed_by` FK(nullable → User), `review_notes` (TextField, nullable)

**9.5 `MaterialPrediction`** (materials app أو ai_engine — اعتُمد داخل `materials` لقربه المنطقي من `MaterialConsumptionRecord`):
`id`, `material` FK `related_name="predictions"`, `predicted_date`, `predicted_quantity`, `confidence_score`, `created_at`

**9.6 `ReportTemplate`** (reports app) — جديد:
`id`, `name`, `module`, `format` (`PDF`/`Excel`), `configuration` (JSONField — تخطيط الأعمدة/الفلاتر الافتراضية للقالب)

**9.7 Authentication** — مؤكَّد: `djangorestframework-simplejwt` (Access + Refresh Tokens)، متوافق بالكامل مع DRF، ده اللي هيتنفذ في Phase 1.

**9.8 Attachment** — مؤكَّد نهائيًا: **بدون** GenericForeignKey. نفس البنية المعتمدة: `entity_type` (CharField) + `entity_id` (UUID)، بدون ContentType framework dependency.

**الحالة: المعمارية نهائية (FINAL). أي تنفيذ لاحق (Phase 2 فصاعدًا) هيتبني فوق هذا المستند بدون إعادة تصميم.**

---

## 10. Phase 1 — Implementation Status

تم تنفيذ Phase 1 بالكامل. راجع التسليم في الرسالة المرفقة بهذا المستند (كود + migrations + tests).
