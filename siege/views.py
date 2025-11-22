from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.contrib import messages
from .models import SiegeProfile, Battle, UNITS
import json

from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User
from django.db.models import Q

@login_required
def hq(request):
    profile, _ = SiegeProfile.objects.get_or_create(user=request.user)
    
    # Auto-resolve pending battles older than 1 hour
    one_hour_ago = timezone.now() - timedelta(hours=1)
    pending_battles = Battle.objects.filter(
        defender=request.user,
        status='PREPARING',
        created_at__lt=one_hour_ago
    )
    
    for battle in pending_battles:
        auto_resolve_battle(battle)
        
    # Fetch active challenges
    challenges = Battle.objects.filter(
        defender=request.user,
        status='PREPARING'
    ).order_by('-created_at')
    
    return render(request, 'siege/hq.html', {
        'profile': profile,
        'challenges': challenges,
        'units': UNITS
    })

@login_required
def refuse_battle(request, battle_id):
    battle = get_object_or_404(Battle, pk=battle_id, defender=request.user, status='PREPARING')
    profile = request.user.siege_profile
    
    today = timezone.now().date()
    if profile.last_refusal_date != today:
        profile.refusals_today = 0
        profile.last_refusal_date = today
        
    if profile.refusals_today >= 3:
        messages.error(request, "Vous avez déjà refusé 3 combats aujourd'hui. Vous devez vous battre !")
        return redirect('siege:hq')
        
    profile.refusals_today += 1
    profile.save()
    
    battle.delete() # Or set status to CANCELLED
    messages.success(request, "Combat refusé avec succès.")
    return redirect('siege:hq')

@login_required
@require_POST
def save_default_army(request):
    profile = request.user.siege_profile
    try:
        data = json.loads(request.body)
        units_selected = data.get('units', {})
        
        # Validate cost
        total_cost = 0
        for unit_key, count in units_selected.items():
            if unit_key in UNITS:
                total_cost += UNITS[unit_key]['cost'] * int(count)
                
        if total_cost > profile.gold:
             return JsonResponse({'status': 'error', 'message': 'Coût supérieur à votre or actuel !'}, status=400)

        profile.default_army = units_selected
        profile.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def auto_resolve_battle(battle):
    defender_profile = battle.defender.siege_profile
    
    # Use default army or random
    if defender_profile.default_army:
        # Verify if they still have enough gold, otherwise scale down? 
        # For simplicity, we assume they spend gold NOW.
        # But wait, gold is deducted at submit_army. 
        # So we need to deduct gold here too.
        
        # Simple logic: try to buy default army
        cost = 0
        army = defender_profile.default_army
        for u, c in army.items():
            cost += UNITS[u]['cost'] * c
            
        if defender_profile.gold >= cost:
            defender_profile.gold -= cost
            defender_profile.save()
            battle.defender_units = army
        else:
            # Not enough gold for default, buy nothing (or random logic could go here)
            battle.defender_units = {} 
    else:
        # No default army, buy nothing (easy win for attacker)
        battle.defender_units = {}
        
    battle.status = 'FIGHTING'
    battle.save()
    # Resolution will happen when someone views the battle state or we can trigger it now
    # Let's trigger resolution logic immediately if we want, but battle_state view handles it.
    # To be safe, let's leave it to battle_state or call resolve_battle here.
    # But resolve_battle is not imported or is below. 
    # Let's just set status to FIGHTING, the next poll will resolve it.


@login_required
def select_opponent(request):
    # Exclure soi-même et les superusers si besoin
    users = User.objects.exclude(id=request.user.id).select_related('siege_profile')
    return render(request, 'siege/select_opponent.html', {'users': users})

@login_required
def create_challenge(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    
    if target_user == request.user:
        messages.error(request, "Vous ne pouvez pas vous attaquer vous-même !")
        return redirect('siege:select_opponent')

    # Vérification des contraintes
    now = timezone.now()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)
    
    # 1. Max 1 fois par heure
    recent_battles = Battle.objects.filter(
        attacker=request.user,
        defender=target_user,
        created_at__gte=one_hour_ago
    )
    if recent_battles.exists():
        messages.warning(request, f"Vous avez déjà attaqué {target_user.username} il y a moins d'une heure. Reposez vos troupes !")
        return redirect('siege:select_opponent')
        
    # 2. Max 3 fois par jour
    daily_battles = Battle.objects.filter(
        attacker=request.user,
        defender=target_user,
        created_at__gte=one_day_ago
    ).count()
    
    if daily_battles >= 3:
        messages.warning(request, f"Vous avez atteint la limite de 3 attaques par jour contre {target_user.username}.")
        return redirect('siege:select_opponent')

    # Création de la bataille
    battle = Battle.objects.create(attacker=request.user, defender=target_user)
    messages.success(request, f"À l'attaque ! Vous défiez {target_user.username} !")
    return redirect('siege:prepare', battle_id=battle.id)

