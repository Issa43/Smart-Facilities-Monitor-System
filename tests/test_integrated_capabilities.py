from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from PIL import Image
import pytest
from rest_framework import status

from apps.common.models import SystemSetting
from apps.facilities.models import Facility, FacilityAssignment
from apps.construction.models import SitePhoto
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.services import notify_users
from apps.users.models import User
from apps.projects.models import Project, ProjectAssignment
import io
from datetime import date, timedelta


@pytest.mark.django_db
def test_password_reset_is_enumeration_safe_and_token_changes_password(api_client, construction_manager_user):
    reset_url = reverse("auth-password-reset")
    existing = api_client.post(reset_url, {"email": construction_manager_user.email})
    missing = api_client.post(reset_url, {"email": "missing@sflms.test"})

    assert existing.status_code == missing.status_code == status.HTTP_202_ACCEPTED
    assert existing.json() == missing.json()
    assert len(mail.outbox) == 1

    uid = urlsafe_base64_encode(force_bytes(construction_manager_user.pk))
    token = default_token_generator.make_token(construction_manager_user)
    response = api_client.post(
        reverse("auth-password-reset-confirm"),
        {"uid": uid, "token": token, "new_password": "ChangedPass456!", "confirm_password": "ChangedPass456!"},
    )
    assert response.status_code == status.HTTP_200_OK
    construction_manager_user.refresh_from_db()
    assert construction_manager_user.check_password("ChangedPass456!")


@pytest.mark.django_db
def test_system_settings_are_persistent_versioned_and_admin_only(api_client, super_admin_user, construction_manager_user):
    setting = SystemSetting.objects.get(key="workflow.autoIncident")
    url = reverse("api_v1:system-setting-detail", kwargs={"key": setting.key})

    api_client.force_authenticate(super_admin_user)
    updated = api_client.patch(url, {"value": True, "version": setting.version})
    assert updated.status_code == status.HTTP_200_OK
    assert updated.data["value"] is True
    assert updated.data["version"] == setting.version + 1

    stale = api_client.patch(url, {"value": False, "version": setting.version})
    assert stale.status_code == status.HTTP_400_BAD_REQUEST

    api_client.force_authenticate(construction_manager_user)
    assert api_client.get(url).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_notifications_are_recipient_scoped_and_preferences_persist(api_client, construction_manager_user, super_admin_user):
    own = Notification.objects.create(
        recipient=construction_manager_user,
        title="Assigned work",
        body="A scoped notification",
        category=Notification.Category.PROJECT,
    )
    Notification.objects.create(
        recipient=super_admin_user,
        title="Admin only",
        body="Must not leak",
        category=Notification.Category.SYSTEM,
    )
    api_client.force_authenticate(construction_manager_user)

    listing = api_client.get(reverse("api_v1:notification-list"))
    assert listing.status_code == status.HTTP_200_OK
    assert [row["id"] for row in listing.data["results"]] == [str(own.pk)]

    read = api_client.post(reverse("api_v1:notification-read", kwargs={"pk": own.pk}))
    assert read.status_code == status.HTTP_200_OK
    assert read.data["read"] is True

    preferences = api_client.patch(
        reverse("api_v1:notification-preferences"),
        {"low_stock": False},
    )
    assert preferences.status_code == status.HTTP_200_OK
    assert preferences.data["low_stock"] is False


