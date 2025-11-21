import uuid
import qrcode
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

class Hunt(models.Model):
    """Une chasse au trésor (parcours)."""
    title = models.CharField("Titre", max_length=200)
    description = models.TextField("Description", blank=True)
    start_clue = models.TextField("Indice de départ", help_text="Indice pour trouver le premier QR Code")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Step(models.Model):
    """Une étape de la chasse (un QR Code à trouver)."""
    hunt = models.ForeignKey(Hunt, on_delete=models.CASCADE, related_name='steps')
    order = models.PositiveIntegerField("Ordre", default=1)
    name = models.CharField("Nom de l'étape", max_length=100, help_text="Ex: La fontaine")
    clue_text = models.TextField("Indice suivant", help_text="Indice révélé quand on scanne cette étape (pour trouver la suivante)")
    secret_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)

    class Meta:
        ordering = ['order']
        unique_together = ['hunt', 'order']

    def __str__(self):
        return f"{self.order}. {self.name} ({self.hunt.title})"

    def save(self, *args, **kwargs):
        if not self.qr_code:
            relative_path = reverse('game:scan_qr', args=[self.secret_token])
            base_url = getattr(settings, 'SITE_BASE_URL', '').rstrip('/')
            data = urljoin(f"{base_url}/", relative_path.lstrip('/')) if base_url else relative_path
            qr = qrcode.make(data)
            buffer = BytesIO()
            qr.save(buffer, format='PNG')
            filename = f"qr_{self.secret_token}.png"
            self.qr_code.save(filename, ContentFile(buffer.getvalue()), save=False)
        super().save(*args, **kwargs)

class PlayerProgress(models.Model):
    """Progression d'un joueur sur une chasse."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='progress')
    hunt = models.ForeignKey(Hunt, on_delete=models.CASCADE)
    current_step = models.ForeignKey(Step, on_delete=models.SET_NULL, null=True, blank=True, help_text="Dernière étape validée")
    total_points = models.IntegerField("Points totaux", default=0)
    completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'hunt']

    def __str__(self):
        step_name = self.current_step.name if self.current_step else "Début"
        return f"{self.user.username} - {self.hunt.title} ({step_name}) - {self.total_points} pts"

class PlayerStep(models.Model):
    """Historique des étapes validées et points gagnés."""
    progress = models.ForeignKey(PlayerProgress, on_delete=models.CASCADE, related_name='steps_history')
    step = models.ForeignKey(Step, on_delete=models.CASCADE)
    scanned_at = models.DateTimeField(auto_now_add=True)
    points_earned = models.IntegerField("Points gagnés")
    time_taken_seconds = models.IntegerField("Temps pris (s)", help_text="Temps depuis l'étape précédente")

    class Meta:
        ordering = ['scanned_at']
        unique_together = ['progress', 'step']
