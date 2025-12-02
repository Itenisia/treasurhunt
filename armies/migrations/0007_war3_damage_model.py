from django.db import migrations, models


def split_army_units_forward(apps, schema_editor):
    ArmyUnit = apps.get_model("armies", "ArmyUnit")
    units_to_create = []
    for unit in ArmyUnit.objects.all():
        qty = getattr(unit, "quantity", 1) or 1
        if qty <= 1:
            continue
        # Keep one on the original row, spawn the rest as new rows (positions reset)
        for _ in range(qty - 1):
            units_to_create.append(
                ArmyUnit(
                    army_id=unit.army_id,
                    unit_type_id=unit.unit_type_id,
                    position_x=None,
                    position_y=None,
                )
            )
        unit.quantity = 1
        unit.save(update_fields=["quantity"])
    if units_to_create:
        ArmyUnit.objects.bulk_create(units_to_create)


class Migration(migrations.Migration):

    dependencies = [
        ("armies", "0006_remove_unittype_attack"),
    ]

    operations = [
        migrations.AddField(
            model_name="unittype",
            name="armor_type",
            field=models.CharField(
                choices=[
                    ("unarmored", "Unarmored"),
                    ("light", "Light"),
                    ("medium", "Medium"),
                    ("heavy", "Heavy"),
                    ("fortified", "Fortified"),
                    ("hero", "Hero"),
                    ("divine", "Divine"),
                ],
                default="unarmored",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="unittype",
            name="attack_type",
            field=models.CharField(
                choices=[
                    ("normal", "Normal"),
                    ("piercing", "Piercing"),
                    ("siege", "Siege"),
                    ("magic", "Magic"),
                    ("hero", "Hero"),
                    ("chaos", "Chaos"),
                    ("spells", "Spells"),
                ],
                default="normal",
                max_length=20,
            ),
        ),
        migrations.AlterUniqueTogether(
            name="armyunit",
            unique_together=set(),
        ),
        migrations.RunPython(split_army_units_forward, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="armyunit",
            name="quantity",
        ),
    ]
