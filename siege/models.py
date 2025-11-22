from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver



class UnitType(models.Model):
    slug = models.SlugField(primary_key=True)
    name = models.CharField(max_length=50)
    cost = models.PositiveIntegerField()
    power = models.PositiveIntegerField()
    emoji = models.CharField(max_length=10, help_text="Representation (e.g. 🏹)")
    
    def __str__(self):
        return f"{self.name} ({self.emoji})"

class SiegeProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='siege_profile')
    gold = models.IntegerField(default=100)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    
    refusals_today = models.IntegerField(default=0)
    last_refusal_date = models.DateField(null=True, blank=True)
    default_army = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.gold} Or"

class Battle(models.Model):
    STATUS_CHOICES = [
        ('PREPARING', 'En préparation'),
        ('FIGHTING', 'En combat'),
        ('FINISHED', 'Terminé'),
    ]

    attacker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='battles_attacked')
    defender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='battles_defended')
    
    attacker_units = models.JSONField(default=dict)
    defender_units = models.JSONField(default=dict)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PREPARING')
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='battles_won')
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Bataille {self.id}: {self.attacker} vs {self.defender}"

@receiver(post_save, sender=User)
def create_siege_profile(sender, instance, created, **kwargs):
    if created:
        SiegeProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_siege_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'siege_profile'):
         SiegeProfile.objects.create(user=instance)
