import json
import math
from datetime import timedelta
from typing import Any, Dict, Optional

from django.http import HttpRequest, JsonResponse
from django.db.models import Q, Exists, OuterRef
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from .models import (
    Army,
    ArmyUnit,
    ArmyUpgrade,
    AttackPreset,
    Battle,
    Commander,
    UnitType,
    Upgrade,
    Faction,
)
from .services import army_value, army_population, simulate_battle, upgrade_purchase_cost


def _json_body(request) -> Dict[str, Any]:
    if not request.body:
        return {}
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        return {}


def _commander_for_user(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, "commander", None)


def _army_payload(army: Army) -> Dict[str, Any]:
    pop_used = army_population(army)
    return {
        "id": army.id,
        "name": army.name,
        "commander": army.commander.name,
        "formation": army.formation_name,
        "pop_used": pop_used,
        "pop_cap": army.commander.pop_cap,
        "units": [
            {
                "id": stack.id,
                "unit_type": stack.unit_type.name,
                "position": {"x": stack.position_x, "y": stack.position_y},
            }
            for stack in army.units.select_related("unit_type")
        ],
        "upgrades": [
            {"id": u.id, "name": u.upgrade.name, "level": u.level}
            for u in army.upgrades.select_related("upgrade")
        ],
    }


def _default_army_name(user, commander: Commander | None = None) -> str:
    username = (getattr(user, "username", "") or "").strip()
    if username:
        return username
    if commander and commander.name:
        return commander.name
    return "Mon armée"


def _ensure_default_army(commander: Commander, user) -> tuple[Army, bool]:
    """
    Ensure the commander has a single army named after the user.
    Returns (army, created_flag).
    """
    desired_name = _default_army_name(user, commander)
    army = commander.armies.filter(name=desired_name).order_by("id").first()
    created = False
    if not army:
        army = commander.armies.order_by("id").first()
        if army:
            if army.name != desired_name:
                army.name = desired_name
                army.save(update_fields=["name"])
        else:
            army = Army.objects.create(commander=commander, name=desired_name, faction=commander.faction)
            created = True
    return army, created


def _has_recent_battle(attacker: Army, defender: Army, window: timedelta = timedelta(hours=1)) -> bool:
    """Return True if attacker fought defender within the cooldown window (resolved battles only)."""
    since = timezone.now() - window
    return Battle.objects.filter(
        attacker=attacker,
        defender=defender,
        status=Battle.STATUS_RESOLVED,
        resolved_at__gte=since,
    ).exists()


def _expected_score(rating_a: int, rating_b: int) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def _apply_elo(attacker: Army, defender: Army, winner: Optional[Army], k_factor: int = 32) -> None:
    """
    Apply Elo update for attacker/defender when winner is known (ignore draws).
    Only applies for human-controlled armies.
    """
    if not winner or winner not in (attacker, defender):
        return
    if not (getattr(attacker.commander, "user_id", None) and getattr(defender.commander, "user_id", None)):
        return

    expected_attacker = _expected_score(attacker.elo, defender.elo)
    expected_defender = _expected_score(defender.elo, attacker.elo)
    score_attacker = 1 if winner == attacker else 0
    score_defender = 1 - score_attacker

    attacker.elo = round(attacker.elo + k_factor * (score_attacker - expected_attacker))
    defender.elo = round(defender.elo + k_factor * (score_defender - expected_defender))
    attacker.save(update_fields=["elo"])
    defender.save(update_fields=["elo"])


def _badge_for_rank(rank: int, total: int) -> str:
    if rank == 1:
        return "Platine"
    if rank in (2, 3):
        return "Diamant"
    gold_cut = max(1, math.ceil(total / 3))
    silver_cut = max(1, math.ceil(2 * total / 3))
    if rank <= gold_cut:
        return "Or"
    if rank <= silver_cut:
        return "Argent"
    return "Bronze"


def _army_leaderboard():
    armies = list(Army.objects.select_related("commander").order_by("-elo", "id"))
    total = len(armies)
    for idx, army in enumerate(armies, start=1):
        army.rank = idx
        army.badge = _badge_for_rank(idx, total)
    return armies


