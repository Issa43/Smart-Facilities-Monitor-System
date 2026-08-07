from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from django.apps import apps as django_apps


class AttachmentEntityRegistryError(Exception):
    """Base error raised while resolving an attachment entity."""


class UnsupportedAttachmentEntityType(AttachmentEntityRegistryError):
    """Raised when a client supplies an entity type outside the frozen whitelist."""


class AttachmentEntityNotFound(AttachmentEntityRegistryError):
    """Raised when the target entity does not exist or is inactive."""


@dataclass(frozen=True)
class AttachmentEntityDefinition:
    key: str
    label: str
    model_label: str
    project_path: str


_ENTITY_DEFINITIONS = {
    "project_phase": AttachmentEntityDefinition(
        key="project_phase",
        label="Project phase",
        model_label="projects.ProjectPhase",
        project_path="project",
    ),
    "phase_progress_log": AttachmentEntityDefinition(
        key="phase_progress_log",
        label="Phase progress log",
        model_label="projects.PhaseProgressLog",
        project_path="phase__project",
    ),
    "daily_report": AttachmentEntityDefinition(
        key="daily_report",
        label="Daily report",
        model_label="construction.DailyReport",
        project_path="project",
    ),
    "material_request": AttachmentEntityDefinition(
        key="material_request",
        label="Material request",
        model_label="materials.MaterialRequest",
        project_path="project",
    ),
    "material_consumption_record": AttachmentEntityDefinition(
        key="material_consumption_record",
        label="Material consumption record",
        model_label="materials.MaterialConsumptionRecord",
        project_path="material__project",
    ),
}

ATTACHMENT_ENTITY_DEFINITIONS = MappingProxyType(_ENTITY_DEFINITIONS)
ATTACHMENT_ENTITY_TYPES = tuple(ATTACHMENT_ENTITY_DEFINITIONS)
ATTACHMENT_ENTITY_CHOICES = tuple(
    (definition.key, definition.label)
    for definition in ATTACHMENT_ENTITY_DEFINITIONS.values()
)


class AttachmentEntityRegistry:
    """Resolves approved generic attachment targets without ContentType/GFK."""

    definitions = ATTACHMENT_ENTITY_DEFINITIONS

    @classmethod
    def get_definition(cls, entity_type: str) -> AttachmentEntityDefinition:
        try:
            return cls.definitions[entity_type]
        except KeyError as exc:
            raise UnsupportedAttachmentEntityType(entity_type) from exc

    @classmethod
    def resolve(cls, entity_type: str, entity_id: Any):
        definition = cls.get_definition(entity_type)
        model = django_apps.get_model(definition.model_label)

        try:
            return model.objects.get(pk=entity_id)
        except (model.DoesNotExist, ValueError, TypeError) as exc:
            raise AttachmentEntityNotFound(
                f"Active {entity_type} target was not found."
            ) from exc

    @classmethod
    def resolve_project(cls, entity_type: str, entity: Any):
        definition = cls.get_definition(entity_type)
        project = entity
        for attribute in definition.project_path.split("__"):
            project = getattr(project, attribute)
        return project
