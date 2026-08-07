import uuid

import django.contrib.auth.models
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

import apps.users.managers


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="Role",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "name",
                    models.CharField(
                        choices=[
                            ("super_admin", "Super Admin"),
                            ("construction_manager", "Construction Manager"),
                            ("operations_manager", "Operations Manager"),
                            ("security_officer", "Security Officer"),
                        ],
                        max_length=50,
                        unique=True,
                    ),
                ),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False)),
                ("full_name", models.CharField(max_length=150)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("phone", models.CharField(blank=True, default="", max_length=30)),
                ("username", models.CharField(max_length=50, unique=True)),
                (
                    "profile_image",
                    models.ImageField(blank=True, null=True, upload_to="users/profile_images/"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("inactive", "Inactive"), ("suspended", "Suspended")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("is_staff", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="users",
                        to="users.role",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
            managers=[
                ("objects", apps.users.managers.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="Permission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("permission_name", models.CharField(max_length=100)),
                (
                    "role",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permissions",
                        to="users.role",
                    ),
                ),
            ],
            options={"ordering": ["role", "permission_name"]},
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["email"], name="users_user_email_idx"),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["username"], name="users_user_username_idx"),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["role"], name="users_user_role_idx"),
        ),
        migrations.AddConstraint(
            model_name="permission",
            constraint=models.UniqueConstraint(
                fields=("role", "permission_name"), name="unique_role_permission"
            ),
        ),
    ]
