from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("facilities", "0003_facilityassignment_and_more")]
    operations = [migrations.AddField(model_name="facility", name="operation_start_date", field=models.DateField(blank=True, null=True))]
