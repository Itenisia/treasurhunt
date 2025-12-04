from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import random
from collections import deque

from django.db import ProgrammingError

from .models import Army, ArmyUnit, UnitType


# Multipliers tirés du modèle WC3 (The Frozen Throne)
ATTACK_ARMOR_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "normal": {
        "unarmored": 1.0,
        "light": 1.0,
        "medium": 1.5,
        "heavy": 1.0,
        "fortified": 0.7,
        "hero": 1.0,
        "divine": 1.0,
    },
    "piercing": {
        "unarmored": 1.5,
        "light": 2.0,
        "medium": 0.75,
        "heavy": 1.0,
        "fortified": 0.35,
        "hero": 0.5,
        "divine": 1.0,
    },
    "siege": {
        "unarmored": 1.5,
        "light": 1.0,
        "medium": 1.0,
        "heavy": 1.0,
        "fortified": 1.5,
        "hero": 0.5,
        "divine": 1.0,
    },
    "magic": {
        "unarmored": 1.0,
        "light": 1.25,
        "medium": 0.75,
        "heavy": 2.0,
        "fortified": 0.35,
        "hero": 1.0,
        "divine": 0.0,
    },
    "hero": {
        "unarmored": 1.0,
        "light": 1.0,
        "medium": 1.0,
        "heavy": 1.0,
        "fortified": 0.5,
        "hero": 1.0,
        "divine": 1.0,
    },
    "chaos": {
        "unarmored": 1.0,
        "light": 1.0,
        "medium": 1.0,
        "heavy": 1.0,
        "fortified": 1.0,
        "hero": 1.0,
        "divine": 1.0,
    },
    "spells": {
        "unarmored": 1.0,
        "light": 1.0,
        "medium": 1.0,
        "heavy": 1.0,
        "fortified": 0.7,
        "hero": 0.7,
        "divine": 0.0,
    },
}


def _attack_vs_armor_multiplier(attack_type: str, armor_type: str) -> float:
    atk = (attack_type or "").lower()
    arm = (armor_type or "").lower()
    table = ATTACK_ARMOR_MULTIPLIERS.get(atk, {})
    return table.get(arm, 1.0)


def _armor_multiplier(armor: float) -> float:
    # Warcraft III: 0.06 per point, supports negative armor (bonus dégâts)
    return 1 - (0.06 * armor) / (1 + 0.06 * abs(armor))


@dataclass
class StackState:
    stack_id: int
    army_unit_id: Optional[int]
    army_id: int
    army_name: str
    unit_name: str
    attack: float
    defense: float
    health: float
    current_hp: float
    speed: float  # legacy
    attack_speed: float
    move_speed: float
    range: int
    damage_min: float
    damage_max: float
    attack_type: str
    armor_type: str
    crit_chance: float
    crit_multiplier: float
    dodge_chance: float
    aoe_radius: int
    position_x: Optional[int]
    position_y: Optional[int]
    attack_meter: float = 0.0
    alive: bool = True
    residual_hp: float = 0.0  # legacy, unused but kept for compatibility


def _upgrade_bonus_for_army(army: Army) -> Dict[object, Dict[str, float]]:
    bonuses: Dict[object, Dict[str, float]] = {"all": {"attack": 0, "defense": 0, "health": 0, "speed": 0}}
    for link in army.upgrades.select_related("upgrade", "upgrade__unit_type").prefetch_related("upgrade__unit_types"):
        upgrade = link.upgrade
        try:
            targets = {ut.id for ut in upgrade.unit_types.all()}
        except ProgrammingError:
            targets = set()
        if upgrade.unit_type_id:
            targets.add(upgrade.unit_type_id)
        if not targets:
            targets = {"all"}
        attack_pct_value = getattr(upgrade, "attack_bonus_pct", 0.0) or 0.0
        for target in targets:
            bonus = bonuses.setdefault(target, {"attack": 0, "defense": 0, "health": 0, "speed": 0, "attack_pct": 0.0})
            bonus["attack"] += upgrade.attack_bonus * link.level
            bonus["attack_pct"] += attack_pct_value * link.level
            bonus["defense"] += upgrade.defense_bonus * link.level
            bonus["health"] += upgrade.health_bonus * link.level
            bonus["speed"] += upgrade.speed_bonus * link.level
    return bonuses


