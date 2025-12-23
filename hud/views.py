from __future__ import annotations

from typing import Any
import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q
from .forms import RegistrationForm, ProfileEditForm, ForgotPasswordForm, ResetPasswordForm
from .models import UserProfile, PasswordResetToken


def _mask_email(email: str) -> str:
    """Mascara parte local do email (ex.: anji****@gmail.com)."""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*" * max(len(local) - 1, 1)
    elif len(local) <= 4:
        masked_local = local[:2] + "*" * (len(local) - 2)
    else:
        masked_local = local[:3] + "*" * (len(local) - 3)
    return f"{masked_local}@{domain}"

from .forms import (
    CampaignForm,
    CharacterAbilityForm,
    CharacterForm,
    CharacterSkillForm,
    ItemForm,
)
from .models import Campaign, Character, InventorySlot, Item, UserProfile, CharacterBar


def forgot_password(request: HttpRequest) -> HttpResponse:
    """Solicita reset de senha por username"""
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            try:
                user = User.objects.get(username=username)
                # Gera token único
                token = secrets.token_urlsafe(32)
                # Token expira em 24 horas
                expires_at = timezone.now() + timedelta(hours=24)
                
                # Cria registro do token
                PasswordResetToken.objects.create(
                    user=user,
                    token=token,
                    expires_at=expires_at
                )
                
                # Envia email
                reset_url = request.build_absolute_uri(f"/reset-password/{token}/")
                send_mail(
                    subject="Recuperar sua senha - Painel RPG HUD",
                    message=f"Olá {user.username},\n\nClique no link abaixo para resetar sua senha:\n\n{reset_url}\n\nEste link expira em 24 horas.",
                    from_email="noreply@rpg-panel.com",
                    recipient_list=[user.email],
                )
                
                # Mostra email mascarado
                masked_email = _mask_email(user.email)
                return render(request, "registration/forgot_password_sent.html", {
                    "email": masked_email
                })
            except User.DoesNotExist:
                messages.error(request, "Usuário não encontrado.")
    else:
        form = ForgotPasswordForm()
    
    return render(request, "registration/forgot_password.html", {"form": form})


def reset_password(request: HttpRequest, token: str) -> HttpResponse:
    """Reseta a senha com token válido"""
    try:
        reset_token = PasswordResetToken.objects.get(token=token)
    except PasswordResetToken.DoesNotExist:
        messages.error(request, "Token inválido ou expirado.")
        return redirect("login")
    
    # Verifica se token expirou
    if reset_token.expires_at < timezone.now():
        messages.error(request, "Token expirado. Solicite um novo reset de senha.")
        return redirect("forgot_password")
    
    # Verifica se já foi usado
    if reset_token.used:
        messages.error(request, "Este token já foi utilizado.")
        return redirect("login")
    
    if request.method == "POST":
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            password = form.cleaned_data["password"]
            reset_token.user.set_password(password)
            reset_token.user.save()
            
            # Marca token como usado
            reset_token.used = True
            reset_token.save()
            
            messages.success(request, "Senha alterada com sucesso! Faça login com sua nova senha.")
            return redirect("login")
    else:
        form = ResetPasswordForm()
    
    return render(request, "registration/reset_password.html", {
        "form": form,
        "token": token
    })
def _user_is_master(user) -> bool:  # noqa: ANN001
    """Legado: mantido por compatibilidade com templates antigas"""
    return True  # Removido: agora verificamos por campanha específica


@login_required
def home(request: HttpRequest) -> HttpResponse:
    return render(request, "hud/role_choice.html")


@login_required
def master_dashboard(request: HttpRequest) -> HttpResponse:
    campaigns = Campaign.objects.filter(master=request.user)
    campaigns_as_player = request.user.campaigns_as_player.all()
    campaign_form = CampaignForm()

    if request.method == "POST":
        campaign_form = CampaignForm(request.POST, request.FILES)
        if campaign_form.is_valid():
            campaign = campaign_form.save(commit=False)
            campaign.master = request.user
            campaign.save()
            # Automatically add master as a player
            campaign.players.add(request.user)
            messages.success(request, "Campanha criada!")
            return redirect("campaign_detail", pk=campaign.pk)

    return render(
        request,
        "hud/master_dashboard.html",
        {
            "campaigns": campaigns,
            "campaign_form": campaign_form,
            "campaigns_as_player": campaigns_as_player,
        },
    )


