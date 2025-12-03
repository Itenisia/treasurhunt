from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("armies", "0010_upgrade_unit_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="upgrade",
            name="attack_bonus_pct",
            field=models.FloatField(default=0.0, help_text="Bonus d'attaque en pourcentage (0.1 = +10%)"),
        ),
    ]

