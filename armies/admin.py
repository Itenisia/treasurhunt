from django.contrib import admin

from .models import (
    Army,
    ArmyUnit,
    ArmyUpgrade,
    AttackPreset,
    Battle,
    Commander,
    Faction,
    UnitType,
    Upgrade,
)


@admin.register(Commander)
class CommanderAdmin(admin.ModelAdmin):
    list_display = ("name", "gold", "created_at")
    search_fields = ("name",)


@admin.register(UnitType)
class UnitTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "faction", "cost", "defense", "health", "attack_speed", "range")
    search_fields = ("name",)
    list_filter = ("faction",)


@admin.register(Upgrade)
class UpgradeAdmin(admin.ModelAdmin):
    list_display = ("name", "faction", "cost", "unit_type", "attack_bonus", "defense_bonus")
    search_fields = ("name",)
    list_filter = ("faction", "unit_type")


class ArmyUnitInline(admin.TabularInline):
    model = ArmyUnit
    extra = 0


class ArmyUpgradeInline(admin.TabularInline):
    model = ArmyUpgrade
    extra = 0


@admin.register(Army)
class ArmyAdmin(admin.ModelAdmin):
    list_display = ("name", "faction", "commander", "formation_name", "created_at")
    search_fields = ("name", "commander__name")
    inlines = [ArmyUnitInline, ArmyUpgradeInline]


@admin.register(Battle)
class BattleAdmin(admin.ModelAdmin):
    list_display = ("id", "attacker", "defender", "winner", "reward", "status")
    list_filter = ("status",)


@admin.register(AttackPreset)
class AttackPresetAdmin(admin.ModelAdmin):
    list_display = ("name", "army", "created_at")
    search_fields = ("name", "army__name", "army__commander__name")


@admin.register(Faction)
class FactionAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