@login_required
def player_dashboard(request: HttpRequest) -> HttpResponse:
    # Show all campaigns the player is part of
    campaigns_as_player = request.user.campaigns_as_player.all()
    
    # Player mode: força modo de visualização
    player_mode = request.GET.get("mode") == "player"
    
    return render(
        request,
        "hud/player_dashboard.html",
        {"campaigns": campaigns_as_player, "player_mode": player_mode},
    )


@login_required
def campaign_detail(request: HttpRequest, pk: int) -> HttpResponse:
    campaign = get_object_or_404(Campaign, pk=pk)

    # Verificar acesso: mestre ou player vinculado
    is_master = campaign.master == request.user
    is_player = request.user in campaign.players.all()

    # Se mode=player, força modo player (sem edição)
    if request.GET.get("mode") == "player":
        is_master = False

    if not is_master and not is_player:
        return HttpResponseForbidden("Você não tem acesso a esta campanha.")

    campaign_form = CampaignForm(instance=campaign, prefix="campaign")
    character_form = CharacterForm(prefix="character")
    # Filter assigned_to to show only players in this campaign
    character_form.fields["assigned_to"].queryset = campaign.players.all()
    item_form = ItemForm(prefix="item")
    players = campaign.players.select_related("profile").all()
    search_results = []
    if is_master:
        q = request.GET.get("player_q", "").strip()
        if q:
            # Busca por apelido (nickname), case-insensitive
            profiles = UserProfile.objects.select_related("user").filter(nickname__icontains=q)
            # Excluir mestre e os já adicionados
            profiles = [p for p in profiles if p.user != campaign.master and p.user not in players]
            search_results = profiles

    if request.method == "POST" and is_master:
        form_type = request.POST.get("form_type")
        if form_type == "campaign":
            campaign_form = CampaignForm(request.POST, request.FILES, instance=campaign, prefix="campaign")
            if campaign_form.is_valid():
                campaign_form.save()
                messages.success(request, "Campanha atualizada.")
                return redirect("campaign_detail", pk=campaign.pk)
        elif form_type == "delete_campaign":
            confirm_name = request.POST.get("confirm_name", "")
            if confirm_name == campaign.name:
                campaign.delete()
                messages.success(request, "Campanha deletada junto com seus personagens e itens.")
                return redirect("master_dashboard")
            messages.error(request, "Nome da campanha não confere.")
            return redirect("campaign_detail", pk=campaign.pk)
        elif form_type == "character":
            character_form = CharacterForm(request.POST, request.FILES, prefix="character")
            if character_form.is_valid():
                character = character_form.save(commit=False)
                character.campaign = campaign
                character.created_by = request.user
                character.save()
                messages.success(request, "Personagem criado.")
                return redirect("campaign_detail", pk=campaign.pk)
        elif form_type == "item":
            item_form = ItemForm(request.POST, request.FILES, prefix="item")
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.campaign = campaign
                item.created_by = request.user
                item.save()
                messages.success(request, "Item adicionado à campanha.")
                return redirect("campaign_detail", pk=campaign.pk)
        elif form_type == "add_player":
            user_id = request.POST.get("user_id")
            if user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = get_object_or_404(User, pk=user_id)
                if user != campaign.master:
                    campaign.players.add(user)
                    messages.success(request, "Jogador adicionado à campanha.")
                return redirect("campaign_detail", pk=campaign.pk)
        elif form_type == "remove_player":
            user_id = request.POST.get("user_id")
            if user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = get_object_or_404(User, pk=user_id)
                if user in campaign.players.all():
                    campaign.players.remove(user)
                    messages.success(request, "Jogador removido da campanha.")
                return redirect("campaign_detail", pk=campaign.pk)
        elif form_type == "add_players_bulk":
            user_ids = request.POST.getlist("user_ids")
            if user_ids:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                users = User.objects.filter(pk__in=user_ids).exclude(pk=campaign.master_id)
                for u in users:
                    campaign.players.add(u)
                messages.success(request, "Jogadores adicionados à campanha.")
            return redirect("campaign_detail", pk=campaign.pk)

    characters = campaign.characters.all()
    
    # Se não for mestre, mostra apenas personagens visíveis
    if not is_master:
        characters = characters.filter(visible=True)
    
    items = campaign.items.all()

    return render(
        request,
        "hud/campaign_detail.html",
        {
            "campaign": campaign,
            "characters": characters,
            "character_form": character_form,
            "campaign_form": campaign_form,
            "item_form": item_form,
            "items": items,
            "is_master": is_master,
            "players": players,
            "search_results": search_results,
        },
    )


