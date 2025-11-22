from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.contrib import messages
from .models import SiegeProfile, Battle, UNITS
import json

@login_required
def hq(request):
    profile, _ = SiegeProfile.objects.get_or_create(user=request.user)
    return render(request, 'siege/hq.html', {'profile': profile})

@login_required
def find_match(request):
    # Chercher une bataille en attente
    battle = Battle.objects.filter(status='PREPARING', defender__isnull=True).exclude(attacker=request.user).first()
    
    if battle:
        battle.defender = request.user
        battle.save()
        return redirect('siege:prepare', battle_id=battle.id)
    else:
        # Créer une nouvelle bataille
        battle = Battle.objects.create(attacker=request.user)
        return redirect('siege:prepare', battle_id=battle.id)

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
