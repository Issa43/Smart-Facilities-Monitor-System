import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class Role(models.Model):
    """
    The four fixed roles of SFLMS (architecture §0/§3.1/§6).

    Kept as a lightweight reference table (not just a code Enum) so it can
    be a real FK target and be listed/managed via `/api/users/roles/`,
    while the *set* of roles itself is intentionally fixed at four values
    to match the approved permission matrix.
    """

    SUPER_ADMIN = "super_admin"
    CONSTRUCTION_MANAGER = "construction_manager"
    OPERATIONS_MANAGER = "operations_manager"
    SECURITY_OFFICER = "security_officer"

    ROLE_CHOICES = [
        (SUPER_ADMIN, "Super Admin"),
        (CONSTRUCTION_MANAGER, "Construction Manager"),
        (OPERATIONS_MANAGER, "Operations Manager"),
        (SECURITY_OFFICER, "Security Officer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, choices=ROLE_CHOICES, unique=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.get_name_display()


class Permission(models.Model):
    """
    Fine-grained permission strings attached to a Role, e.g. "project.create",
    "incident.close". Consumed by the RBAC layer (apps.common.permissions)
    and by domain-specific permission classes in later phases.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    permission_name = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "permission_name"], name="unique_role_permission")
        ]
        ordering = ["role", "permission_name"]

    def __str__(self):
        return f"{self.role.name}:{self.permission_name}"


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model. `email` is the login field (USERNAME_FIELD);
    `username` is kept as a separate required, unique display/handle field
    per the approved schema.
    """

    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_SUSPENDED = "suspended"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
        (STATUS_SUSPENDED, "Suspended"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True, default="")
    username = models.CharField(max_length=50, unique=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users", null=True, blank=True)
    profile_image = models.ImageField(upload_to="users/profile_images/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # `last_login` is provided by AbstractBaseUser.

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "full_name"]

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["username"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    def delete(self, using=None, keep_parents=False):
        """Preserve operational history by deactivating accounts."""
        if self.status != self.STATUS_INACTIVE:
            self.status = self.STATUS_INACTIVE
            self.save(update_fields=["status", "updated_at"])

    @property
    def is_active(self):
        # Bridges our `status` field with Django's auth expectations
        # (login, admin site, etc.) without a separate boolean column.
        return self.status == self.STATUS_ACTIVE

    @is_active.setter
    def is_active(self, value):
        self.status = self.STATUS_ACTIVE if value else self.STATUS_INACTIVE