def build_stack_states(army: Army, positions_override: Optional[Dict[int, Tuple[int, int]]] = None) -> List[StackState]:
    bonuses = _upgrade_bonus_for_army(army)
    global_bonus = bonuses.get("all", {})
    stacks: List[StackState] = []
    for stack in army.units.select_related("unit_type"):
        type_bonus = bonuses.get(stack.unit_type_id, {})
        ut = stack.unit_type
        attack_flat = global_bonus.get("attack", 0) + type_bonus.get("attack", 0)
        attack_pct = global_bonus.get("attack_pct", 0.0) + type_bonus.get("attack_pct", 0.0)
        defense = ut.defense + global_bonus.get("defense", 0) + type_bonus.get("defense", 0)
        health = ut.health + global_bonus.get("health", 0) + type_bonus.get("health", 0)
        speed = ut.speed + global_bonus.get("speed", 0) + type_bonus.get("speed", 0)
        dmg_min = ut.damage_min * (1 + attack_pct) + attack_flat
        dmg_max = ut.damage_max * (1 + attack_pct) + attack_flat
        stacks.append(
            StackState(
                stack_id=stack.id,
                army_id=army.id,
                army_unit_id=stack.id,
                army_name=army.name,
                unit_name=stack.unit_type.name,
                attack=(dmg_min + dmg_max) / 2,
                defense=defense,
                health=health,
                current_hp=health,
                speed=speed,
                attack_speed=min(4.0, ut.attack_speed),
                move_speed=ut.move_speed,
                range=ut.range,
                damage_min=dmg_min,
                damage_max=dmg_max,
                attack_type=ut.attack_type or "normal",
                armor_type=ut.armor_type or "unarmored",
                crit_chance=min(0.5, ut.crit_chance),
                crit_multiplier=ut.crit_multiplier,
                dodge_chance=min(0.5, ut.dodge_chance),
                aoe_radius=ut.aoe_radius,
                position_x=positions_override.get(stack.id, (stack.position_x, stack.position_y))[0]
                if positions_override
                else stack.position_x,
                position_y=positions_override.get(stack.id, (stack.position_x, stack.position_y))[1]
                if positions_override
                else stack.position_y,
            )
        )
    return stacks


def army_value(army: Army) -> int:
    """Estime la valeur d'une armée (coût des unités + upgrades appliquées)."""
    units_value = sum(
        stack.unit_type.cost for stack in army.units.select_related("unit_type")
    )
    upgrades_value = sum(
        link.level * link.upgrade.cost for link in army.upgrades.select_related("upgrade")
    )
    return int(units_value + upgrades_value)


def army_population(army: Army) -> int:
    """Total de population utilisée par une armée."""
    return sum(
        unit.unit_type.pop_cost for unit in army.units.select_related("unit_type")
    )


def upgrade_purchase_cost(upgrade, current_level: int, levels_to_add: int) -> int:
    """
    Calcule le coût total pour acheter `levels_to_add` niveaux supplémentaires.
    Chaque niveau coûte +10% du coût de base par niveau déjà acquis.
    Ex : coût du 10e niveau ~= 2x le coût de base.
    """
    base = upgrade.cost
    total = 0.0
    for i in range(levels_to_add):
        total += base * (1 + 0.1 * (current_level + i))
    return int(round(total))


def _position_defense_bonus(stack: StackState) -> float:
    if stack.position_y is None:
        return 0.0
    if stack.position_y <= 1:
        return 0.08
    if stack.position_y <= 3:
        return 0.04
    return 0.0


def _distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _neighbors(x: int, y: int) -> List[Tuple[int, int]]:
    coords = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < 10 and 0 <= ny < 10:
                coords.append((nx, ny))
    return coords


def _find_target(stack: StackState, enemies: List[StackState], in_range_only: bool = False) -> Optional[StackState]:
    in_range = []
    for e in enemies:
        if not e.alive or e.position_x is None or e.position_y is None:
            continue
        dist = _distance((stack.position_x, stack.position_y), (e.position_x, e.position_y))
        if dist <= stack.range:
            in_range.append((dist, e))
    if in_range:
        in_range.sort(key=lambda t: t[0])
        return in_range[0][1]
    if in_range_only:
        return None
    # otherwise pick closest overall
    candidates = []
    for e in enemies:
        if not e.alive or e.position_x is None or e.position_y is None:
            continue
        dist = _distance((stack.position_x, stack.position_y), (e.position_x, e.position_y))
        candidates.append((dist, e))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def _grid_occupancy(allies: List[StackState], enemies: List[StackState]) -> Dict[Tuple[int, int], str]:
    occ = {}
    for s in allies:
        if s.alive and s.position_x is not None and s.position_y is not None:
            occ[(s.position_x, s.position_y)] = "ally"
    for s in enemies:
        if s.alive and s.position_x is not None and s.position_y is not None:
            occ[(s.position_x, s.position_y)] = "enemy"
    return occ


def _random_place(stacks: List[StackState], allowed_cols: List[int]):
    # place randomly in allowed columns (rows 0-9)
    import random

    occupied = set((s.position_x, s.position_y) for s in stacks if s.position_x is not None and s.position_y is not None)
    for s in stacks:
        if s.position_x is not None and s.position_y is not None:
            continue
        tries = [(x, y) for x in allowed_cols for y in range(10)]
        random.shuffle(tries)
        for coord in tries:
            if coord not in occupied:
                s.position_x, s.position_y = coord
                occupied.add(coord)
                break