@csrf_exempt
def commanders(request):
    if request.method == "GET":
        payload = [
            {"id": c.id, "name": c.name, "gold": c.gold}
            for c in Commander.objects.all().order_by("id")
        ]
        return JsonResponse({"commanders": payload})

    if request.method == "POST":
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentification requise"}, status=401)
        if _commander_for_user(request.user):
            return JsonResponse({"error": "Déjà un commandant"}, status=400)
        data = _json_body(request)
        name = data.get("name")
        starting_gold = data.get("gold", 1000)
        faction_id = data.get("faction_id")
        faction = None
        if faction_id:
            faction = Faction.objects.filter(id=faction_id).first()
        if not name:
            return JsonResponse({"error": "name requis"}, status=400)
        commander = Commander.objects.create(
            user=request.user, name=name, gold=starting_gold, faction=faction
        )
        _ensure_default_army(commander, request.user)
        return JsonResponse(
            {"id": commander.id, "name": commander.name, "gold": commander.gold},
            status=201,
        )

    return JsonResponse({"error": "Méthode non supportée"}, status=405)


@csrf_exempt
def unit_types(request):
    if request.method == "GET":
        units = [
            {
                "id": u.id,
                "name": u.name,
                "description": u.description,
                "cost": u.cost,
                "defense": u.defense,
                "health": u.health,
                "speed": u.speed,
                "damage_min": u.damage_min,
                "damage_max": u.damage_max,
                "attack_type": u.attack_type,
                "armor_type": u.armor_type,
                "pop_cost": u.pop_cost,
            }
            for u in UnitType.objects.all()
        ]
        return JsonResponse({"units": units})

    if request.method == "POST":
        data = _json_body(request)
        required = ["name", "cost", "defense", "health", "speed", "damage_min", "damage_max", "pop_cost"]
        if any(field not in data for field in required):
            return JsonResponse({"error": "Champs manquants"}, status=400)
        unit = UnitType.objects.create(
            name=data["name"],
            description=data.get("description", ""),
            cost=data["cost"],
            defense=data["defense"],
            health=data["health"],
            speed=data["speed"],
            attack_speed=data.get("attack_speed", 1.0),
            move_speed=data.get("move_speed", 1.0),
            range=data.get("range", 1),
            damage_min=data["damage_min"],
            damage_max=data["damage_max"],
            attack_type=data.get("attack_type", "normal"),
            armor_type=data.get("armor_type", "unarmored"),
            crit_chance=data.get("crit_chance", 0.1),
            crit_multiplier=data.get("crit_multiplier", 2.0),
            dodge_chance=data.get("dodge_chance", 0.0),
            aoe_radius=data.get("aoe_radius", 0),
            pop_cost=data["pop_cost"],
        )
        return JsonResponse({"id": unit.id}, status=201)

    return JsonResponse({"error": "Méthode non supportée"}, status=405)


@csrf_exempt
def armies(request):
    if request.method == "GET":
        payload = [_army_payload(army) for army in Army.objects.all()]
        return JsonResponse({"armies": payload})

    if request.method == "POST":
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentification requise"}, status=401)
        commander = _commander_for_user(request.user)
        if not commander:
            return JsonResponse({"error": "Commander non initialisé"}, status=400)
        data = _json_body(request)
        army, created = _ensure_default_army(commander, request.user)
        if "formation_name" in data:
            formation = data.get("formation_name") or ""
            if army.formation_name != formation:
                army.formation_name = formation
                army.save(update_fields=["formation_name"])
        if army.faction_id != commander.faction_id:
            army.faction = commander.faction
            army.save(update_fields=["faction"])
        return JsonResponse(_army_payload(army), status=201 if created else 200)

    return JsonResponse({"error": "Méthode non supportée"}, status=405)


