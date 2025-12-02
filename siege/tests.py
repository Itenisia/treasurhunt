from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import SiegeProfile, Battle, UnitType
from .views import resolve_battle
import json
from datetime import timedelta
from django.utils import timezone

class SiegeModelTests(TestCase):
    def test_siege_profile_creation(self):
        """Test that a SiegeProfile is created when a User is created."""
        user = User.objects.create_user(username='testuser', password='password')
        self.assertTrue(hasattr(user, 'siege_profile'))
        self.assertEqual(user.siege_profile.gold, 100)

    def test_battle_creation(self):
        """Test Battle model creation."""
        attacker = User.objects.create_user(username='attacker', password='password')
        defender = User.objects.create_user(username='defender', password='password')
        battle = Battle.objects.create(attacker=attacker, defender=defender)
        self.assertEqual(battle.status, 'PREPARING')
        self.assertEqual(str(battle), f"Bataille {battle.id}: {attacker} vs {defender}")

class SiegeViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.attacker = User.objects.create_user(username='attacker', password='password')
        self.defender = User.objects.create_user(username='defender', password='password')
        self.client.login(username='attacker', password='password')

    def test_create_challenge(self):
        """Test creating a challenge."""
        url = reverse('siege:create_challenge', args=[self.defender.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # Redirects to prepare
        self.assertTrue(Battle.objects.filter(attacker=self.attacker, defender=self.defender).exists())

    def test_create_challenge_self(self):
        """Test that you cannot challenge yourself."""
        url = reverse('siege:create_challenge', args=[self.attacker.id])
        response = self.client.get(url)
        # Should redirect to select_opponent with an error message
        self.assertRedirects(response, reverse('siege:select_opponent'))
        messages = list(response.wsgi_request._messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Vous ne pouvez pas vous attaquer vous-même !")

    def test_rate_limit_hourly(self):
        """Test hourly rate limit."""
        # Create a battle 30 minutes ago
        Battle.objects.create(attacker=self.attacker, defender=self.defender, created_at=timezone.now() - timedelta(minutes=30))
        
        url = reverse('siege:create_challenge', args=[self.defender.id])
        response = self.client.get(url)
        self.assertRedirects(response, reverse('siege:select_opponent'))
        
        # Verify no new battle was created (count should be 1 from the setup)
        self.assertEqual(Battle.objects.filter(attacker=self.attacker, defender=self.defender).count(), 1)

    def test_submit_army(self):
        """Test submitting an army."""
        battle = Battle.objects.create(attacker=self.attacker, defender=self.defender)
        url = reverse('siege:submit_army', args=[battle.id])
        
        # Attacker submits army
        data = {'units': {'peasant': 5}} # Cost: 5 * 10 = 50. Attacker has 100.
        response = self.client.post(url, json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        battle.refresh_from_db()
        self.assertEqual(battle.attacker_units, {'peasant': 5})
        self.attacker.siege_profile.refresh_from_db()
        # Peasant cost is 10
        peasant_cost = UnitType.objects.get(slug='peasant').cost
        self.assertEqual(self.attacker.siege_profile.gold, 100 - (5 * peasant_cost))

    def test_submit_army_too_expensive(self):
        """Test submitting an army that costs too much."""
        battle = Battle.objects.create(attacker=self.attacker, defender=self.defender)
        url = reverse('siege:submit_army', args=[battle.id])
        
        # Attacker tries to buy too many peasants
        data = {'units': {'peasant': 20}} # Cost: 20 * 10 = 200. Attacker has 100.
        response = self.client.post(url, json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        battle.refresh_from_db()
        self.assertEqual(battle.attacker_units, {})

        battle.refresh_from_db()
        self.assertEqual(battle.attacker_units, {})

    def test_placement_view(self):
        """Test that the placement view loads correctly."""
        battle = Battle.objects.create(attacker=self.attacker, defender=self.defender)
        # Give attacker some units
        battle.attacker_units = {'peasant': 5}
        battle.save()
        
        url = reverse('siege:placement', args=[battle.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'siege/placement.html')
        self.assertContains(response, 'peasant')
        self.assertContains(response, '5')

    def test_save_placement(self):
        """Test saving the placement layout."""
        battle = Battle.objects.create(attacker=self.attacker, defender=self.defender)
        battle.attacker_units = {'peasant': 1}
        battle.save()
        
        url = reverse('siege:save_placement', args=[battle.id])
        layout = {'0,0': 'peasant'}
        data = {'layout': layout}
        
        response = self.client.post(url, json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        battle.refresh_from_db()
        self.assertEqual(battle.attacker_layout, layout)

class SiegeLogicTests(TestCase):
    def setUp(self):
        self.attacker = User.objects.create_user(username='attacker', password='password')
        self.defender = User.objects.create_user(username='defender', password='password')
        self.battle = Battle.objects.create(attacker=self.attacker, defender=self.defender, status='FIGHTING')

    def test_resolve_battle_attacker_wins(self):
        """Test attacker wins."""
        # Attacker: 10 peasants (Power: 10 * 1 = 10)
        # Defender: 1 peasant (Power: 1 * 1 = 1)
        self.battle.attacker_units = {'peasant': 10}
        self.battle.defender_units = {'peasant': 1}
        self.battle.save()

        resolve_battle(self.battle)
        
        self.assertEqual(self.battle.winner, self.attacker)
        self.assertEqual(self.battle.status, 'FINISHED')
        
        self.attacker.siege_profile.refresh_from_db()
        # Initial 100 + 50 win = 150
        self.assertEqual(self.attacker.siege_profile.gold, 150)