@login_required
def search_players(request: HttpRequest, pk: int) -> JsonResponse:
    campaign = get_object_or_404(Campaign, pk=pk)
    if campaign.master != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)
    q = (request.GET.get("q", "") or "").strip()
    results = []
    if q:
        profiles = (
            UserProfile.objects.select_related("user")
            .filter(
                Q(nickname__icontains=q)
                | Q(display_name__icontains=q)
                | Q(user__username__icontains=q)
            )
            .exclude(user=campaign.master)
        )
        current_ids = set(campaign.players.values_list("id", flat=True))
        for p in profiles:
            if p.user_id in current_ids:
                continue
            results.append(
                {
                    "id": p.user_id,
                    "name": p.user.username,
                    "avatar": p.avatar.url if p.avatar else "",
                }
            )
    return JsonResponse(results, safe=False)


@login_required
@require_POST
def delete_item(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Item, pk=pk)
    if not item.campaign or item.campaign.master != request.user:
        return HttpResponseForbidden("Sem permissão")
    campaign_id = item.campaign_id
    item.delete()
    messages.success(request, "Item deletado.")
    return redirect("campaign_detail", pk=campaign_id)


@login_required
@require_POST
def delete_character(request: HttpRequest, pk: int) -> HttpResponse:
    character = get_object_or_404(Character, pk=pk)
    if not character.campaign or character.campaign.master != request.user:
        return HttpResponseForbidden("Sem permissão")
    campaign_id = character.campaign_id
    character.delete()
    messages.success(request, "Personagem deletado.")
    return redirect("campaign_detail", pk=campaign_id)