@login_required
def find_match(request):
    # Chercher une bataille en attente (ancienne méthode, gardée pour compatibilité ou "Partie Rapide")
    battle = Battle.objects.filter(status='PREPARING', defender__isnull=True).exclude(attacker=request.user).first()
    
    if battle:
        battle.defender = request.user
        battle.save()
        return redirect('siege:prepare', battle_id=battle.id)
    else:
        # Rediriger vers la sélection d'adversaire par défaut maintenant
        return redirect('siege:select_opponent')


@login_required
def prepare_battle(request, battle_id):
    battle = get_object_or_404(Battle, pk=battle_id)
    profile, _ = SiegeProfile.objects.get_or_create(user=request.user)
    
    # Vérifier si l'utilisateur fait partie de la bataille
    if request.user != battle.attacker and request.user != battle.defender:
        messages.error(request, "Vous ne faites pas partie de cette bataille.")
        return redirect('siege:hq')
        
    # Si déjà prêt, aller à la salle de combat
    if request.user == battle.attacker and battle.attacker_units:
        return redirect('siege:room', battle_id=battle.id)
    if request.user == battle.defender and battle.defender_units:
        return redirect('siege:room', battle_id=battle.id)

    return render(request, 'siege/prepare.html', {
        'battle': battle,
        'profile': profile,
        'units': UNITS
    })

@login_required
@require_POST
def submit_army(request, battle_id):
    battle = get_object_or_404(Battle, pk=battle_id)
    profile = get_object_or_404(SiegeProfile, user=request.user)
    
    try:
        data = json.loads(request.body)
        units_selected = data.get('units', {})
        
        # Calculer le coût total
        total_cost = 0
        for unit_key, count in units_selected.items():
            if unit_key in UNITS:
                total_cost += UNITS[unit_key]['cost'] * int(count)
        
        if total_cost > profile.gold:
            return JsonResponse({'status': 'error', 'message': 'Pas assez d\'or !'}, status=400)
            
        # Sauvegarder l'armée et déduire l'or
        with transaction.atomic():
            profile.gold -= total_cost
            profile.save()
            
            if request.user == battle.attacker:
                battle.attacker_units = units_selected
            elif request.user == battle.defender:
                battle.defender_units = units_selected
            
            battle.save()
            
            # Si les deux ont choisi, passer en combat
            if battle.attacker_units and battle.defender_units:
                battle.status = 'FIGHTING'
                battle.save()
                
        return JsonResponse({'status': 'ok'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def battle_room(request, battle_id):
    battle = get_object_or_404(Battle, pk=battle_id)
    return render(request, 'siege/room.html', {'battle': battle, 'units_config': UNITS})

@login_required
def battle_state(request, battle_id):
    battle = get_object_or_404(Battle, pk=battle_id)
    
    # Résolution du combat si nécessaire
    if battle.status == 'FIGHTING' and not battle.winner:
        resolve_battle(battle)
    
    return JsonResponse({
        'status': battle.status,
        'attacker': battle.attacker.username,
        'defender': battle.defender.username if battle.defender else None,
        'attacker_units': battle.attacker_units,
        'defender_units': battle.defender_units,
        'winner': battle.winner.username if battle.winner else None
    })

def resolve_battle(battle):
    # Calcul de la puissance totale
    attacker_power = sum(UNITS[u]['power'] * c for u, c in battle.attacker_units.items())
    defender_power = sum(UNITS[u]['power'] * c for u, c in battle.defender_units.items())
    
    if attacker_power > defender_power:
        battle.winner = battle.attacker
        # Récompense
        attacker_profile = SiegeProfile.objects.get(user=battle.attacker)
        attacker_profile.gold += 50 # Gain de victoire
        attacker_profile.wins += 1
        attacker_profile.save()
        
        if battle.defender:
            defender_profile = SiegeProfile.objects.get(user=battle.defender)
            defender_profile.gold += 10 # Lot de consolation
            defender_profile.losses += 1
            defender_profile.save()
            
    elif defender_power > attacker_power:
        battle.winner = battle.defender
        if battle.defender:
            defender_profile = SiegeProfile.objects.get(user=battle.defender)
            defender_profile.gold += 50
            defender_profile.wins += 1
            defender_profile.save()
            
        attacker_profile = SiegeProfile.objects.get(user=battle.attacker)
        attacker_profile.gold += 10
        attacker_profile.losses += 1
        attacker_profile.save()
    else:
        # Égalité (pas de vainqueur, mais petit gain pour les deux)
        attacker_profile = SiegeProfile.objects.get(user=battle.attacker)
        attacker_profile.gold += 20
        attacker_profile.save()
        if battle.defender:
            defender_profile = SiegeProfile.objects.get(user=battle.defender)
            defender_profile.gold += 20
            defender_profile.save()
            
    battle.status = 'FINISHED'
    battle.save()
