from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("armies", "0008_pop_cap_and_unit_pop_cost"),
    ]

    operations = [
        migrations.AddField(
            model_name="commander",
            name="faction",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="commanders",
                to="armies.faction",
            ),
        ),
        migrations.AddField(
            model_name="commander",
            name="user",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="commander",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