@login_required
def user_page(request: HttpRequest) -> HttpResponse:
    form = ProfileEditForm(user=request.user, data=request.POST or None, files=request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Perfil atualizado.")
        return redirect("user_page")
    return render(
        request,
        "hud/user_page.html",
        {"form": form},
    )


def register(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, "Conta criada. Faça login.")
        return redirect("login")
    return render(request, "registration/register.html", {"form": form})


@login_required
def character_detail(request: HttpRequest, pk: int) -> HttpResponse:
    character = get_object_or_404(Character, pk=pk)
    campaign = character.campaign

    # Verificar acesso e permissões
    is_master = False
    is_player = False
    
    if campaign:
        # Se há campanha, só mestre da campanha consegue editar
        is_master = campaign.master == request.user
        # Jogador vê se está vinculado ao personagem OU na campanha
        is_player = request.user in campaign.players.all() or character.assigned_to == request.user
    else:
        # Fallback para modo legado (sem campanha)
        is_master = character.created_by == request.user
        is_player = character.assigned_to == request.user

    # Se acessar com ?mode=player, força modo leitura mesmo sendo mestre
    if request.GET.get("mode") == "player":
        is_master = False

    if not is_master and not is_player:
        return HttpResponseForbidden("Você não tem acesso a este personagem.")

    skill_form = CharacterSkillForm(prefix="skill")
    ability_form = CharacterAbilityForm(prefix="ability")
    character_form = CharacterForm(instance=character, prefix="character")

    if request.method == "POST" and is_master:
        form_type = request.POST.get("form_type")
        if form_type == "character":
            character_form = CharacterForm(request.POST, request.FILES, instance=character, prefix="character")
            if character_form.is_valid():
                character_form.save()
                messages.success(request, "Personagem atualizado.")
                return redirect("character_detail", pk=character.pk)
        elif form_type == "skill":
            skill_form = CharacterSkillForm(request.POST, prefix="skill")
            if skill_form.is_valid():
                skill = skill_form.save(commit=False)
                skill.character = character
                skill.save()
                messages.success(request, "Perícia adicionada.")
                return redirect("character_detail", pk=character.pk)
        elif form_type == "ability":
            ability_form = CharacterAbilityForm(request.POST, prefix="ability")
            if ability_form.is_valid():
                ability = ability_form.save(commit=False)
                ability.character = character
                ability.save()
                messages.success(request, "Habilidade adicionada.")
                return redirect("character_detail", pk=character.pk)
        elif form_type == "change_player":
            assigned_to_id = request.POST.get("assigned_to")
            if assigned_to_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    new_player = User.objects.get(pk=assigned_to_id)
                    if character.campaign and new_player in character.campaign.players.all():
                        character.assigned_to = new_player
                        character.save()
                        messages.success(request, "Jogador reatribuído.")
                except User.DoesNotExist:
                    messages.error(request, "Jogador não encontrado.")
                return redirect("character_detail", pk=character.pk)

    character.ensure_slots()
    slots_list = list(InventorySlot.objects.filter(character=character).order_by("position"))
    items = Item.objects.filter(campaign=character.campaign) if character.campaign else Item.objects.none()
    campaign_characters = character.campaign.characters.all() if character.campaign else []
    return render(
        request,
        "hud/character_detail.html",
        {
            "character": character,
            "slots": slots_list,
            "is_master": is_master,
            "character_form": character_form,
            "skill_form": skill_form,
            "ability_form": ability_form,
            "items": items,
            "campaign": character.campaign,
            "campaign_characters": campaign_characters,
        },
    )


@login_required
@require_POST
def assign_slot(request: HttpRequest, character_id: int, slot_id: int) -> JsonResponse:
    character = get_object_or_404(Character, pk=character_id)
    # Permite mestre da campanha ou criador do personagem
    if character.campaign:
        if character.campaign.master != request.user:
            return JsonResponse({"error": "Sem permissão"}, status=403)
    elif character.created_by != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    slot = get_object_or_404(InventorySlot, pk=slot_id, character=character)
    item_id = request.POST.get("item_id")

    if item_id:
        item = get_object_or_404(Item, pk=item_id)
        slot.item = item
        slot.save()
        return JsonResponse(
            {"success": True, "itemName": item.name, "itemImage": item.image.url if item.image else ""}
        )

    # Sem item_id: remove item do slot
    slot.item = None
    slot.save()
    return JsonResponse({"success": True, "itemName": "Vazio", "itemImage": ""})


@login_required
def character_list(request: HttpRequest) -> HttpResponse:
    """Legado: redireciona para master_dashboard"""
    if not _user_is_master(request.user):
        return HttpResponseForbidden("Apenas mestres podem acessar esta página.")
    return redirect("master_dashboard")


@login_required
@require_POST
def modify_hp(request: HttpRequest, character_id: int) -> JsonResponse:
    """Modifica HP atual do personagem (+1 ou -1)"""
    character = get_object_or_404(Character, pk=character_id)
    
    # Verifica permissão: mestre da campanha OU dono do personagem
    if character.campaign:
        is_master = character.campaign.master == request.user
        is_owner = character.assigned_to == request.user
        if not (is_master or is_owner):
            return JsonResponse({"error": "Sem permissão"}, status=403)
    else:
        if character.assigned_to != request.user and character.created_by != request.user:
            return JsonResponse({"error": "Sem permissão"}, status=403)
    
    action = request.POST.get("action")  # "increase" ou "decrease"
    
    if action == "increase":
        character.hp_current = min(character.hp_current + 1, character.hp_max)
    elif action == "decrease":
        character.hp_current = max(character.hp_current - 1, 0)
    else:
        return JsonResponse({"error": "Ação inválida"}, status=400)
    
    character.save()
    return JsonResponse({"success": True, "hp_current": character.hp_current})


@login_required
@require_POST
def modify_sp(request: HttpRequest, character_id: int) -> JsonResponse:
    """Modifica SP atual do personagem (+1 ou -1)"""
    character = get_object_or_404(Character, pk=character_id)
    
    # Verifica permissão: mestre da campanha OU dono do personagem
    if character.campaign:
        is_master = character.campaign.master == request.user
        is_owner = character.assigned_to == request.user
        if not (is_master or is_owner):
            return JsonResponse({"error": "Sem permissão"}, status=403)
    else:
        if character.assigned_to != request.user and character.created_by != request.user:
            return JsonResponse({"error": "Sem permissão"}, status=403)
    
    action = request.POST.get("action")  # "increase" ou "decrease"
    
    if action == "increase":
        character.sp_current = min(character.sp_current + 1, character.sp_max)
    elif action == "decrease":
        character.sp_current = max(character.sp_current - 1, 0)
    else:
        return JsonResponse({"error": "Ação inválida"}, status=400)
    
    character.save()
    return JsonResponse({"success": True, "sp_current": character.sp_current})


@login_required
@require_POST
def toggle_character_visibility(request: HttpRequest, character_id: int) -> JsonResponse:
    """Alterna visibilidade do personagem (apenas mestre)"""
    character = get_object_or_404(Character, pk=character_id)
    
    # Apenas mestre da campanha pode alterar
    if not character.campaign or character.campaign.master != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)
    
    character.visible = not character.visible
    character.save()
    
    return JsonResponse({"success": True, "visible": character.visible})


