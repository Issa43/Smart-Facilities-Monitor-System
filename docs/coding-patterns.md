# Coding Patterns

## Purpose
The canonical, copy-from implementation shape for every recurring concern
in this codebase — service layer, ViewSets, serializers, permissions,
Celery tasks, exceptions, responses, logging, file uploads, business
logic placement. Where `coding-standards.md` states the rule,
this document shows the code shape that satisfies it.

## Scope
Concrete code patterns with illustrative snippets. Not a style guide
(that's `coding-standards.md`) and not a description of what exists today
in each app (that's `backend-architecture.md`).

## Architecture

### Pattern: Service Layer
Business logic that touches more than one model, or needs to be callable
from both a view and a Celery task, lives in `services.py` as a plain
function — not a class, not a method on a serializer.

```python
# apps/projects/services.py
from django.db import transaction
from apps.facilities.models import Facility
from .models import Project

@transaction.atomic
def convert_project_to_facility(project: Project, performed_by) -> Facility:
    if project.status != Project.STATUS_COMPLETED:
        raise ValueError("Only a Completed project can be converted.")

    facility = Facility.objects.create(
        name=project.name,
        created_from_project=project,
        status=Facility.STATUS_OPERATIONAL,
        created_by=performed_by,
    )
    project.facility = facility
    project.status = Project.STATUS_OPERATIONAL
    project.save(update_fields=["facility", "status", "updated_at"])
    return facility
```
Called identically from a view action and, if ever needed, from a Celery
task or a management command — no duplicated logic.

### Pattern: ViewSets
```python
# apps/projects/views.py
class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [ProjectAccessPermission]   # app-level, see below
    filterset_fields = ["status", "facility"]
    search_fields = ["name", "location"]

    def get_queryset(self):
        user = self.request.user
        qs = Project.objects.select_related("facility")
        if user.role.name == Role.SUPER_ADMIN:
            return qs
        return qs.filter(assignments__user=user)   # object-level filter

    @action(detail=True, methods=["post"])
    def convert_to_facility(self, request, pk=None):
        project = self.get_object()
        facility = services.convert_project_to_facility(project, request.user)
        return Response(FacilitySerializer(facility).data, status=201)
```
Note: `convert_to_facility` calls the service, does not implement the
transition itself — see Service Layer pattern above.

### Pattern: Serializers (one per purpose, not per model)
```python
class ProjectSerializer(serializers.ModelSerializer):        # read
    ...
class ProjectCreateSerializer(serializers.ModelSerializer):  # write
    def validate(self, attrs):
        # cross-field / cross-model validation goes here, calling
        # services.py helpers if it needs to touch other models
        return attrs
```

### Pattern: Permissions (two-layer, see `permissions-rbac.md`)
```python
# apps/projects/permissions.py
class ProjectAccessPermission(BasePermission):
    def has_permission(self, request, view):        # Layer 1: role
        user = request.user
        return bool(user.is_authenticated and user.role_id and
                     user.role.name in (Role.SUPER_ADMIN, Role.CONSTRUCTION_MANAGER))

    def has_object_permission(self, request, view, obj):  # Layer 2 backstop
        user = request.user
        if user.role.name == Role.SUPER_ADMIN:
            return True
        return obj.assignments.filter(user=user).exists()
```
`get_queryset()` (above) is the *primary* Layer 2 mechanism;
`has_object_permission` is a backstop against direct `{id}/` access to an
ID the user guessed but was never assigned.

### Pattern: Celery Tasks
```python
# apps/ai_engine/tasks.py
from celery import shared_task
from . import services

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_frame(self, camera_id, frame_ref):
    try:
        services.run_detection(camera_id, frame_ref)
    except TransientError as exc:
        raise self.retry(exc=exc)
```
Tasks orchestrate; `services.py` does the work — identical layering rule
as views. See `celery-tasks.md` for the full registry and retry
conventions per task.

### Pattern: Exception Handling
```python
# apps/common/exceptions.py already provides the global envelope.
# App-specific exceptions:
class MaterialInsufficientStockError(Exception):
    """Raised by services.py; caught in views.py, never propagated raw."""
```
```python
# in views.py
try:
    services.fulfill_material_request(request_obj)
except MaterialInsufficientStockError as exc:
    return Response({"detail": str(exc)}, status=400)
```

### Pattern: Responses
Always return DRF `Response` with an explicit status code — never rely on
the default 200. List endpoints always go through
`StandardResultsPagination` (automatic via `DEFAULT_PAGINATION_CLASS`);
never manually paginate in a view.

### Pattern: Logging
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Project %s converted to Facility %s by user %s",
            project.id, facility.id, performed_by.id)
```
Structured, parameterized logging (not f-strings) so log aggregation can
filter/query fields later.

### Pattern: File Uploads
```python
class ProjectDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDocument
        fields = ["id", "project", "file_name", "file_type", "file_path", "uploaded_by"]
        read_only_fields = ["id", "uploaded_by"]

    def create(self, validated_data):
        validated_data["uploaded_by"] = self.context["request"].user
        return super().create(validated_data)
```
Uploads always go through a `FileField`/`ImageField` on a model — never a
raw file-handling view that writes to `MEDIA_ROOT` manually (breaks the
storage abstraction — see `backend-architecture.md`).

### Pattern: Business Logic Placement Decision Tree
```
Does it touch only this model's own fields, with no cross-model query?
  → Yes: model method or serializer validate_<field>()
  → No, but it's request-context-only (needs request.user, one-shot)?
      → services.py function, called from the view
  → No, and it must also run from Celery/a management command?
      → services.py function (same as above — this is the common case)
```

## Business Rules
N/A — this is an implementation-pattern document.

## Technical Notes
Every pattern above is illustrative, not copy-paste-exact for a specific
app — adapt names, keep the shape.

## Current Implementation
`apps/users`/`apps/authentication` demonstrate the ViewSet, Serializer,
Permission, Exception, and Response patterns today (no `services.py` yet
— Phase 1 had no cross-model logic requiring one). Service Layer,
Celery Task, and File Upload patterns above are illustrative of Phase
3+ target code, not yet implemented.

## Future Evolution
As each pattern is first used for real, replace or supplement its
illustrative snippet above with a reference to the actual file/line, so
this document stays grounded in real code rather than only hypotheticals.

## Important Decisions
Service Layer is mandatory for cross-model logic (see
`backend-architecture.md`) — this is the single most important pattern
in this document; violating it is the most common way this codebase would
degrade over a multi-year lifetime.

## Developer Notes
If you're about to write a `try/except` around a raw SQL-adjacent
operation inside a view, stop — that logic belongs in `services.py`.

## Related Components
`coding-standards.md`, `backend-architecture.md`, `celery-tasks.md`,
`permissions-rbac.md`.

## Files Involved
Illustrative only — no single file owns this document's content.

## Dependencies
`coding-standards.md`, `backend-architecture.md`.

## Things That MUST NEVER Be Changed Without Updating Documentation
The Service Layer placement rule (the decision tree above).

## Future Improvements
Once 3+ services.py files exist, extract genuinely common logic (e.g.,
"Super Admin bypass else filter by Assignment") into a shared
`apps.common` helper, referenced here as an updated pattern.
