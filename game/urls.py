from django.urls import path, re_path
from . import views

app_name = 'game'

urlpatterns = [
    path('', views.home, name='home'),
    path('hunt/<int:hunt_id>/start/', views.start_hunt, name='start_hunt'),
    path('hunt/<int:hunt_id>/play/', views.current_step, name='current_step'),
    path('hunt/<int:hunt_id>/leaderboard/', views.leaderboard, name='leaderboard'),
    path('hunt/<int:hunt_id>/pdf/', views.generate_qr_pdf, name='hunt_pdf'),
    re_path(
        r'^scan/(?P<token>[0-9a-fA-F-]{36})/name=scanQR/?$',
        views.scan_qr,
        name='scan_qr_scanapp',
    ),
    path('scan/<uuid:token>/', views.scan_qr, name='scan_qr'),
    path('signup/', views.SignUpView.as_view(), name='signup'),
]