def _bfs_next_step(start: Tuple[int, int], goal: Tuple[int, int], occ: Dict[Tuple[int, int], str]) -> Optional[Tuple[int, int]]:
    if start == goal:
        return goal
    q = deque()
    q.append(start)
    seen = {start: None}
    while q:
        cx, cy = q.popleft()
        for nx, ny in _neighbors(cx, cy):
            if (nx, ny) in seen:
                continue
            if (nx, ny) in occ and (nx, ny) != goal:
                continue
            seen[(nx, ny)] = (cx, cy)
            if (nx, ny) == goal:
                # reconstruct first step
                step = (nx, ny)
                while seen[step] != start and seen[step] is not None:
                    step = seen[step]
                return step
            q.append((nx, ny))
    return None


def _try_move(stack: StackState, enemies: List[StackState], allies: List[StackState], occ: Dict[Tuple[int, int], str], events: List[Dict], t: int, side: str):
    target = _find_target(stack, enemies, in_range_only=False)
    if not target or target.position_x is None or target.position_y is None:
        return False
    dist = _distance((stack.position_x, stack.position_y), (target.position_x, target.position_y))
    if dist <= stack.range:
        return False  # already in range
    # find closest empty cell toward target
    target_pos = (target.position_x, target.position_y)
    # choose goal among neighbors of target within range
    goals = []
    for nx, ny in _neighbors(target_pos[0], target_pos[1]) + [target_pos]:
        if (nx, ny) in occ:
            continue
        goals.append((nx, ny))
    goals.sort(key=lambda c: _distance((stack.position_x, stack.position_y), c))
    next_step = None
    for cell in goals:
        candidate = _bfs_next_step((stack.position_x, stack.position_y), cell, occ)
        if candidate:
            next_step = candidate
            break
    if next_step:
        prev = (stack.position_x, stack.position_y)
        occ.pop((stack.position_x, stack.position_y), None)
        stack.position_x, stack.position_y = next_step
        occ[next_step] = "ally"
        events.append(
            {
                "t": t,
                "type": "move",
                "unit_id": stack.stack_id,
                "unit_name": stack.unit_name,
                "side": side,
                "from": {"x": prev[0], "y": prev[1]},
                "to": {"x": next_step[0], "y": next_step[1]},
            }
        )
        return True
    return False


def _apply_damage(target: StackState, dmg: float) -> Dict[str, float]:
    prev_pos = (target.position_x, target.position_y)
    prev_hp = target.current_hp
    remaining = max(0.0, target.current_hp - dmg)
    target.current_hp = remaining
    killed = False
    if remaining <= 0:
        target.alive = False
        target.position_x = None
        target.position_y = None
        killed = True
    return {
        "killed": killed,
        "remaining_hp": remaining,
        "last_unit_hp": remaining,
        "prev_pos": prev_pos,
        "taken": min(prev_hp, dmg),
    }


def _perform_attack(attacker: StackState, defenders: List[StackState], occ: Dict[Tuple[int, int], str], events: List[Dict], t: int, side: str):
    target = _find_target(attacker, defenders, in_range_only=True)
    if not target:
        return
    if target.position_x is None or target.position_y is None:
        return
    dmg_roll = random.uniform(attacker.damage_min, attacker.damage_max)
    crit = random.random() < attacker.crit_chance
    if crit:
        dmg_roll *= attacker.crit_multiplier

    impacted = []
    targets = [target]
    if attacker.aoe_radius > 0:
        for other in defenders:
            if not other.alive or other == target:
                continue
            if other.position_x is None or other.position_y is None:
                continue
            if _distance((target.position_x, target.position_y), (other.position_x, other.position_y)) <= attacker.aoe_radius:
                targets.append(other)

    for tgt in targets:
        if random.random() < tgt.dodge_chance:
            impacted.append(
                {
                    "defender": tgt.unit_name,
                    "defender_id": tgt.stack_id,
                    "killed": False,
                    "remaining": tgt.alive,
                    "last_unit_hp": round(tgt.current_hp, 2),
                    "crit": False,
                    "dodge": True,
                    "dmg": 0.0,
                }
            )
            continue

        dmg = dmg_roll
        dmg *= _attack_vs_armor_multiplier(attacker.attack_type, tgt.armor_type)
        dmg *= _armor_multiplier(tgt.defense)
        dmg = max(0.0, dmg)

        result = _apply_damage(tgt, dmg)
        impacted.append(
            {
                "defender": tgt.unit_name,
                "defender_id": tgt.stack_id,
                "killed": result["killed"],
                "remaining": tgt.alive,
                "last_unit_hp": round(result.get("last_unit_hp", 0), 2),
                "crit": crit,
                "dodge": False,
                "dmg": round(dmg, 2),
            }
        )
        if not tgt.alive:
            prev_pos = result.get("prev_pos")
            if prev_pos:
                occ.pop(prev_pos, None)

    events.append(
        {
            "t": t,
            "type": "attack",
            "attacker": attacker.unit_name,
            "attacker_id": attacker.stack_id,
            "attacker_side": side,
            "targets": impacted,
            "crit": crit,
        }
    )


