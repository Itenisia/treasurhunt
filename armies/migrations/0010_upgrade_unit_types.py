from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("armies", "0009_commander_user_faction"),
    ]

    operations = [
        migrations.AddField(
            model_name="upgrade",
            name="unit_types",
            field=models.ManyToManyField(blank=True, related_name="upgrades", to="armies.unittype"),
        ),
    ]

