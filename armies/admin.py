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
    list_display = ("name", "faction", "cost", "target_units", "attack_bonus_pct_display", "defense_bonus")
    search_fields = ("name",)
    list_filter = ("faction", "unit_types")
    filter_horizontal = ("unit_types",)
    fields = (
        "name",
        "faction",
        "cost",
        "description",
        "attack_bonus_pct",
        "defense_bonus",
        "health_bonus",
        "speed_bonus",
        "unit_types",
    )

    @admin.display(description="Cible unités")
    def target_units(self, obj):
        units = list(obj.unit_types.values_list("name", flat=True))
        if not units and obj.unit_type_id:
            return obj.unit_type.name
        return ", ".join(units) if units else "Global"

    @admin.display(description="Bonus attaque")
    def attack_bonus_pct_display(self, obj):
        pct = obj.attack_bonus_pct or 0
        return f"+{pct * 100:.0f}%"


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
