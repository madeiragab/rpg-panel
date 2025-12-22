from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("master/", views.master_dashboard, name="master_dashboard"),
    path("player/", views.player_dashboard, name="player_dashboard"),
    path("campaigns/<int:pk>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<int:pk>/search_players/", views.search_players, name="search_players"),
    path("characters/", views.character_list, name="character_list"),
    path("characters/<int:pk>/", views.character_detail, name="character_detail"),
    path(
        "characters/<int:character_id>/slots/<int:slot_id>/assign/",
        views.assign_slot,
        name="assign_slot",
    ),
    path("register/", views.register, name="register"),
    path("me/", views.user_page, name="user_page"),
    path("items/<int:pk>/delete/", views.delete_item, name="delete_item"),
    path("characters/<int:pk>/delete/", views.delete_character, name="delete_character"),
]
