from django.db import migrations

def populate_units(apps, schema_editor):
    UnitType = apps.get_model('siege', 'UnitType')
    
    units_data = [
        {'slug': 'peasant', 'name': 'Paysan', 'cost': 10, 'power': 1, 'emoji': '🧑‍🌾'},
        {'slug': 'archer', 'name': 'Archer', 'cost': 30, 'power': 4, 'emoji': '🏹'},
        {'slug': 'knight', 'name': 'Chevalier', 'cost': 80, 'power': 12, 'emoji': '⚔️'},
        {'slug': 'catapult', 'name': 'Catapulte', 'cost': 150, 'power': 25, 'emoji': '☄️'},
    ]
    
    for unit in units_data:
        UnitType.objects.create(**unit)

def reverse_populate(apps, schema_editor):
    UnitType = apps.get_model('siege', 'UnitType')
    UnitType.objects.all().delete()

class Migration(migrations.Migration):

    dependencies = [
        ('siege', '0004_unittype'),
    ]

    operations = [
        migrations.RunPython(populate_units, reverse_populate),
    ]
