import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']

from django.test import Client
from django.contrib.auth.models import User
from siege.models import UnitType, Battle, SiegeProfile
from django.urls import reverse

def reproduce():
    print("Setting up test data...")
    # Create Units
    UnitType.objects.get_or_create(slug='peasant', defaults={'name': 'Paysan', 'cost': 10, 'power': 1, 'emoji': '🌾'})
    UnitType.objects.get_or_create(slug='archer', defaults={'name': 'Archer', 'cost': 20, 'power': 3, 'emoji': '🏹'})
    
    # Create User
    user, _ = User.objects.get_or_create(username='Player1')
    user.set_password('password')
    user.save()
    
    # Ensure profile exists and has gold
    profile, _ = SiegeProfile.objects.get_or_create(user=user)
    profile.gold = 1000
    profile.save()
    
    client = Client()
    client.force_login(user)
    
    print("1. Starting training...")
    url = reverse('siege:training')
    response = client.get(url, follow=True)
    
    # Should redirect to prepare
    if response.status_code != 200:
        print(f"Error starting training: {response.status_code}")
        return
        
    print(f"Redirected to: {response.redirect_chain[-1][0]}")
    
    # Get the battle
    battle = Battle.objects.filter(attacker=user, defender__username='Entraineur').last()
    if not battle:
        print("Error: Battle not created!")
        return
    print(f"Battle created: {battle}")
    
    print("2. Submitting army...")
    url = reverse('siege:submit_army', args=[battle.id])
    data = {'units': {'peasant': 5, 'archer': 2}} # Cost: 50 + 40 = 90
    response = client.post(url, json.dumps(data), content_type='application/json')
    
    if response.status_code != 200:
        print(f"Error submitting army: {response.status_code}")
        print(response.content.decode())
        return
    print("Army submitted successfully.")
    
    battle.refresh_from_db()
    print(f"Attacker units: {battle.attacker_units}")
    print(f"Defender (Bot) units: {battle.defender_units}")
    print(f"Defender (Bot) layout: {battle.defender_layout}")
    
    if not battle.defender_units:
        print("Error: Bot army not generated!")
    
    if not battle.defender_layout:
        print("Error: Bot layout not generated!")

    print("3. Placing units...")
    url = reverse('siege:save_placement', args=[battle.id])
    # Simple layout
    layout = {}
    for i in range(5):
        layout[f"0,{i}"] = 'peasant'
    for i in range(2):
        layout[f"1,{i}"] = 'archer'
        
    data = {'layout': layout}
    response = client.post(url, json.dumps(data), content_type='application/json')
    
    if response.status_code != 200:
        print(f"Error saving placement: {response.status_code}")
        print(response.content.decode())
        return
    print("Placement saved.")
    
    battle.refresh_from_db()
    print(f"Battle status: {battle.status}")
    
    if battle.status != 'FIGHTING':
        print("Error: Battle status should be FIGHTING!")
        
    print("4. Checking battle state (resolution)...")
    url = reverse('siege:state', args=[battle.id])
    response = client.get(url)
    
    if response.status_code != 200:
        print(f"Error checking state: {response.status_code}")
        return
        
    state = response.json()
    print(f"State: {state}")
    
    if state['status'] == 'FINISHED':
        print(f"Battle finished! Winner: {state['winner']}")
    else:
        print("Battle still in progress (or not resolved).")

if __name__ == "__main__":
    reproduce()
