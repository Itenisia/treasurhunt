from django.urls import path
from . import views

app_name = 'siege'

urlpatterns = [
    path('hq/', views.hq, name='hq'),
    path('refuse/<int:battle_id>/', views.refuse_battle, name='refuse'),
    path('api/save_default/', views.save_default_army, name='save_default'),
    path('select/', views.select_opponent, name='select_opponent'),
    path('challenge/<int:user_id>/', views.create_challenge, name='create_challenge'),
    path('find_match/', views.find_match, name='find_match'),
    path('prepare/<int:battle_id>/', views.prepare_battle, name='prepare'),
    path('api/submit_army/<int:battle_id>/', views.submit_army, name='submit_army'),
    path('room/<int:battle_id>/', views.battle_room, name='room'),
    path('api/state/<int:battle_id>/', views.battle_state, name='state'),
]
