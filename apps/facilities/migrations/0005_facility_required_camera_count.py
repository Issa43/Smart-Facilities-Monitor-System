from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("facilities", "0004_facility_operation_start_date")]
    operations = [migrations.AddField(model_name="facility", name="required_camera_count", field=models.PositiveIntegerField(blank=True, null=True))]
