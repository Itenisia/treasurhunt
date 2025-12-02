from django.contrib import admin
from .models import Hunt, Step, PlayerProgress

class StepInline(admin.TabularInline):
    model = Step
    extra = 1
    readonly_fields = ('qr_code_preview',)

    def qr_code_preview(self, obj):
        from django.utils.html import mark_safe
        if obj.qr_code:
            return mark_safe(f'<img src="{obj.qr_code.url}" width="100" height="100" />')
        return "-"

@admin.register(Hunt)
class HuntAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at')
    inlines = [StepInline]
    actions = ['download_qr_codes']

    @admin.action(description='Télécharger les QR Codes (PDF)')
    def download_qr_codes(self, request, queryset):
        from django.shortcuts import redirect
        from django.urls import reverse
        
        if queryset.count() != 1:
            self.message_user(request, "Veuillez sélectionner une seule chasse à la fois.", level='warning')
            return
            
        hunt = queryset.first()
        return redirect(reverse('game:hunt_pdf', args=[hunt.id]))

@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = ('order', 'name', 'hunt', 'secret_token')
    list_filter = ('hunt',)
    readonly_fields = ('secret_token', 'qr_code')

@admin.register(PlayerProgress)
class PlayerProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'hunt', 'current_step', 'completed', 'updated_at')
    list_filter = ('hunt', 'completed')