@csrf_exempt
def purchase_unit(request, army_id: int):
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non supportée"}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentification requise"}, status=401)
    commander = _commander_for_user(request.user)
    if not commander:
        return JsonResponse({"error": "Commander manquant"}, status=400)
    default_army, _ = _ensure_default_army(commander, request.user)
    data = _json_body(request)
    unit_type_id = data.get("unit_type_id")
    quantity = int(data.get("quantity", 1))
    if not unit_type_id or quantity <= 0:
        return JsonResponse({"error": "unit_type_id et quantity requis"}, status=400)

    army = get_object_or_404(Army, id=army_id)
    if army.commander_id != commander.id:
        return JsonResponse({"error": "Armée hors propriété"}, status=403)
    if default_army and army.id != default_army.id:
        return JsonResponse({"error": "Une seule armée est autorisée, nommée comme votre compte."}, status=400)
    unit_type = get_object_or_404(UnitType, id=unit_type_id)
    if (army.faction_id and unit_type.faction_id and army.faction_id != unit_type.faction_id) or (
        commander.faction_id and unit_type.faction_id and commander.faction_id != unit_type.faction_id
    ):
        return JsonResponse({"error": "Unité hors faction"}, status=400)
    cost = unit_type.cost * quantity
    if army.commander.gold < cost:
        return JsonResponse({"error": "Or insuffisant"}, status=400)
    pop_used = army_population(army)
    pop_needed = unit_type.pop_cost * quantity
    if pop_used + pop_needed > army.commander.pop_cap:
        return JsonResponse({"error": f"Population insuffisante ({pop_used}/{army.commander.pop_cap})"}, status=400)

    army.commander.gold -= cost
    army.commander.save(update_fields=["gold"])

    new_units = [ArmyUnit(army=army, unit_type=unit_type) for _ in range(quantity)]
    ArmyUnit.objects.bulk_create(new_units)
    return JsonResponse(
        {"army": _army_payload(army), "remaining_gold": army.commander.gold}
    )


@csrf_exempt
def purchase_upgrade(request, army_id: int):
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non supportée"}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentification requise"}, status=401)
    commander = _commander_for_user(request.user)
    if not commander:
        return JsonResponse({"error": "Commander manquant"}, status=400)
    default_army, _ = _ensure_default_army(commander, request.user)
    data = _json_body(request)
    upgrade_id = data.get("upgrade_id")
    level = int(data.get("level", 1))
    if not upgrade_id or level <= 0:
        return JsonResponse({"error": "upgrade_id et level requis"}, status=400)

    army = get_object_or_404(Army, id=army_id)
    if army.commander_id != commander.id:
        return JsonResponse({"error": "Armée hors propriété"}, status=403)
    if default_army and army.id != default_army.id:
        return JsonResponse({"error": "Une seule armée est autorisée, nommée comme votre compte."}, status=400)
    upgrade = get_object_or_404(Upgrade, id=upgrade_id)
    if army.faction and upgrade.faction and army.faction_id != upgrade.faction_id:
        return JsonResponse({"error": "Upgrade hors faction"}, status=400)
    current_level = (
        ArmyUpgrade.objects.filter(army=army, upgrade=upgrade)
        .values_list("level", flat=True)
        .first()
        or 0
    )
    cost = upgrade_purchase_cost(upgrade, current_level, level)
    if army.commander.gold < cost:
        return JsonResponse({"error": "Or insuffisant"}, status=400)

    army.commander.gold -= cost
    army.commander.save(update_fields=["gold"])

    link, created = ArmyUpgrade.objects.get_or_create(
        army=army, upgrade=upgrade, defaults={"level": 0}
    )
    link.level += level
    link.save(update_fields=["level"])
    return JsonResponse(
        {"army": _army_payload(army), "remaining_gold": army.commander.gold},
        status=201 if created else 200,
    )


@csrf_exempt
def place_unit(request, army_id: int):
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non supportée"}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentification requise"}, status=401)
    commander = _commander_for_user(request.user)
    if not commander:
        return JsonResponse({"error": "Commander manquant"}, status=400)
    default_army, _ = _ensure_default_army(commander, request.user)
    data = _json_body(request)
    unit_id = data.get("army_unit_id")
    x = data.get("x")
    y = data.get("y")
    if x is None or y is None:
        return JsonResponse({"error": "x et y requis"}, status=400)

    army = get_object_or_404(Army, id=army_id)
    if army.commander_id != commander.id:
        return JsonResponse({"error": "Armée hors propriété"}, status=403)
    if default_army and army.id != default_army.id:
        return JsonResponse({"error": "Une seule armée est autorisée, nommée comme votre compte."}, status=400)
    if not unit_id:
        return JsonResponse({"error": "army_unit_id requis"}, status=400)
    stack = get_object_or_404(ArmyUnit, id=unit_id, army=army)

    stack.position_x = int(x)
    stack.position_y = int(y)
    stack.save(update_fields=["position_x", "position_y"])
    return JsonResponse({"army": _army_payload(army)})


