from django.db import models
from django.contrib.auth.models import User


class Commander(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name="commander")
    faction = models.ForeignKey("Faction", on_delete=models.SET_NULL, null=True, blank=True, related_name="commanders")
    name = models.CharField(max_length=80, unique=True)
    gold = models.PositiveIntegerField(default=1000)
    pop_cap = models.PositiveIntegerField(default=30, help_text="Limite de population pour l'admin")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.gold} or)"


class UnitType(models.Model):
    faction = models.ForeignKey("Faction", on_delete=models.SET_NULL, null=True, blank=True, related_name="units")
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    cost = models.PositiveIntegerField(default=50)
    defense = models.PositiveIntegerField(default=1)
    health = models.PositiveIntegerField(default=5)
    speed = models.PositiveIntegerField(default=1, help_text="Vitesse d'attaque historique (conservée pour compatibilité)")
    attack_speed = models.FloatField(default=1.0, help_text="Attaques par seconde (cap à 4)")
    move_speed = models.FloatField(default=1.0, help_text="Vitesse de déplacement en cases/s")
    range = models.PositiveIntegerField(default=1, help_text="Portée en cases (1 = mêlée)")
    damage_min = models.FloatField(default=0.9, help_text="Variance dégâts min (multiplicateur)")
    damage_max = models.FloatField(default=1.1, help_text="Variance dégâts max (multiplicateur)")
    pop_cost = models.PositiveIntegerField(default=1, help_text="Coût en population pour cette unité")
    crit_chance = models.FloatField(default=0.1, help_text="Chance de critique (0-1)")
    crit_multiplier = models.FloatField(default=2.0, help_text="Multiplicateur critique")
    dodge_chance = models.FloatField(default=0.0, help_text="Chance d'esquive (0-0.5)")
    aoe_radius = models.PositiveIntegerField(default=0, help_text="Rayon AOE en cases (0 = monocible)")
    ATTACK_TYPE_CHOICES = [
        ("normal", "Normal"),
        ("piercing", "Piercing"),
        ("siege", "Siege"),
        ("magic", "Magic"),
        ("hero", "Hero"),
        ("chaos", "Chaos"),
        ("spells", "Spells"),
    ]
    ARMOR_TYPE_CHOICES = [
        ("unarmored", "Unarmored"),
        ("light", "Light"),
        ("medium", "Medium"),
        ("heavy", "Heavy"),
        ("fortified", "Fortified"),
        ("hero", "Hero"),
        ("divine", "Divine"),
    ]
    attack_type = models.CharField(max_length=20, choices=ATTACK_TYPE_CHOICES, default="normal")
    armor_type = models.CharField(max_length=20, choices=ARMOR_TYPE_CHOICES, default="unarmored")

    def __str__(self) -> str:
        return self.name


class Upgrade(models.Model):
    faction = models.ForeignKey("Faction", on_delete=models.SET_NULL, null=True, blank=True, related_name="upgrades")
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    cost = models.PositiveIntegerField(default=25)
    attack_bonus = models.IntegerField(default=0)
    defense_bonus = models.IntegerField(default=0)
    health_bonus = models.IntegerField(default=0)
    speed_bonus = models.IntegerField(default=0)
    unit_type = models.ForeignKey(
        UnitType,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        help_text="Spécifiez pour cibler une unité précise. Vide = bonus global.",
    )

    def __str__(self) -> str:
        return self.name


class Army(models.Model):
    faction = models.ForeignKey("Faction", on_delete=models.SET_NULL, null=True, blank=True, related_name="armies")
    commander = models.ForeignKey(
        Commander, on_delete=models.CASCADE, related_name="armies"
    )
    name = models.CharField(max_length=80)
    formation_name = models.CharField(
        max_length=100, blank=True, help_text="Nom convivial de la formation enregistrée."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("commander", "name")

    def __str__(self) -> str:
        return f"{self.name} / {self.commander.name}"


class ArmyUnit(models.Model):
    army = models.ForeignKey(Army, on_delete=models.CASCADE, related_name="units")
    unit_type = models.ForeignKey(UnitType, on_delete=models.CASCADE)
    position_x = models.PositiveIntegerField(null=True, blank=True)
    position_y = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.unit_type} ({self.army})"


class ArmyUpgrade(models.Model):
    army = models.ForeignKey(Army, on_delete=models.CASCADE, related_name="upgrades")
    upgrade = models.ForeignKey(Upgrade, on_delete=models.CASCADE)
    level = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("army", "upgrade")

    def __str__(self) -> str:
        return f"{self.army}: {self.upgrade} (niv. {self.level})"


class Battle(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_RESOLVED, "Résolu"),
    ]

    attacker = models.ForeignKey(
        Army, on_delete=models.CASCADE, related_name="attacking_battles"
    )
    defender = models.ForeignKey(
        Army, on_delete=models.CASCADE, related_name="defending_battles"
    )
    winner = models.ForeignKey(
        Army, on_delete=models.SET_NULL, null=True, blank=True, related_name="wins"
    )
    reward = models.PositiveIntegerField(default=0)
    rounds = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    log = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        vs = f"{self.attacker} vs {self.defender}"
        return f"Combat ({self.status}) {vs}"


class AttackPreset(models.Model):
    army = models.ForeignKey(Army, on_delete=models.CASCADE, related_name="attack_presets")
    name = models.CharField(max_length=50)
    positions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("army", "name")

    def __str__(self) -> str:
        return f"{self.army} - {self.name}"


class Faction(models.Model):
    name = models.CharField(max_length=80, unique=True)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name
