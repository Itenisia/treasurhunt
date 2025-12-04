from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("armies", "0011_upgrade_attack_bonus_pct"),
    ]

    operations = [
        migrations.AddField(
            model_name="army",
            name="elo",
            field=models.IntegerField(default=666),
        ),
    ]
