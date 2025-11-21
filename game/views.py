from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy, reverse
from django.views import generic
from .models import Hunt, Step, PlayerProgress, PlayerStep

class SignUpView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'

@login_required
def home(request):
    """Liste des chasses disponibles."""
    hunts = Hunt.objects.all()
    my_progress = {p.hunt_id: p for p in PlayerProgress.objects.filter(user=request.user)}
    
    context = {
        'hunts': hunts,
        'my_progress': my_progress
    }
    return render(request, 'game/home.html', context)

@login_required
def start_hunt(request, hunt_id):
    """Démarrer une chasse."""
    hunt = get_object_or_404(Hunt, pk=hunt_id)
    progress, created = PlayerProgress.objects.get_or_create(user=request.user, hunt=hunt)
    if created:
        messages.success(request, f"Chasse '{hunt.title}' démarrée ! Bonne chance.")
    return redirect('game:current_step', hunt_id=hunt.id)

@login_required
def current_step(request, hunt_id):
    """Affiche l'indice de l'étape actuelle."""
    progress = get_object_or_404(PlayerProgress, user=request.user, hunt_id=hunt_id)
    
    if progress.completed:
        return render(request, 'game/victory.html', {'progress': progress})
    
    # Si pas d'étape courante, c'est le début -> Indice de départ
    if not progress.current_step:
        clue = progress.hunt.start_clue
        step_number = 0
    else:
        clue = progress.current_step.clue_text
        step_number = progress.current_step.order
        
    return render(request, 'game/current_step.html', {
        'progress': progress,
        'clue': clue,
        'step_number': step_number
    })

@login_required
def scan_qr(request, token):
    """Traitement du scan d'un QR Code."""
    step = get_object_or_404(Step, secret_token=token)
    hunt = step.hunt
    
    # Récupérer ou créer la progression (au cas où on scanne sans avoir cliqué sur "Démarrer")
    progress, created = PlayerProgress.objects.get_or_create(user=request.user, hunt=hunt)
    
    # Vérifier si c'est la bonne étape
    if progress.current_step:
        expected_order = progress.current_step.order + 1
    else:
        expected_order = 1
        
    if step.order == expected_order:
        # C'est la bonne étape !
        
        # 1. Calcul du score
        if step.order == 1:
            points = 0
            msg_success = "Chasse démarrée ! Bonne chance."
        else:
            now = timezone.now()
            last_time = progress.updated_at
            if created:
                 last_time = progress.started_at
                 
            delta = now - last_time
            minutes_taken = delta.total_seconds() / 60.0
            
            # Formule : 100 pts à 0 min, 10 pts à 120 min (2h)
            points = max(10, int(100 - (minutes_taken * 0.75)))
            msg_success = f"Étape validée ! +{points} points. Voici l'indice suivant."
        
        # 2. Enregistrer l'étape et les points
        PlayerStep.objects.create(
            progress=progress,
            step=step,
            points_earned=points,
            time_taken_seconds=0 if step.order == 1 else int((timezone.now() - progress.updated_at).total_seconds())
        )
        
        # 3. Mettre à jour la progression
        progress.current_step = step
        progress.total_points += points
        
        # Vérifier si c'est la fin
        next_step_exists = hunt.steps.filter(order=step.order + 1).exists()
        if not next_step_exists:
            progress.completed = True
            messages.success(request, f"Bravo ! Vous avez terminé la chasse avec {points} points pour cette étape.")
        else:
            messages.success(request, msg_success)
            
        progress.save()
        
        return redirect('game:current_step', hunt_id=hunt.id)
        
    elif step.order <= (progress.current_step.order if progress.current_step else 0):
        messages.info(request, "Vous avez déjà validé cette étape.")
        return redirect('game:current_step', hunt_id=hunt.id)
    else:
        messages.warning(request, "Ce n'est pas l'étape attendue ! Cherchez encore.")
        return redirect('game:current_step', hunt_id=hunt.id)

@login_required
def leaderboard(request, hunt_id):
    """Classement des joueurs."""
    hunt = get_object_or_404(Hunt, pk=hunt_id)
    ranking = PlayerProgress.objects.filter(hunt=hunt).order_by('-total_points', 'updated_at')
    
    return render(request, 'game/leaderboard.html', {
        'hunt': hunt,
        'ranking': ranking
    })

@user_passes_test(lambda u: u.is_staff)
def generate_qr_pdf(request, hunt_id):
    """Génère un PDF avec les QR Codes de la chasse."""
    hunt = get_object_or_404(Hunt, pk=hunt_id)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="qr_codes_{hunt.title}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    
    # Titre
    p.setFont("Helvetica-Bold", 24)
    p.drawString(2*cm, height - 3*cm, f"Chasse : {hunt.title}")
    p.setFont("Helvetica", 12)
    p.drawString(2*cm, height - 4*cm, f"Généré le {timezone.now().strftime('%d/%m/%Y')}")
    
    y_position = height - 7*cm
    x_position = 2*cm
    
    steps = hunt.steps.all().order_by('order')
    
    for step in steps:
        if not step.qr_code:
            continue
            
        # Dessiner le cadre
        p.rect(x_position, y_position, 8*cm, 10*cm)
        
        # Titre de l'étape
        p.setFont("Helvetica-Bold", 16)
        p.drawString(x_position + 0.5*cm, y_position + 9*cm, f"Étape {step.order}")
        p.setFont("Helvetica", 12)
        p.drawString(x_position + 0.5*cm, y_position + 8.5*cm, step.name)
        
        # Image QR Code
        try:
            p.drawImage(step.qr_code.path, x_position + 1*cm, y_position + 2*cm, width=6*cm, height=6*cm)
        except Exception as e:
            p.drawString(x_position + 1*cm, y_position + 5*cm, "Erreur image")
            
        # Token (au cas où)
        p.setFont("Helvetica", 8)
        p.drawString(x_position + 0.5*cm, y_position + 1*cm, str(step.secret_token))
        
        # Gestion de la grille (2 colonnes, 2 lignes par page)
        x_position += 9*cm
        if x_position > width - 9*cm:
            x_position = 2*cm
            y_position -= 11*cm
            
        if y_position < 2*cm:
            p.showPage()
            y_position = height - 7*cm
            x_position = 2*cm
            
    p.showPage()
    p.save()
    return response

def custom_page_not_found_view(request, exception):
    """Vue personnalisée pour les erreurs 404 qui redirige vers l'accueil."""
    return HttpResponseRedirect(reverse('game:home'))
