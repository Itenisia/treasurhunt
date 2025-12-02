import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from siege.models import SiegeProfile

def add_gold():
    user = User.objects.get(username='Player1')
    profile, _ = SiegeProfile.objects.get_or_create(user=user)
    profile.gold = 1000
    profile.save()
    print(f"Added gold to {user.username}. New balance: {profile.gold}")

if __name__ == "__main__":
    add_gold()