@csrf_exempt
def create_challenge(request):
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non supportée"}, status=405)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentification requise"}, status=401)
    commander = _commander_for_user(request.user)
    if not commander:
        return JsonResponse({"error": "Commander manquant"}, status=400)
    attacker, _ = _ensure_default_army(commander, request.user)
    data = _json_body(request)
    attacker_input = data.get("attacker_id")
    if attacker_input is not None:
        try:
            attacker_id = int(attacker_input)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Identifiant d'armée invalide"}, status=400)
        if attacker_id != attacker.id:
            return JsonResponse({"error": "Une seule armée est autorisée, nommée comme votre compte."}, status=400)
    defender_id = data.get("defender_id")
    if not defender_id:
        return JsonResponse({"error": "defender_id requis"}, status=400)
    defender = get_object_or_404(Army, id=defender_id)
    if attacker.id == defender.id:
        return JsonResponse({"error": "Choisir deux armées distinctes"}, status=400)
    if _has_recent_battle(attacker, defender):
        return JsonResponse({"error": "Vous avez déjà attaqué cette armée il y a moins d'une heure."}, status=400)

    battle = Battle.objects.create(attacker=attacker, defender=defender)
    outcome = simulate_battle(attacker, defender)
    winner_field = outcome["winner"]
    winner_army = attacker if winner_field == "attacker" else defender if winner_field == "defender" else None

    attacker_value = army_value(attacker)
    defender_value = army_value(defender)
    winner_reward = 0
    loser_reward = 0
    if winner_field == "attacker":
        winner_reward = round(defender_value * 0.2)
        loser_reward = round(attacker_value * 0.1)
    elif winner_field == "defender":
        winner_reward = round(attacker_value * 0.2)
        loser_reward = round(defender_value * 0.1)
    battle.winner = winner_army
    battle.rounds = outcome["rounds"]
    battle.log = outcome["log"]
    battle.status = Battle.STATUS_RESOLVED
    battle.resolved_at = timezone.now()
    battle.reward = winner_reward
    battle.metadata = outcome.get("initial_positions", {})
    battle.save()
    _apply_elo(attacker, defender, winner_army)

    if winner_reward and winner_army:
        winner_army.commander.gold += winner_reward
        winner_army.commander.save(update_fields=["gold"])
    if loser_reward:
        loser_commander = attacker.commander if winner_field == "defender" else defender.commander
        loser_commander.gold += loser_reward
        loser_commander.save(update_fields=["gold"])

    return JsonResponse(
        {
            "battle_id": battle.id,
            "winner": winner_field,
            "winner_reward": winner_reward if winner_army else 0,
            "loser_reward": loser_reward if winner_army else 0,
            "rounds": outcome["rounds"],
            "log": outcome["log"],
            "attacker_remaining": outcome["attacker_remaining"],
            "defender_remaining": outcome["defender_remaining"],
        }
    )


def placement_page(request: HttpRequest):
    armies_all = list(Army.objects.select_related("commander").all())
    if not armies_all:
        return render(request, "armies/placement.html", {"armies": [], "selected_army": None})
    army_id = request.GET.get("army") or armies_all[0].id
    try:
        army_id = int(army_id)
    except (TypeError, ValueError):
        army_id = armies_all[0].id
    selected_army = next((a for a in armies_all if a.id == army_id), armies_all[0])
    presets = selected_army.attack_presets.values_list("name", flat=True)
    defender_id = request.GET.get("defender")
    defender_army = None
    if defender_id:
        try:
            defender_army = Army.objects.select_related("commander").get(id=int(defender_id))
        except (Army.DoesNotExist, ValueError, TypeError):
            defender_army = None

    return render(
        request,
        "armies/placement.html",
        {
            "armies": armies_all,
        "selected_army": selected_army,
        "presets": presets,
        "mode": request.GET.get("mode", "defense"),
        "defender_army": defender_army,
        "defender_units": _positions_for_army_units(defender_army) if defender_army else [],
        "after_battle_flag": bool(request.GET.get("after_battle")),
    },
)


def _validate_positions(positions, mode: str):
    for pos in positions:
        x = pos.get("x")
        y = pos.get("y")
        if x is None or y is None:
            raise ValueError("x et y requis")
        if not (0 <= int(x) < 10 and 0 <= int(y) < 10):
            raise ValueError("Coordonnées hors grille")
        if mode == "defense" and int(x) not in (8, 9):
            raise ValueError("Défense limitée aux colonnes 8 et 9")
        if mode == "attack" and int(x) not in (0, 1):
            raise ValueError("Attaque limitée aux colonnes 0 et 1")