@login_required
@require_POST
def add_character_bar(request: HttpRequest, character_id: int) -> JsonResponse:
    """Adiciona uma nova barra ao personagem"""
    character = get_object_or_404(Character, pk=character_id)
    
    # Verifica permissão: apenas mestre
    if character.campaign:
        if character.campaign.master != request.user:
            return JsonResponse({"error": "Sem permissão"}, status=403)
    elif character.created_by != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)
    
    name = request.POST.get("name", "Nova Barra")
    max_value = int(request.POST.get("max_value", 100))
    color = request.POST.get("color", "#70e0ff")
    
    bar = CharacterBar.objects.create(
        character=character,
        name=name,
        current=max_value,
        max_value=max_value,
        color=color,
        order=character.bars.count()
    )
    
    return JsonResponse({
        "success": True,
        "bar": {
            "id": bar.id,
            "name": bar.name,
            "current": bar.current,
            "max_value": bar.max_value,
            "color": bar.color
        }
    })


@login_required
@require_POST
def modify_bar(request: HttpRequest, bar_id: int) -> JsonResponse:
    """Modifica valor de uma barra (+1 ou -1)"""
    bar = get_object_or_404(CharacterBar, pk=bar_id)
    character = bar.character
    
    # Verifica permissão: mestre ou dono
    if character.campaign:
        is_master = character.campaign.master == request.user
        is_owner = character.assigned_to == request.user
        if not (is_master or is_owner):
            return JsonResponse({"error": "Sem permissão"}, status=403)
    else:
        if character.assigned_to != request.user and character.created_by != request.user:
            return JsonResponse({"error": "Sem permissão"}, status=403)
    
    action = request.POST.get("action")
    
    if action == "increase":
        bar.current = min(bar.current + 1, bar.max_value)
    elif action == "decrease":
        bar.current = max(bar.current - 1, 0)
    else:
        return JsonResponse({"error": "Ação inválida"}, status=400)
    
    bar.save()
    return JsonResponse({"success": True, "current": bar.current})


@login_required
@require_POST
def delete_bar(request: HttpRequest, bar_id: int) -> JsonResponse:
    """Deleta uma barra personalizada"""
    bar = get_object_or_404(CharacterBar, pk=bar_id)
    character = bar.character
    
    # Apenas mestre pode deletar
    if character.campaign:
        if character.campaign.master != request.user:
            return JsonResponse({"error": "Sem permissão"}, status=403)
    elif character.created_by != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)
    
    bar.delete()
    return JsonResponse({"success": True})