@pytest.mark.django_db
def test_notification_global_and_user_preferences_are_enforced(
    construction_manager_user, django_capture_on_commit_callbacks
):
    setting = SystemSetting.objects.get(key="notify.lowStock")
    setting.value = False
    setting.save(update_fields=["value", "updated_at"])
    with django_capture_on_commit_callbacks(execute=True):
        notify_users(
            [construction_manager_user], title="Low stock", body="Disabled globally",
            category=Notification.Category.MATERIAL, preference_field="low_stock",
            system_setting_key="notify.lowStock",
        )
    assert Notification.objects.count() == 0

    setting.value = True
    setting.save(update_fields=["value", "updated_at"])
    preference = NotificationPreference.objects.create(
        user=construction_manager_user,
        low_stock=False,
        created_by=construction_manager_user,
    )
    with django_capture_on_commit_callbacks(execute=True):
        notify_users(
            [construction_manager_user], title="Low stock", body="Disabled by user",
            category=Notification.Category.MATERIAL, preference_field="low_stock",
            system_setting_key="notify.lowStock",
        )
    assert Notification.objects.count() == 0

    preference.low_stock = True
    preference.save(update_fields=["low_stock", "updated_at"])
    with django_capture_on_commit_callbacks(execute=True):
        notify_users(
            [construction_manager_user], title="Low stock", body="Delivered",
            category=Notification.Category.MATERIAL, preference_field="low_stock",
            system_setting_key="notify.lowStock",
        )
    assert Notification.objects.filter(recipient=construction_manager_user).count() == 1


@pytest.mark.django_db
def test_operations_analytics_and_facilities_are_assignment_scoped(
    api_client, role_operations_manager, super_admin_user
):
    manager = User.objects.create_user(
        email="operations@sflms.test",
        username="operations",
        full_name="Operations Manager",
        password="StrongPass123!",
        role=role_operations_manager,
    )
    assigned = Facility.objects.create(
        name="Assigned Facility",
        type=Facility.Type.COMMERCIAL,
        location="Riyadh",
        created_by=super_admin_user,
    )
    Facility.objects.create(
        name="Hidden Facility",
        type=Facility.Type.INDUSTRIAL,
        location="Jeddah",
        created_by=super_admin_user,
    )
    FacilityAssignment.objects.create(
        facility=assigned,
        user=manager,
        role_type=FacilityAssignment.RoleType.OPERATIONS_MANAGER,
        created_by=super_admin_user,
    )
    api_client.force_authenticate(manager)

    facilities = api_client.get(reverse("api_v1:operations-facility-list"))
    assert facilities.status_code == status.HTTP_200_OK
    assert [row["name"] for row in facilities.data["results"]] == ["Assigned Facility"]

    analytics = api_client.get(reverse("api_v1:analytics-operations"))
    assert analytics.status_code == status.HTTP_200_OK
    assert analytics.data["facilities"] == 1
    assert analytics.data["average_uptime"] is None


@pytest.mark.django_db
def test_site_photo_upload_and_download_are_project_scoped(
    api_client, construction_manager_user, super_admin_user, role_security_officer
):
    project = Project.objects.create(
        name="Protected Site",
        facility_type=Project.FacilityType.COMMERCIAL,
        location="Riyadh",
        start_date=date.today(),
        expected_completion_date=date.today() + timedelta(days=90),
        created_by=super_admin_user,
    )
    ProjectAssignment.objects.create(
        project=project,
        user=construction_manager_user,
        role_type=ProjectAssignment.RoleType.PRIMARY_MANAGER,
        created_by=super_admin_user,
    )
    officer = User.objects.create_user(
        email="unassigned-security@sflms.test",
        username="unassigned-security",
        full_name="Unassigned Security",
        password="StrongPass123!",
        role=role_security_officer,
    )
    api_client.force_authenticate(construction_manager_user)
    image_bytes = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(image_bytes, format="PNG")
    response = api_client.post(
        reverse("api_v1:construction-site-photo-list"),
        {
            "project": str(project.pk),
            "caption": "Verified installation progress",
            "image": SimpleUploadedFile(
                "site.png",
                image_bytes.getvalue(),
                content_type="image/png",
            ),
        },
        format="multipart",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    photo = SitePhoto.objects.get(pk=response.data["id"])

    download = api_client.get(
        reverse("api_v1:construction-site-photo-download", kwargs={"pk": photo.pk})
    )
    assert download.status_code == status.HTTP_200_OK
    assert b"".join(download.streaming_content).startswith(b"\x89PNG")
    download.close()

    api_client.force_authenticate(officer)
    assert api_client.get(
        reverse("api_v1:construction-site-photo-download", kwargs={"pk": photo.pk})
    ).status_code == status.HTTP_403_FORBIDDEN
    photo.image.delete(save=False)