def _positions_for_army_units(army: Army, preset: AttackPreset | None = None):
    attack_map = {}
    if preset:
        for item in preset.positions:
            attack_map[item.get("army_unit_id")] = (item.get("x"), item.get("y"))
    units = []
    for stack in army.units.select_related("unit_type"):
        units.append(
            {
                "id": stack.id,
                "unit_name": stack.unit_type.name,
                "defense_position": {
                    "x": stack.position_x,
                    "y": stack.position_y,
                },
                "attack_position": {
                    "x": attack_map.get(stack.id, (None, None))[0],
                    "y": attack_map.get(stack.id, (None, None))[1],
                },
            }
        )
    return units


@csrf_exempt
def placement_data(request, army_id: int):
    army = get_object_or_404(Army, id=army_id)
    if request.method == "GET":
        mode = request.GET.get("mode", "defense")
        preset_name = request.GET.get("preset")
        preset = None
        if mode == "attack" and preset_name:
            preset = army.attack_presets.filter(name=preset_name).first()
        units = _positions_for_army_units(army, preset)
        presets = list(army.attack_presets.values_list("name", flat=True))
        return JsonResponse({"units": units, "presets": presets})

    if request.method == "POST":
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentification requise"}, status=401)
        commander = _commander_for_user(request.user)
        if not commander or army.commander_id != commander.id:
            return JsonResponse({"error": "Armée hors propriété"}, status=403)
        default_army, _ = _ensure_default_army(commander, request.user)
        if default_army and army.id != default_army.id:
            return JsonResponse({"error": "Une seule armée est autorisée, nommée comme votre compte."}, status=400)
        data = _json_body(request)
        mode = data.get("mode", "defense")
        positions = data.get("positions", [])
        try:
            _validate_positions(positions, mode)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)

        if mode != "defense":
            return JsonResponse({"error": "Utilisez /attack-presets pour sauvegarder l'attaque"}, status=400)
        # Save defense positions directly on ArmyUnit
        pos_by_id = {int(p["army_unit_id"]): p for p in positions if p.get("army_unit_id")}
        for stack in army.units.all():
            pos = pos_by_id.get(stack.id)
            stack.position_x = int(pos["x"]) if pos else None
            stack.position_y = int(pos["y"]) if pos else None
            stack.save(update_fields=["position_x", "position_y"])
        return JsonResponse({"status": "ok"})

    return JsonResponse({"error": "Méthode non supportée"}, status=405)


@csrf_exempt
def attack_presets(request, army_id: int):
    army = get_object_or_404(Army, id=army_id)
    if request.method == "GET":
        presets = [
            {"name": p.name, "positions": p.positions}
            for p in army.attack_presets.all().order_by("created_at")
        ]
        return JsonResponse({"presets": presets})

    if request.method == "POST":
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentification requise"}, status=401)
        commander = _commander_for_user(request.user)
        if not commander or army.commander_id != commander.id:
            return JsonResponse({"error": "Armée hors propriété"}, status=403)
        default_army, _ = _ensure_default_army(commander, request.user)
        if default_army and army.id != default_army.id:
            return JsonResponse({"error": "Une seule armée est autorisée, nommée comme votre compte."}, status=400)
        data = _json_body(request)
        name = data.get("name")
        positions = data.get("positions", [])
        if not name:
            return JsonResponse({"error": "name requis"}, status=400)
        try:
            _validate_positions(positions, "attack")
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)

        existing = army.attack_presets.filter(name=name).first()
        if not existing and name != "__auto__" and army.attack_presets.count() >= 3:
            return JsonResponse({"error": "Limite de 3 presets atteinte"}, status=400)

        preset = existing or AttackPreset(army=army, name=name)
        preset.positions = [
            {
                "army_unit_id": p.get("army_unit_id"),
                "x": int(p["x"]),
                "y": int(p["y"]),
            }
            for p in positions
        ]
        preset.save()
        return JsonResponse({"name": preset.name, "positions": preset.positions})

    return JsonResponse({"error": "Méthode non supportée"}, status=405)


