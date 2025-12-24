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
    path("npcs/<int:pk>/delete/", views.delete_npc, name="delete_npc"),
    path("characters/<int:pk>/delete/", views.delete_character, name="delete_character"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/<str:token>/", views.reset_password, name="reset_password"),
    path("characters/<int:character_id>/modify-hp/", views.modify_hp, name="modify_hp"),
    path("characters/<int:character_id>/modify-sp/", views.modify_sp, name="modify_sp"),
    path("characters/<int:character_id>/toggle-visibility/", views.toggle_character_visibility, name="toggle_character_visibility"),
    path("npcs/<int:npc_id>/toggle-visibility/", views.toggle_npc_visibility, name="toggle_npc_visibility"),
    path("characters/<int:character_id>/add-bar/", views.add_character_bar, name="add_character_bar"),
    path("bars/<int:bar_id>/modify/", views.modify_bar, name="modify_bar"),
    path("bars/<int:bar_id>/delete/", views.delete_bar, name="delete_bar"),
]
