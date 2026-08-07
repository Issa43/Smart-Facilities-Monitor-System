from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Custom manager for the SFLMS User model (email is the login field)."""

    use_in_migrations = True

    def _create_user(self, email, username, full_name, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        if not username:
            raise ValueError("Users must have a username.")
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, full_name=full_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, username, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, username, full_name, password, **extra_fields)

    def create_superuser(self, email, username, full_name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", "active")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        role_model = self.model._meta.get_field("role").remote_field.model
        try:
            super_admin_role = role_model._default_manager.db_manager(self._db).get(
                name=role_model.SUPER_ADMIN
            )
        except role_model.DoesNotExist as exc:
            raise ValueError(
                "The Super Admin role must exist before creating a superuser. Run migrations first."
            ) from exc

        supplied_role = extra_fields.get("role")
        if supplied_role is not None and supplied_role.pk != super_admin_role.pk:
            raise ValueError("Superuser role must be the Super Admin role.")
        extra_fields["role"] = super_admin_role

        return self._create_user(email, username, full_name, password, **extra_fields)