def battle_detail(request, battle_id: int):
    battle = get_object_or_404(Battle.objects.select_related("attacker", "defender", "winner"), id=battle_id)
    return JsonResponse(
        {
            "id": battle.id,
            "attacker": battle.attacker.name,
            "defender": battle.defender.name,
            "winner": battle.winner.name if battle.winner else None,
            "reward": battle.reward,
            "rounds": battle.rounds,
            "log": battle.log,
            "initial_positions": battle.metadata,
            "created_at": battle.created_at,
        }
    )


def replay_page(request: HttpRequest, battle_id: int):
    battle = get_object_or_404(Battle.objects.select_related("attacker", "defender", "winner"), id=battle_id)
    return render(
        request,
        "armies/replay.html",
        {
            "battle_id": battle.id,
            "attacker": battle.attacker.name,
            "defender": battle.defender.name,
            "winner": battle.winner.name if battle.winner else None,
            "reward": battle.reward,
            "rounds": battle.rounds,
            "log": battle.log,
            "initial_positions": battle.metadata,
        },
    )


@login_required
def home(request: HttpRequest):
    current_commander = _commander_for_user(request.user)
    unit_filter = (request.GET.get("unit_filter") or request.POST.get("unit_filter") or "").strip()
    upgrade_filter = (request.GET.get("upgrade_filter") or request.POST.get("upgrade_filter") or "").strip()
    message = None
    commander_ready = bool(current_commander and current_commander.faction_id)
    default_army: Army | None = None
    default_army_created = False

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "init_commander":
            if current_commander:
                message = "Commandant déjà créé."
            else:
                faction_id = request.POST.get("faction_id")
                commander_name = (request.POST.get("commander_name") or request.user.username).strip()
                faction = Faction.objects.filter(id=faction_id).first() if faction_id else None
                if not faction:
                    message = "Choisissez une faction pour démarrer."
                else:
                    commander_name = commander_name or request.user.username
                    base_name = commander_name
                    suffix = 1
                    while Commander.objects.filter(name=commander_name).exists():
                        commander_name = f"{base_name}-{suffix}"
                        suffix += 1
                    current_commander = Commander.objects.create(
                        user=request.user,
                        name=commander_name,
                        gold=1000,
                        pop_cap=30,
                        faction=faction,
                    )
                    message = "Commandant créé."
                    commander_ready = True
                    default_army, default_army_created = _ensure_default_army(current_commander, request.user)
        elif action == "choose_faction":
            if not current_commander:
                message = "Créez d'abord votre commandant."
            elif current_commander.faction_id:
                message = "Faction déjà définie."
            else:
                faction_id = request.POST.get("faction_id")
                faction = Faction.objects.filter(id=faction_id).first() if faction_id else None
                if not faction:
                    message = "Choisissez une faction pour démarrer."
                else:
                    current_commander.faction = faction
                    current_commander.save(update_fields=["faction"])
                    message = "Faction enregistrée."
                    commander_ready = True
                    default_army, created = _ensure_default_army(current_commander, request.user)
                    default_army_created = default_army_created or created
        else:
            if not commander_ready:
                message = "Choisissez une faction pour créer votre commandant avant de jouer."
            else:
                default_army, created = _ensure_default_army(current_commander, request.user)
                default_army_created = default_army_created or created
                if action == "create_army":
                    message = (
                        f"Armée {default_army.name} créée."
                        if created
                        else f"Armée unique associée à votre compte : {default_army.name}."
                    )
                elif action == "challenge":
                    defender_id = request.POST.get("defender_id")
                    try:
                        defender_id_int = int(defender_id)
                    except (TypeError, ValueError):
                        message = "Choisissez une armée à défier."
                    else:
                        if defender_id_int == default_army.id:
                            message = "Choisissez une armée adverse."
                        else:
                            defender = get_object_or_404(Army, id=defender_id_int)
                            if _has_recent_battle(default_army, defender):
                                message = "Vous avez déjà attaqué cette armée il y a moins d'une heure."
                            else:
                                battle = Battle.objects.create(attacker=default_army, defender=defender)
                                outcome = simulate_battle(default_army, defender)
                                winner_field = outcome["winner"]
                                winner_army = (
                                    default_army
                                    if winner_field == "attacker"
                                    else defender
                                    if winner_field == "defender"
                                    else None
                                )
                                attacker_value = army_value(default_army)
                                defender_value = army_value(defender)
                                winner_reward = 0
                                loser_reward = 0
                                if winner_field == "attacker":
                                    winner_reward = round(defender_value * 0.2)
                                    loser_reward = round(attacker_value * 0.1)
                                elif winner_field == "defender":
                                    winner_reward = round(attacker_value * 0.2)
                                    loser_reward = round(defender_value * 0.1)

                                battle.winner = winner_army
                                battle.rounds = outcome["rounds"]
                                battle.log = outcome["log"]
                                battle.status = Battle.STATUS_RESOLVED
                                battle.resolved_at = timezone.now()
                                battle.reward = winner_reward
                                battle.save()

                                if winner_reward and winner_army:
                                    winner_army.commander.gold += winner_reward
                                    winner_army.commander.save(update_fields=["gold"])
                                if loser_reward:
                                    loser_commander = (
                                        default_army.commander if winner_field == "defender" else defender.commander
                                    )
                                    loser_commander.gold += loser_reward
                                    loser_commander.save(update_fields=["gold"])
                                _apply_elo(default_army, defender, winner_army)

                                message = (
                                    f"Combat #{battle.id} terminé. Vainqueur: {winner_field or 'égalité'} "
                                    f"(+{winner_reward} or pour le gagnant, +{loser_reward} pour le perdant)."
                                )
                elif action == "buy_unit":
                    unit_type_id = request.POST.get("unit_type_id")
                    quantity = int(request.POST.get("quantity") or 0)
                    if not (unit_type_id and quantity > 0):
                        message = "Sélectionnez un type d'unité et une quantité > 0."
                    else:
                        unit_type = get_object_or_404(UnitType, id=unit_type_id)
                        if (
                            default_army.faction_id
                            and unit_type.faction_id
                            and default_army.faction_id != unit_type.faction_id
                        ):
                            message = "Unité hors faction."
                        else:
                            cost = unit_type.cost * quantity
                            if default_army.commander.gold < cost:
                                message = "Or insuffisant."
                            else:
                                pop_used = army_population(default_army)
                                pop_needed = unit_type.pop_cost * quantity
                                if pop_used + pop_needed > default_army.commander.pop_cap:
                                    message = (
                                        f"Population insuffisante ({pop_used}/{default_army.commander.pop_cap})."
                                    )
                                else:
                                    default_army.commander.gold -= cost
                                    default_army.commander.save(update_fields=["gold"])
                                    new_units = [
                                        ArmyUnit(army=default_army, unit_type=unit_type) for _ in range(quantity)
                                    ]
                                    ArmyUnit.objects.bulk_create(new_units)
                                    message = (
                                        f"Acheté {quantity}x {unit_type.name} pour {default_army.name} (-{cost} or)."
                                    )
                elif action == "buy_upgrade":
                    upgrade_id = request.POST.get("upgrade_id")
                    level = int(request.POST.get("level") or 0)
                    if not (upgrade_id and level > 0):
                        message = "Sélectionnez un upgrade et un niveau > 0."
                    else:
                        upgrade = get_object_or_404(Upgrade, id=upgrade_id)
                        current_level = (
                            ArmyUpgrade.objects.filter(army=default_army, upgrade=upgrade)
                            .values_list("level", flat=True)
                            .first()
                            or 0
                        )
                        cost = upgrade_purchase_cost(upgrade, current_level, level)
                        if default_army.commander.gold < cost:
                            message = "Or insuffisant."
                        else:
                            default_army.commander.gold -= cost
                            default_army.commander.save(update_fields=["gold"])
                            link, _ = ArmyUpgrade.objects.get_or_create(
                                army=default_army, upgrade=upgrade, defaults={"level": 0}
                            )
                            link.level += level
                            link.save(update_fields=["level"])
                            message = (
                                f"Acheté {level} niveau(x) de {upgrade.name} pour {default_army.name} (-{cost} or)."
                            )

    commander_ready = bool(current_commander and current_commander.faction_id)
    if commander_ready and not default_army:
        default_army, created = _ensure_default_army(current_commander, request.user)
        default_army_created = default_army_created or created

    armies_owned = []
    other_armies = []
    recent_battles = []
    if commander_ready and default_army:
        armies_owned = (
            Army.objects.filter(id=default_army.id)
            .select_related("commander")
            .prefetch_related("units", "upgrades")
        )
        cooldown_since = timezone.now() - timedelta(hours=1)
        recent_vs = Battle.objects.filter(
            attacker=default_army,
            defender=OuterRef("pk"),
            status=Battle.STATUS_RESOLVED,
            resolved_at__gte=cooldown_since,
        )
        other_armies = (
            Army.objects.exclude(commander=current_commander)
            .annotate(can_attack=~Exists(recent_vs))
            .filter(can_attack=True)
            .select_related("commander")
            .order_by("-elo", "id")
        )
        other_armies = list(other_armies)
        recent_battles = (
            Battle.objects.filter(attacker__commander=current_commander)
            | Battle.objects.filter(defender__commander=current_commander)
        ).select_related("attacker", "defender", "winner")[:10]

    unit_qs = UnitType.objects.all()
    if commander_ready:
        unit_qs = unit_qs.filter(faction_id=current_commander.faction_id)
    if unit_filter:
        unit_qs = unit_qs.filter(name__icontains=unit_filter)
    upgrade_qs = Upgrade.objects.all()
    if commander_ready:
        upgrade_qs = upgrade_qs.filter(Q(faction_id__isnull=True) | Q(faction_id=current_commander.faction_id))
    if upgrade_filter:
        upgrade_qs = upgrade_qs.filter(name__icontains=upgrade_filter)

    leaderboard_armies = _army_leaderboard()
    rank_map = {army.id: (army.rank, army.badge, army.elo) for army in leaderboard_armies}
    if default_army:
        rank, badge, _ = rank_map.get(default_army.id, (None, "Bronze", default_army.elo))
        default_army.rank = rank
        default_army.badge = badge

    def max_affordable_levels(upgrade: Upgrade, current_level: int, gold: int) -> int:
        levels = 0
        acc = 0.0
        while True:
            next_cost = upgrade.cost * (1 + 0.1 * (current_level + levels))
            if acc + next_cost > gold:
                break
            acc += next_cost
            levels += 1
        return levels

    for army in armies_owned:
        army.pop_used = army_population(army)
        army.pop_cap = army.commander.pop_cap
        pop_remaining = max(0, army.pop_cap - army.pop_used)
        army.pop_remaining = pop_remaining
        army.unit_choices = [
            {
                "id": ut.id,
                "name": ut.name,
                "cost": ut.cost,
                "max_quantity": min(
                    army.commander.gold // ut.cost if ut.cost else pop_remaining,
                    pop_remaining // ut.pop_cost if ut.pop_cost else pop_remaining,
                ),
                "pop_cost": ut.pop_cost,
            }
            for ut in unit_qs
        ]
        level_map = {link.upgrade_id: link.level for link in army.upgrades.all()}
        army.upgrade_choices = [
            {
                "id": up.id,
                "name": up.name,
                "base_cost": up.cost,
                "current_level": level_map.get(up.id, 0),
                "max_level": max_affordable_levels(up, level_map.get(up.id, 0), army.commander.gold),
            }
            for up in upgrade_qs
        ]
        rank, badge, elo = rank_map.get(army.id, (None, "Bronze", army.elo))
        army.rank = rank
        army.badge = badge
        army.elo = elo
    for army in other_armies:
        rank, badge, elo = rank_map.get(army.id, (None, "Bronze", army.elo))
        army.rank = rank
        army.badge = badge
        army.elo = elo

    if default_army_created and default_army and not message:
        message = f"Armée {default_army.name} créée automatiquement pour votre compte."

    return render(
        request,
        "armies/home.html",
        {
            "commanders": Commander.objects.all().order_by("id"),
            "selected_commander": current_commander,
            "armies_owned": armies_owned,
            "other_armies": other_armies,
            "recent_battles": recent_battles,
            "unit_types": unit_qs,
            "upgrades": upgrade_qs,
            "unit_filter": unit_filter,
            "upgrade_filter": upgrade_filter,
            "message": message,
            "user_faction": current_commander.faction if current_commander else None,
            "is_authenticated": request.user.is_authenticated,
            "factions": Faction.objects.all(),
            "needs_commander": current_commander is None,
            "needs_faction_choice": bool(current_commander and not current_commander.faction_id),
            "default_commander_name": request.user.username,
            "commander_ready": commander_ready,
            "default_army": default_army,
            "leaderboard_url": "/siege/leaderboard/",
        },
    )


@login_required
def army_leaderboard(request: HttpRequest):
    armies = _army_leaderboard()
    return render(
        request,
        "armies/leaderboard.html",
        {
            "armies": armies,
        },
    )
