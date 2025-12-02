from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("commanders/", views.commanders),
    path("armies/", views.armies),
    path("units/", views.unit_types),
    path("armies/<int:army_id>/purchase-unit/", views.purchase_unit),
    path("armies/<int:army_id>/purchase-upgrade/", views.purchase_upgrade),
    path("armies/<int:army_id>/place-unit/", views.place_unit),
    path("challenges/", views.create_challenge),
    path("armies/<int:army_id>/placement/", views.placement_data),
    path("armies/<int:army_id>/attack-presets/", views.attack_presets),
    path("battles/<int:battle_id>/", views.battle_detail),
]