def simulate_battle(attacker: Army, defender: Army, max_rounds: int = 60) -> Dict:
    attacker_preset = (
        attacker.attack_presets.filter(name="__auto__").order_by("-created_at").first()
    )
    override = {}
    if attacker_preset:
        for p in attacker_preset.positions:
            if p.get("army_unit_id") is not None:
                override[int(p["army_unit_id"])] = (p.get("x"), p.get("y"))

    attacker_stacks = build_stack_states(attacker, positions_override=override)
    defender_stacks = build_stack_states(defender)
    # auto-place missing positions
    _random_place(attacker_stacks, allowed_cols=[0, 1])
    _random_place(defender_stacks, allowed_cols=[8, 9])
    events: List[Dict] = []
    initial_positions = {
        "attacker": [
            {
                "id": s.stack_id,
                "unit_name": s.unit_name,
                "hp": s.current_hp,
                "x": s.position_x,
                "y": s.position_y,
                "range": s.range,
                "army_unit_id": s.army_unit_id,
            }
            for s_idx, s in enumerate(attacker_stacks)
        ],
        "defender": [
            {
                "id": s.stack_id,
                "unit_name": s.unit_name,
                "hp": s.current_hp,
                "x": s.position_x,
                "y": s.position_y,
                "range": s.range,
                "army_unit_id": s.army_unit_id,
            }
            for s_idx, s in enumerate(defender_stacks)
        ],
    }
    # ensure positions default to defense for defender; attacker may have positions set (attack preset)
    for s in attacker_stacks + defender_stacks:
        if s.position_x is None or s.position_y is None:
            # spawn in reserve if no position, keep None
            s.position_x = s.position_x
    last_t = 0
    for t in range(1, max_rounds + 1):
        last_t = t
        if not any(s.alive for s in attacker_stacks) or not any(s.alive for s in defender_stacks):
            break
        occ_att = _grid_occupancy(attacker_stacks, defender_stacks)
        occ_def = _grid_occupancy(defender_stacks, attacker_stacks)
        # movement phase
        for stack in attacker_stacks:
            if not stack.alive or stack.position_x is None or stack.position_y is None:
                continue
            steps = int(stack.move_speed)
            frac = stack.move_speed - steps
            for _ in range(steps):
                _try_move(stack, defender_stacks, attacker_stacks, occ_att, events, t, "attacker")
            if random.random() < frac:
                _try_move(stack, defender_stacks, attacker_stacks, occ_att, events, t, "attacker")
        for stack in defender_stacks:
            if not stack.alive or stack.position_x is None or stack.position_y is None:
                continue
            steps = int(stack.move_speed)
            frac = stack.move_speed - steps
            for _ in range(steps):
                _try_move(stack, attacker_stacks, defender_stacks, occ_def, events, t, "defender")
            if random.random() < frac:
                _try_move(stack, attacker_stacks, defender_stacks, occ_def, events, t, "defender")

        # attack phase
        for side, foes, occ, label in [
            (attacker_stacks, defender_stacks, occ_att, "attacker"),
            (defender_stacks, attacker_stacks, occ_def, "defender"),
        ]:
            for stack in side:
                if not stack.alive or stack.position_x is None or stack.position_y is None:
                    continue
                stack.attack_meter = min(4.0, stack.attack_meter + stack.attack_speed)
                attacks = int(stack.attack_meter)
                stack.attack_meter -= attacks
                for _ in range(attacks):
                    if not any(e.alive for e in foes):
                        break
                    _perform_attack(stack, foes, occ, events, t, label)
        events.append(
            {
                "t": t,
                "type": "status",
                "attacker_alive": sum(1 for s in attacker_stacks if s.alive),
                "defender_alive": sum(1 for s in defender_stacks if s.alive),
            }
        )

    atk_alive = sum(1 for s in attacker_stacks if s.alive)
    def_alive = sum(1 for s in defender_stacks if s.alive)
    if atk_alive <= 0 and def_alive <= 0:
        winner = None
    elif def_alive <= 0:
        winner = "attacker"
    elif atk_alive <= 0:
        winner = "defender"
    else:
        winner = "attacker" if atk_alive > def_alive else "defender"

    return {
        "winner": winner,
        "rounds": last_t,
        "log": events,
        "attacker_remaining": atk_alive,
        "defender_remaining": def_alive,
        "initial_positions": initial_positions,
    }
