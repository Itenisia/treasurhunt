import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.management import call_command
from openpyxl import Workbook
from game.models import Hunt

from tempfile import TemporaryDirectory

def reproduce():
    try:
        with TemporaryDirectory() as tmp:
            path = f"{tmp}/hunt.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["Import Hunt", "Description import", "First clue"])
            ws.append([1, "Spot A", "Go to B"])
            ws.append([2, "Spot B", "Go to C"])
            wb.save(path)

            print(f"Created {path}")
            
            call_command("import_hunt_xlsx", path)
            
            hunt = Hunt.objects.get(title="Import Hunt")
            print(f"Successfully imported hunt: {hunt.title}")
            
    except Exception as e:
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    reproduce()
