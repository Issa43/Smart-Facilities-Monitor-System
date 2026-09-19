from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Custom manager for the SFLMS User model (email is the login field)."""

    use_in_migrations = True

    def get_by_natural_key(self, username):
        """Resolve the login identifier without regard to letter case.

        ``ModelBackend`` funnels every authentication attempt through here, and
        the default implementation matches ``email`` exactly. Email local parts
        are case-insensitive in practice, and every other place that resolves an
        account from an address -- both password-reset paths -- already uses
        ``iexact``. The mismatch was reachable: an account stored with any
        uppercase letter could complete a password reset requested in lower
        case and then be refused at login with the password it had just set,
        which is indistinguishable from a wrong password.

        This only decides *which* account an identifier names; the password is
        still verified afterwards by the backend, unchanged.
        """

        lookup = f"{self.model.USERNAME_FIELD}__iexact"
        try:
            return self.get(**{lookup: username})
        except self.model.MultipleObjectsReturned:
            # `email` is unique but case-sensitively so, so addresses differing
            # only in case can coexist. Never guess between them: honour an
            # exact match if there is one, otherwise refuse.
            try:
                return self.get(**{self.model.USERNAME_FIELD: username})
            except self.model.DoesNotExist:
                raise self.model.DoesNotExist(
                    "Multiple accounts share that email address."
                ) from None

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
