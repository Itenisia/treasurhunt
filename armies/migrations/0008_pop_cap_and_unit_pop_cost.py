from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("armies", "0007_war3_damage_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="commander",
            name="pop_cap",
            field=models.PositiveIntegerField(
                default=30, help_text="Limite de population pour l'admin"
            ),
        ),
        migrations.AddField(
            model_name="unittype",
            name="pop_cost",
            field=models.PositiveIntegerField(default=1, help_text="Coût en population pour cette unité"),
        ),
    ]
