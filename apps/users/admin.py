from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Permission, Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "created_at")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission_name")
    list_filter = ("role",)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User
    ordering = ("-created_at",)
    list_display = ("email", "username", "full_name", "role", "status", "is_staff")
    list_filter = ("role", "status", "is_staff")
    search_fields = ("email", "username", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Personal info", {"fields": ("full_name", "phone", "profile_image")}),
        ("Access", {"fields": ("role", "status", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "full_name", "role", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at", "last_login")
