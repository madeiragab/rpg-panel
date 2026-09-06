from __future__ import annotations

from typing import Any
from datetime import timedelta
import json

from math import isfinite
from random import randint

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.db.models import Q
from .forms import RegistrationForm, ProfileEditForm, ForgotPasswordForm, ResetPasswordForm
from .models import UserProfile, PasswordResetToken


from .forms import (
    CampaignForm,
    CharacterAbilityForm,
    CharacterAttackForm,
    CharacterAttributeForm,
    CharacterForm,
    CharacterSkillForm,
    EnemyAbilityForm,
    EnemyAttackForm,
    EnemyForm,
    EnemySkillForm,
    ItemForm,
    PolaroidForm,
    NPCForm,
    NPCAbilityForm,
    NPCAttackForm,
    NPCAttributeForm,
    NPCSkillForm,
)
from .models import (
    Campaign,
    Character,
    CharacterAbility,
    CharacterAttack,
    CharacterAttribute,
    CharacterBar,
    CharacterSkill,
    Enemy,
    EnemyAbility,
    EnemyAttack,
    EnemyAttribute,
    EnemyBar,
    EnemySkill,
    InventorySlot,
    Item,
    NPC,
    NPCAbility,
    NPCAttack,
    NPCAttribute,
    NPCBar,
    NPCInventorySlot,
    NPCSkill,
    Polaroid,
    StickyNote,
    UserProfile,
)


PEDIDOS_POR_CONTA = 5
PEDIDOS_POR_IP = 10
JANELA_DE_PEDIDOS = 60 * 60  # 1 hora


def _pode_pedir_reset(request: HttpRequest, username: str) -> bool:
    """Segura o gatilho do esqueci-a-senha.

    Sem isto, o endereço vira um botão de disparar e-mail em série contra a
    caixa de qualquer usuário. Conta e IP têm cotas separadas: a da conta
    protege a vítima, a do IP protege o resto.

    O contador vive no cache padrão, que é de processo. Num servidor com vários
    workers cada um tem o seu, então o teto real é o número de workers vezes a
    cota. Ainda assim é a diferença entre milhares de e-mails e algumas dezenas.
    """
    ip = (request.META.get("REMOTE_ADDR") or "sem-ip").strip()
    chaves = (
        (f"reset:conta:{username}", PEDIDOS_POR_CONTA),
        (f"reset:ip:{ip}", PEDIDOS_POR_IP),
    )

    for chave, teto in chaves:
        if cache.get(chave, 0) >= teto:
            return False

    for chave, _teto in chaves:
        cache.add(chave, 0, JANELA_DE_PEDIDOS)
        try:
            cache.incr(chave)
        except ValueError:
            # A entrada expirou entre o add e o incr; na próxima ela existe.
            cache.set(chave, 1, JANELA_DE_PEDIDOS)

    return True


def forgot_password(request: HttpRequest) -> HttpResponse:
    """Solicita reset de senha por username.

    A resposta é a mesma exista ou não a conta, e o e-mail não aparece na tela:
    dizer "usuário não encontrado" entrega quais contas existem para quem está
    chutando nomes. Por isso o envio também é `fail_silently` — um erro de SMTP
    que só acontecesse no caminho do usuário existente seria o mesmo vazamento
    por outra porta.
    """
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            user = User.objects.filter(username=username).first()
            if user is not None and user.email and _pode_pedir_reset(request, username):
                # O banco guarda só o hash; o valor cru sai daqui direto para o
                # e-mail e não fica em lugar nenhum.
                token = PasswordResetToken.emitir(user, timedelta(hours=24))

                # Envia email
                reset_url = request.build_absolute_uri(f"/reset-password/{token}/")
                send_mail(
                    subject="Recuperar sua senha - Painel RPG HUD",
                    message=f"Olá {user.username},\n\nClique no link abaixo para resetar sua senha:\n\n{reset_url}\n\nEste link expira em 24 horas.",
                    from_email=None,  # cai no DEFAULT_FROM_EMAIL
                    recipient_list=[user.email],
                    fail_silently=True,
                )

            return render(request, "registration/forgot_password_sent.html")
    else:
        form = ForgotPasswordForm()

    return render(request, "registration/forgot_password.html", {"form": form})


def reset_password(request: HttpRequest, token: str) -> HttpResponse:
    """Reseta a senha com token válido"""
    try:
        # O que está gravado é o hash, então a busca é pelo hash do que chegou.
        reset_token = PasswordResetToken.objects.get(
            token=PasswordResetToken.hash_token(token)
        )
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

            # Queima todos os tokens abertos do usuário, não só este. Se alguém
            # pediu três resets, os outros dois continuariam valendo por 24h.
            PasswordResetToken.objects.filter(
                user=reset_token.user, used=False
            ).update(used=True)

            messages.success(request, "Senha alterada com sucesso! Faça login com sua nova senha.")
            return redirect("login")
    else:
        form = ResetPasswordForm()
    
    return render(request, "registration/reset_password.html", {
        "form": form,
        "token": token
    })
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
        {
            "campaigns": campaigns_as_player,
            "player_mode": player_mode,
        },
    )


def _pediu_sem_recarregar(request: HttpRequest) -> bool:
    """Se quem chamou espera só o pedaço novo, e não a página inteira."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _pedaco(request: HttpRequest, template: str, contexto: dict[str, Any]) -> JsonResponse:
    """Devolve o card recém-criado já montado.

    O HTML sai do mesmo template que desenha os outros da grade, e não de uma
    montagem em JavaScript: um card que nasce agora tem que ser idêntico ao que
    já estava na tela, e duas cópias do mesmo layout divergem na primeira
    mudança.
    """
    return JsonResponse(
        {"ok": True, "html": render_to_string(template, contexto, request=request)}
    )


def _erro_do_form(form) -> JsonResponse:  # noqa: ANN001
    primeiro = next(iter(form.errors.values()), ["Confira os campos."])
    return JsonResponse({"ok": False, "erro": primeiro[0]}, status=400)


def _apagado(request: HttpRequest, destino: str, pk: int) -> HttpResponse:
    """Quem apagou pela página volta para ela; quem apagou pelo card, não."""
    if _pediu_sem_recarregar(request):
        return JsonResponse({"ok": True})
    return redirect(destino, pk=pk)


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
    npc_form = NPCForm(prefix="npc") if is_master else None
    if is_master and npc_form:
        npc_form.fields["assigned_to_character"].queryset = campaign.characters.all()
    enemy_form = EnemyForm(prefix="enemy") if is_master else None
    polaroid_form = PolaroidForm(prefix="polaroid") if is_master else None
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
                if _pediu_sem_recarregar(request):
                    return _pedaco(
                        request,
                        "hud/_card_personagem.html",
                        {"character": character, "is_master": True},
                    )
                messages.success(request, "Personagem criado.")
                return redirect("campaign_detail", pk=campaign.pk)
            elif _pediu_sem_recarregar(request):
                return _erro_do_form(character_form)
        elif form_type == "item":
            item_form = ItemForm(request.POST, request.FILES, prefix="item")
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.campaign = campaign
                item.created_by = request.user
                item.save()
                if _pediu_sem_recarregar(request):
                    return _pedaco(request, "hud/_card_item.html", {"item": item})
                messages.success(request, "Item adicionado à campanha.")
                return redirect("campaign_detail", pk=campaign.pk)
            elif _pediu_sem_recarregar(request):
                return _erro_do_form(item_form)
        elif form_type == "npc":
            npc_form = NPCForm(request.POST, request.FILES, prefix="npc")
            if npc_form.is_valid():
                npc = npc_form.save(commit=False)
                npc.campaign = campaign
                npc.created_by = request.user
                npc.save()
                if _pediu_sem_recarregar(request):
                    return _pedaco(
                        request, "hud/_card_npc.html", {"npc": npc, "is_master": True}
                    )
                messages.success(request, "NPC adicionado à campanha.")
                return redirect("campaign_detail", pk=campaign.pk)
            elif _pediu_sem_recarregar(request):
                return _erro_do_form(npc_form)
        elif form_type == "polaroid":
            polaroid_form = PolaroidForm(request.POST, request.FILES, prefix="polaroid")
            if polaroid_form.is_valid():
                polaroid = polaroid_form.save(commit=False)
                polaroid.campaign = campaign
                polaroid.created_by = request.user
                # Cada foto entra torta de um jeito, e continua desse jeito: um
                # quadro que reembaralha os ângulos a cada F5 cansa de olhar.
                polaroid.tilt = randint(-Polaroid.INCLINACAO_MAXIMA, Polaroid.INCLINACAO_MAXIMA)
                polaroid.save()
                if _pediu_sem_recarregar(request):
                    _arrumar_no_quadro([polaroid])
                    return _pedaco(request, "hud/_peca_polaroid.html", {"peca": polaroid})
                messages.success(request, "Polaroid pregada no quadro.")
                return redirect("campaign_detail", pk=campaign.pk)
            elif _pediu_sem_recarregar(request):
                return _erro_do_form(polaroid_form)
        elif form_type == "enemy":
            enemy_form = EnemyForm(request.POST, request.FILES, prefix="enemy")
            if enemy_form.is_valid():
                enemy = enemy_form.save(commit=False)
                enemy.campaign = campaign
                enemy.created_by = request.user
                enemy.save()
                if _pediu_sem_recarregar(request):
                    return _pedaco(request, "hud/_card_inimigo.html", {"enemy": enemy})
                messages.success(request, "Inimigo adicionado à campanha.")
                return redirect("campaign_detail", pk=campaign.pk)
            elif _pediu_sem_recarregar(request):
                return _erro_do_form(enemy_form)
        elif form_type == "item_update":
            item_id = request.POST.get("item_id")
            description = request.POST.get("description", "")
            if item_id:
                item = get_object_or_404(Item, pk=item_id, campaign=campaign)
                item.description = description
                item.save(update_fields=["description"])
                messages.success(request, "Descrição do item atualizada.")
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
    npcs = campaign.npcs.all()
    # O jogador só enxerga o que o mestre revelou; o mestre vê todos.
    enemies = campaign.enemies.all() if is_master else campaign.enemies.filter(visible=True)
    polaroids = campaign.polaroids.all() if is_master else Polaroid.objects.none()
    notes = campaign.notes.all() if is_master else StickyNote.objects.none()
    # O quadro só monta peça do que já está revelado. O que ainda está oculto
    # não entra: enquanto a mesa não pode ver, aquilo não está em jogo, e a
    # aba de cada tipo continua sendo onde o mestre mexe no que ainda é
    # segredo.
    board_characters = campaign.characters.filter(visible=True) if is_master else []
    board_npcs = campaign.npcs.filter(visible=True) if is_master else []
    board_enemies = campaign.enemies.filter(visible=True) if is_master else []
    if is_master:
        # Uma peça que nunca foi arrastada entra na grade, e a grade é uma só
        # para todas: arrumar cada lista por conta empilharia as três no mesmo
        # canto do quadro.
        _arrumar_no_quadro(
            list(board_characters)
            + list(board_npcs)
            + list(board_enemies)
            + list(polaroids)
            + list(notes)
        )

    return render(
        request,
        "hud/campaign_detail.html",
        {
            "campaign": campaign,
            "characters": characters,
            "character_form": character_form,
            "campaign_form": campaign_form,
            "item_form": item_form,
            "npc_form": npc_form,
            "enemy_form": enemy_form,
            "polaroid_form": polaroid_form,
            "items": items,
            "npcs": npcs,
            "enemies": enemies,
            "board_characters": board_characters,
            "board_npcs": board_npcs,
            "board_enemies": board_enemies,
            "polaroids": polaroids,
            "notes": notes,
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
def delete_npc(request: HttpRequest, pk: int) -> HttpResponse:
    npc = get_object_or_404(NPC, pk=pk)
    if not npc.campaign or npc.campaign.master != request.user:
        return HttpResponseForbidden("Sem permissão")
    campaign_id = npc.campaign_id
    npc.delete()
    if _pediu_sem_recarregar(request):
        return JsonResponse({"ok": True})
    messages.success(request, "NPC deletado.")
    return redirect("campaign_detail", pk=campaign_id)


@login_required
@require_POST
def leave_campaign(request: HttpRequest, pk: int) -> HttpResponse:
    """Remove o jogador da campanha e desvincula seus personagens."""
    campaign = get_object_or_404(Campaign, pk=pk)
    
    # Verificar se o usuário está na campanha
    if request.user not in campaign.players.all():
        return HttpResponseForbidden("Você não está nesta campanha.")
    
    # Desvincula todos os personagens do jogador
    characters = Character.objects.filter(campaign=campaign, assigned_to=request.user)
    for char in characters:
        char.assigned_to = None
        char.save()
    
    # Remove o jogador da campanha
    campaign.players.remove(request.user)
    messages.success(request, f"Você saiu da campanha '{campaign.name}'.")
    return redirect("player_dashboard")


@login_required
@require_POST
def delete_item(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Item, pk=pk)
    if not item.campaign or item.campaign.master != request.user:
        return HttpResponseForbidden("Sem permissão")
    campaign_id = item.campaign_id
    item.delete()
    if _pediu_sem_recarregar(request):
        return JsonResponse({"ok": True})
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
    if _pediu_sem_recarregar(request):
        return JsonResponse({"ok": True})
    messages.success(request, "Personagem deletado.")
    return redirect("campaign_detail", pk=campaign_id)
@login_required
def user_page(request: HttpRequest) -> HttpResponse:
    form = ProfileEditForm(user=request.user, data=request.POST or None, files=request.FILES or None)
    if request.method == "POST" and form.is_valid():
        trocou_senha = bool(form.cleaned_data.get("senha"))
        user = form.save()
        # Trocar a senha invalida o hash guardado na sessão: sem isto o usuário
        # é deslogado no mesmo clique em que atualiza o perfil.
        if trocou_senha:
            update_session_auth_hash(request, user)
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


def _ler_enquadramento(request: HttpRequest) -> tuple[int, float, float] | None:
    """Lê zoom e ponto do POST, já aparados na faixa que a moldura aceita."""
    try:
        zoom = int(float(request.POST.get("zoom", "")))
        x = float(request.POST.get("focus_x", ""))
        y = float(request.POST.get("focus_y", ""))
    except (TypeError, ValueError, OverflowError):
        return None
    # NaN atravessa o float() e depois passa por qualquer min/max sem ser
    # aparado: iria para o banco e deixaria o retrato sem posição.
    if not (isfinite(x) and isfinite(y)):
        return None
    return (
        min(max(zoom, 100), 400),
        min(max(x, 0.0), 1.0),
        min(max(y, 0.0), 1.0),
    )


CAMPOS_DO_ENQUADRAMENTO = ["image_zoom", "image_focus_x", "image_focus_y", "updated_at"]
CAMPOS_DO_CARD = ["card_zoom", "card_focus_x", "card_focus_y", "updated_at"]


def _guardar_enquadramento(request: HttpRequest, ficha, dados) -> None:
    """Grava no enquadramento que o pedido escolheu.

    A mesma imagem tem dois cortes: o da ficha, numa moldura alta, e o do card
    da lista, numa moldura larga e baixa. Um corte so nunca serve para as duas.
    """
    if request.POST.get("alvo") == "menu" and hasattr(ficha, "card_zoom"):
        ficha.card_zoom, ficha.card_focus_x, ficha.card_focus_y = dados
        ficha.save(update_fields=CAMPOS_DO_CARD)
        return
    ficha.image_zoom, ficha.image_focus_x, ficha.image_focus_y = dados
    ficha.save(update_fields=CAMPOS_DO_ENQUADRAMENTO)


@login_required
@require_POST
def update_character_framing(request: HttpRequest, character_id: int) -> JsonResponse:
    """Guarda o corte do retrato. Quem enquadra é quem edita a ficha."""
    character = get_object_or_404(Character, pk=character_id)
    if character.campaign:
        if character.campaign.master != request.user:
            return JsonResponse({"error": "Sem permissão"}, status=403)
    elif character.created_by != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    dados = _ler_enquadramento(request)
    if dados is None:
        return JsonResponse({"error": "Enquadramento inválido"}, status=400)

    _guardar_enquadramento(request, character, dados)
    return JsonResponse(
        {"success": True, "zoom": character.image_zoom,
         "x": character.image_focus_x, "y": character.image_focus_y}
    )


@login_required
@require_POST
def update_npc_framing(request: HttpRequest, npc_id: int) -> JsonResponse:
    """Mesmo corte, do lado do NPC: só o mestre da campanha mexe."""
    npc = get_object_or_404(NPC, pk=npc_id)
    if not npc.campaign or npc.campaign.master != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    dados = _ler_enquadramento(request)
    if dados is None:
        return JsonResponse({"error": "Enquadramento inválido"}, status=400)

    _guardar_enquadramento(request, npc, dados)
    return JsonResponse(
        {"success": True, "zoom": npc.image_zoom,
         "x": npc.image_focus_x, "y": npc.image_focus_y}
    )


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
        # O jogador abre a própria ficha, e só ela. Bastar estar na
        # campanha abria a ficha de todo mundo — nome, vida, perícias e
        # inventário dos outros — e ficha alheia é do dono e do mestre.
        #
        # E só enquanto o mestre a deixa à vista: escondida, ela já sai da
        # lista da campanha, e continuar abrindo pela URL faria do `visible`
        # uma cortina em vez de uma tranca.
        is_player = character.assigned_to == request.user and character.visible
    else:
        # Fallback para modo legado (sem campanha)
        is_master = character.created_by == request.user
        is_player = character.assigned_to == request.user

    # Se acessar com ?mode=player, força modo leitura mesmo sendo mestre
    if request.GET.get("mode") == "player":
        # O mestre continua entrando: ele já vê tudo, e é assim que confere
        # como a ficha chega para a mesa.
        is_player = is_player or is_master
        is_master = False

    if not is_master and not is_player:
        return HttpResponseForbidden("Você não tem acesso a este personagem.")

    skill_form = CharacterSkillForm(prefix="skill")
    ability_form = CharacterAbilityForm(prefix="ability")
    attack_form = CharacterAttackForm(prefix="attack")
    character_form = CharacterForm(instance=character, prefix="character")

    if request.method == "POST" and is_master:
        form_type = request.POST.get("form_type")
        if form_type == "character":
            character_form = CharacterForm(request.POST, request.FILES, instance=character, prefix="character")
            if character_form.is_valid():
                character_form.save()
                character.ensure_slots()  # Ajusta slots após mudança de capacidade
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
        elif form_type == "attack":
            attack_form = CharacterAttackForm(request.POST, prefix="attack")
            if attack_form.is_valid():
                attack = attack_form.save(commit=False)
                attack.character = character
                attack.order = character.attacks.count()
                attack.save()
                messages.success(request, "Ataque adicionado.")
                return redirect("character_detail", pk=character.pk)
        elif form_type == "ability":
            ability_form = CharacterAbilityForm(request.POST, prefix="ability")
            if ability_form.is_valid():
                ability = ability_form.save(commit=False)
                ability.character = character
                ability.save()
                messages.success(request, "Habilidade adicionada.")
                return redirect("character_detail", pk=character.pk)
        elif form_type == "attribute":
            name = request.POST.get("attribute-name", "").strip()
            value = request.POST.get("attribute-value", "").strip()
            if name and value:
                CharacterAttribute.objects.create(
                    character=character,
                    name=name,
                    value=value,
                    order=character.attributes.count(),
                )
                messages.success(request, "Atributo adicionado.")
                return redirect("character_detail", pk=character.pk)
            else:
                messages.error(request, "Nome e valor do atributo são obrigatórios.")
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
    # A barra do topo é a navegação entre fichas, e para o jogador ela tem
    # só a ficha aberta: quem não é mestre não circula pelas fichas da mesa,
    # nem pelas próprias — de personagem para personagem se passa pela
    # campanha. Ao lado dela ficam os NPCs vinculados a este personagem, que
    # é a única companhia que a ficha do jogador tem.
    if not character.campaign:
        campaign_characters = []
    elif is_master:
        campaign_characters = character.campaign.characters.all()
    else:
        campaign_characters = character.campaign.characters.filter(pk=character.pk)
    
    # Buscar NPCs visíveis vinculados ao personagem do jogador
    visible_npcs = NPC.objects.none()
    if character.campaign and is_player:
        visible_npcs = NPC.objects.filter(
            campaign=character.campaign,
            assigned_to_character=character,
            visible=True,
        )
    
    return render(
        request,
        "hud/character_detail.html",
        {
            "character": character,
            "slots": slots_list,
            "is_master": is_master,
            "is_player": is_player,
            "character_form": character_form,
            "skill_form": skill_form,
            "ability_form": ability_form,
            "attack_form": attack_form,
            "items": items,
            "campaign": character.campaign,
            "campaign_characters": campaign_characters,
            "visible_npcs": visible_npcs,
        },
    )


def _passo_da_barra(request: HttpRequest) -> int:
    """De quanto anda a barra neste clique.

    A ficha manda 1 e o quadro manda o que o botão disser: no meio do combate,
    tirar 12 de vida em doze cliques é pior do que não ter o botão.
    """
    try:
        passo = int(request.POST.get("amount", 1))
    except (TypeError, ValueError):
        return 1
    return min(max(passo, 1), 999)


def _item_no_slot(item: Item | None) -> dict[str, Any]:
    """O que o inventory.js precisa para redesenhar um slot.

    O enquadramento vai junto com a imagem: sem ele o slot que acabou de
    receber o item mostraria o corte pelo meio, e só voltaria ao corte certo
    depois de recarregar a página.
    """
    if item is None:
        return {
            "itemName": "Vazio",
            "itemImage": "",
            "itemDescription": "",
            "itemZoom": 100,
            "itemFocusX": 0.5,
            "itemFocusY": 0.5,
        }
    return {
        "itemName": item.name,
        "itemImage": item.image.url if item.image else "",
        "itemDescription": item.description,
        "itemZoom": item.image_zoom,
        "itemFocusX": item.image_focus_x,
        "itemFocusY": item.image_focus_y,
    }


# ---------------------------------------------------------------- o quadro --
# O quadro é do mestre e mostra tudo: personagem, NPC e inimigo da campanha,
# escondidos inclusive. Filtrar pelo `visible` aqui esconderia do mestre o que
# ele mesmo ainda não revelou — cada peça leva um selo dizendo se a mesa a
# enxerga, e é isso que ele precisa saber enquanto arruma a sessão.

# Grade em que as peças que nunca foram arrastadas aparecem. Empilhar todas no
# mesmo ponto deixaria o quadro inútil no primeiro acesso.
COLUNAS_DO_QUADRO = 5
PRIMEIRA_COLUNA = 0.12
PRIMEIRA_LINHA = 0.16
PASSO_HORIZONTAL = 0.19
PASSO_VERTICAL = 0.30


def _arrumar_no_quadro(pecas: list) -> list:
    """Dá a cada peça um `quadro_x`/`quadro_y` para o template posicionar.

    Quem já foi arrastada usa o que está no banco. Quem nunca foi entra na
    grade, sem gravar nada: a posição só vira número no banco quando alguém
    arrasta de verdade.
    """
    solta = 0
    for peca in pecas:
        if peca.board_x is not None and peca.board_y is not None:
            peca.quadro_x = peca.board_x
            peca.quadro_y = peca.board_y
            continue
        coluna = solta % COLUNAS_DO_QUADRO
        linha = solta // COLUNAS_DO_QUADRO
        peca.quadro_x = min(PRIMEIRA_COLUNA + coluna * PASSO_HORIZONTAL, 0.95)
        peca.quadro_y = min(PRIMEIRA_LINHA + linha * PASSO_VERTICAL, 0.95)
        solta += 1
    return pecas


TIPOS_DO_QUADRO = {
    "character": Character,
    "npc": NPC,
    "enemy": Enemy,
    "polaroid": Polaroid,
    "note": StickyNote,
}


@login_required
@require_POST
def move_board_piece(request: HttpRequest, pk: int) -> JsonResponse:
    """Guarda onde a peça parou. Só o mestre arruma o quadro da mesa dele."""
    campaign = get_object_or_404(Campaign, pk=pk)
    if campaign.master != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    modelo = TIPOS_DO_QUADRO.get(request.POST.get("kind", ""))
    if modelo is None:
        return JsonResponse({"error": "Tipo desconhecido"}, status=400)

    try:
        x = float(request.POST.get("x", ""))
        y = float(request.POST.get("y", ""))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Posição inválida"}, status=400)
    if not (isfinite(x) and isfinite(y)):
        return JsonResponse({"error": "Posição inválida"}, status=400)

    # O filtro por campanha é o que impede mover, pela mesma URL, a peça de
    # outra mesa em que este usuário não é mestre.
    peca = get_object_or_404(modelo, pk=request.POST.get("id") or 0, campaign=campaign)
    peca.board_x = min(max(x, 0.0), 1.0)
    peca.board_y = min(max(y, 0.0), 1.0)
    peca.save(update_fields=["board_x", "board_y"])
    return JsonResponse({"success": True, "x": peca.board_x, "y": peca.board_y})


@login_required
@require_POST
def create_sticky_note(request: HttpRequest, pk: int) -> HttpResponse:
    """Prega um post-it vazio no quadro.

    Sem formulário de propósito: o post-it existe para o que o mestre lembrou
    no meio da sessão e não quer perder, e o caminho entre lembrar e escrever
    tem que ser um clique. Ele nasce em branco e é escrito no lugar.
    """
    campaign = get_object_or_404(Campaign, pk=pk)
    if campaign.master != request.user:
        return HttpResponseForbidden("Sem permissão")

    # A cor gira pela lista em vez de sortear: duas seguidas iguais parecem um
    # bug, e o mestre normalmente prega os post-its em sequência.
    cor = StickyNote.CORES[campaign.notes.count() % len(StickyNote.CORES)]
    recado = StickyNote.objects.create(
        campaign=campaign,
        created_by=request.user,
        color=cor,
        tilt=randint(-StickyNote.INCLINACAO_MAXIMA, StickyNote.INCLINACAO_MAXIMA),
    )
    if _pediu_sem_recarregar(request):
        _arrumar_no_quadro([recado])
        return _pedaco(request, "hud/_peca_post_it.html", {"peca": recado})
    return redirect("campaign_detail", pk=campaign.pk)


@login_required
@require_POST
def update_sticky_note(request: HttpRequest, pk: int) -> JsonResponse:
    """Guarda o texto do post-it, do jeito que estava quando pararam de digitar."""
    note = get_object_or_404(StickyNote, pk=pk)
    if note.campaign.master != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    note.text = request.POST.get("text", "")
    note.save(update_fields=["text"])
    return JsonResponse({"success": True, "text": note.text})


@login_required
@require_POST
def delete_sticky_note(request: HttpRequest, pk: int) -> HttpResponse:
    note = get_object_or_404(StickyNote, pk=pk)
    if note.campaign.master != request.user:
        return HttpResponseForbidden("Sem permissão")
    campaign_id = note.campaign_id
    note.delete()
    if _pediu_sem_recarregar(request):
        return JsonResponse({"ok": True})
    messages.success(request, "Post-it tirado do quadro.")
    return redirect("campaign_detail", pk=campaign_id)


@login_required
@require_POST
def delete_polaroid(request: HttpRequest, pk: int) -> HttpResponse:
    polaroid = get_object_or_404(Polaroid, pk=pk)
    if polaroid.campaign.master != request.user:
        return HttpResponseForbidden("Sem permissão")
    campaign_id = polaroid.campaign_id
    polaroid.delete()
    if _pediu_sem_recarregar(request):
        return JsonResponse({"ok": True})
    messages.success(request, "Polaroid removida do quadro.")
    return redirect("campaign_detail", pk=campaign_id)


@login_required
@require_POST
def update_polaroid_framing(request: HttpRequest, polaroid_id: int) -> JsonResponse:
    """Guarda o corte da foto pregada no quadro."""
    polaroid = get_object_or_404(Polaroid, pk=polaroid_id)
    if polaroid.campaign.master != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    dados = _ler_enquadramento(request)
    if dados is None:
        return JsonResponse({"error": "Enquadramento inválido"}, status=400)

    polaroid.image_zoom, polaroid.image_focus_x, polaroid.image_focus_y = dados
    polaroid.save(update_fields=["image_zoom", "image_focus_x", "image_focus_y"])
    return JsonResponse({"success": True})


# ------------------------------------------------ as linhas soltas da ficha --
# Perícia, habilidade e atributo eram só de escrever: entravam e ficavam. São
# nove modelos (três tipos × três fichas) e a diferença entre eles cabe nesta
# tabela, então um par de rotas atende os nove em vez de dezoito views quase
# iguais.
#
# `dono` é o caminho da linha até a campanha, e é por ele que a permissão sai:
# quem edita é sempre o mestre da mesa daquela ficha.
LINHAS_DA_FICHA = {
    "character-skill": (CharacterSkill, "character", ("name", "value")),
    "character-attack": (CharacterAttack, "character", ("name", "damage")),
    "npc-attack": (NPCAttack, "npc", ("name", "damage")),
    "enemy-attack": (EnemyAttack, "enemy", ("name", "damage")),
    "character-ability": (CharacterAbility, "character", ("name", "damage")),
    "character-attribute": (CharacterAttribute, "character", ("name", "value")),
    "npc-skill": (NPCSkill, "npc", ("name", "value")),
    "npc-ability": (NPCAbility, "npc", ("name", "damage")),
    "npc-attribute": (NPCAttribute, "npc", ("name", "value")),
    "enemy-skill": (EnemySkill, "enemy", ("name", "value")),
    "enemy-ability": (EnemyAbility, "enemy", ("name", "damage")),
    "enemy-attribute": (EnemyAttribute, "enemy", ("name", "value")),
}


def _linha_do_mestre(request: HttpRequest, tipo: str, pk: int):
    """A linha, se quem pede for o mestre da campanha dela. Senão, None."""
    registro = LINHAS_DA_FICHA.get(tipo)
    if registro is None:
        return None, None
    modelo, dono, campos = registro
    linha = get_object_or_404(modelo, pk=pk)
    ficha = getattr(linha, dono)
    campanha = ficha.campaign
    if campanha:
        if campanha.master != request.user:
            return None, None
    elif getattr(ficha, "created_by", None) != request.user:
        return None, None
    return linha, campos


@login_required
@require_POST
def update_sheet_line(request: HttpRequest, tipo: str, pk: int) -> JsonResponse:
    """Reescreve uma linha da ficha no lugar."""
    linha, campos = _linha_do_mestre(request, tipo, pk)
    if linha is None:
        return JsonResponse({"ok": False, "erro": "Sem permissão"}, status=403)

    nome = request.POST.get("name", "").strip()
    if not nome:
        return JsonResponse({"ok": False, "erro": "O nome não pode ficar vazio."}, status=400)

    linha.name = nome[:80]
    if "damage" in campos:
        linha.damage = request.POST.get("damage", "").strip()[:60]
        linha.description = request.POST.get("description", "").strip()[:1000]
        # Os campos extras chegam como JSON porque são uma lista de pares de
        # tamanho livre; em campos soltos do POST a ordem se perderia.
        try:
            extras = json.loads(request.POST.get("extras", "[]"))
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "erro": "Campos inválidos."}, status=400)
        linha.extras = extras if isinstance(extras, list) else []
    if "value" in campos:
        # Atributo exige valor; perícia aceita em branco. O modelo é quem sabe:
        # o campo de perícia é blank=True e o de atributo não.
        valor = request.POST.get("value", "").strip()[:40]
        if not valor and not linha._meta.get_field("value").blank:
            return JsonResponse({"ok": False, "erro": "O valor não pode ficar vazio."}, status=400)
        linha.value = valor
    linha.save()

    return JsonResponse(
        {
            "ok": True,
            "name": linha.name,
            "value": getattr(linha, "value", ""),
            "damage": getattr(linha, "damage", ""),
            "description": getattr(linha, "description", ""),
            "extras": getattr(linha, "extras", []),
        }
    )


@login_required
@require_POST
def delete_sheet_line(request: HttpRequest, tipo: str, pk: int) -> JsonResponse:
    linha, _ = _linha_do_mestre(request, tipo, pk)
    if linha is None:
        return JsonResponse({"ok": False, "erro": "Sem permissão"}, status=403)
    linha.delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def reorder_sheet_lines(request: HttpRequest, tipo: str) -> JsonResponse:
    """Grava a nova ordem depois de um arraste.

    Chega a lista inteira de ids na ordem em que ficaram, e não "essa subiu
    uma": duas pessoas arrastando ao mesmo tempo com movimentos relativos
    acabariam com ordens diferentes das que cada uma viu.
    """
    registro = LINHAS_DA_FICHA.get(tipo)
    if registro is None:
        return JsonResponse({"ok": False, "erro": "Tipo desconhecido"}, status=400)

    try:
        ids = [int(x) for x in json.loads(request.POST.get("ids", "[]"))]
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "erro": "Ordem inválida"}, status=400)

    modelo = registro[0]
    linhas = []
    for posicao, pk in enumerate(ids):
        linha, _ = _linha_do_mestre(request, tipo, pk)
        if linha is None:
            return JsonResponse({"ok": False, "erro": "Sem permissão"}, status=403)
        linha.order = posicao
        linhas.append(linha)
    modelo.objects.bulk_update(linhas, ["order"])
    return JsonResponse({"ok": True})


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
        # O item tem que ser da mesma campanha do personagem: sem esse filtro,
        # um id de outra mesa entra no slot e a resposta devolve nome e imagem.
        if character.campaign:
            item = get_object_or_404(Item, pk=item_id, campaign=character.campaign)
        else:
            item = get_object_or_404(Item, pk=item_id, campaign__isnull=True)
        slot.item = item
        slot.save()
        return JsonResponse({"success": True, **_item_no_slot(item)})

    # Sem item_id: remove item do slot
    slot.item = None
    slot.save()
    return JsonResponse({"success": True, **_item_no_slot(None)})


@login_required
@require_POST
def assign_npc_slot(request: HttpRequest, npc_id: int, slot_id: int) -> JsonResponse:
    """Põe ou tira um item de um slot do NPC. Só o mestre da campanha mexe."""
    npc = get_object_or_404(NPC, pk=npc_id)
    if not npc.campaign or npc.campaign.master != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    slot = get_object_or_404(NPCInventorySlot, pk=slot_id, npc=npc)
    item_id = request.POST.get("item_id")

    if item_id:
        item = get_object_or_404(Item, pk=item_id, campaign=npc.campaign)
        slot.item = item
        slot.save()
        return JsonResponse({"success": True, **_item_no_slot(item)})

    slot.item = None
    slot.save()
    return JsonResponse({"success": True, **_item_no_slot(None)})


@login_required
def character_list(request: HttpRequest) -> HttpResponse:
    """Legado: a rota continua no menu, o painel do mestre é quem responde."""
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
def toggle_npc_visibility(request: HttpRequest, npc_id: int) -> JsonResponse:
    """Alterna visibilidade do NPC (apenas mestre)"""
    npc = get_object_or_404(NPC, pk=npc_id)
    
    # Apenas mestre da campanha pode alterar
    if not npc.campaign or npc.campaign.master != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)
    
    npc.visible = not npc.visible
    npc.save()
    
    return JsonResponse({"success": True, "visible": npc.visible})


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

    if _pediu_sem_recarregar(request):
        return _pedaco(
            request,
            "hud/_barra_da_ficha.html",
            {"bar": bar, "fn_mod": "modifyBar", "fn_del": "deleteBar",
             "pode_editar": True, "pode_apagar": True},
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
    
    passo = _passo_da_barra(request)
    if action == "increase":
        bar.current = min(bar.current + passo, bar.max_value)
    elif action == "decrease":
        bar.current = max(bar.current - passo, 0)
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


@login_required
def npc_detail(request: HttpRequest, pk: int) -> HttpResponse:
    npc = get_object_or_404(NPC, pk=pk)
    campaign = npc.campaign

    # Verificar acesso
    is_master = False
    is_player = False
    
    if campaign:
        # Mestre da campanha tem acesso total
        is_master = campaign.master == request.user
        # Jogador só vê se o NPC está vinculado a um de seus personagens
        is_player = request.user in campaign.players.all() and npc.assigned_to_character and npc.assigned_to_character.assigned_to == request.user
    
    # Se mode=player, força modo leitura mesmo sendo mestre
    if request.GET.get("mode") == "player":
        is_master = False

    # Jogador não tem acesso se o NPC não está vinculado a ele
    if not campaign or (not is_master and not is_player):
        return HttpResponseForbidden("Você não tem acesso a este NPC.")

    skill_form = NPCSkillForm(prefix="skill")
    ability_form = NPCAbilityForm(prefix="ability")
    attack_form = NPCAttackForm(prefix="attack")
    npc_form = NPCForm(instance=npc, prefix="npc")
    npc_form.fields["assigned_to_character"].queryset = campaign.characters.all()

    if request.method == "POST" and is_master:
        form_type = request.POST.get("form_type")
        if form_type == "npc":
            npc_form = NPCForm(request.POST, request.FILES, instance=npc, prefix="npc")
            if npc_form.is_valid():
                npc_form.save()
                npc.ensure_slots()
                messages.success(request, "NPC atualizado.")
                return redirect("npc_detail", pk=npc.pk)
        elif form_type == "skill":
            skill_form = NPCSkillForm(request.POST, prefix="skill")
            if skill_form.is_valid():
                skill = skill_form.save(commit=False)
                skill.npc = npc
                skill.save()
                messages.success(request, "Perícia adicionada.")
                return redirect("npc_detail", pk=npc.pk)
        elif form_type == "attack":
            attack_form = NPCAttackForm(request.POST, prefix="attack")
            if attack_form.is_valid():
                attack = attack_form.save(commit=False)
                attack.npc = npc
                attack.order = npc.attacks.count()
                attack.save()
                messages.success(request, "Ataque adicionado.")
                return redirect("npc_detail", pk=npc.pk)
        elif form_type == "ability":
            ability_form = NPCAbilityForm(request.POST, prefix="ability")
            if ability_form.is_valid():
                ability = ability_form.save(commit=False)
                ability.npc = npc
                ability.save()
                messages.success(request, "Habilidade adicionada.")
                return redirect("npc_detail", pk=npc.pk)
        elif form_type == "attribute":
            name = request.POST.get("attribute-name", "").strip()
            value = request.POST.get("attribute-value", "").strip()
            if name and value:
                NPCAttribute.objects.create(
                    npc=npc, name=name, value=value, order=npc.attributes.count()
                )
                messages.success(request, "Atributo adicionado.")
                return redirect("npc_detail", pk=npc.pk)
            else:
                messages.error(request, "Nome e valor do atributo são obrigatórios.")

    npc.ensure_slots()
    slots_list = list(NPCInventorySlot.objects.filter(npc=npc).order_by("position"))
    items = Item.objects.filter(campaign=campaign) if campaign else Item.objects.none()

    return render(
        request,
        "hud/npc_detail.html",
        {
            "npc": npc,
            "slots": slots_list,
            "is_master": is_master,
            "is_player": is_player,
            "npc_form": npc_form,
            "skill_form": skill_form,
            "ability_form": ability_form,
            "attack_form": attack_form,
            "items": items,
            "campaign": campaign,
        },
    )


@login_required
@require_POST
def add_npc_bar(request: HttpRequest, pk: int) -> JsonResponse:
    """Adiciona uma barra dinâmica ao NPC."""
    npc = get_object_or_404(NPC, pk=pk)
    campaign = npc.campaign

    if not campaign or campaign.master != request.user:
        return JsonResponse({"success": False, "error": "Não autorizado"}, status=403)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        max_value = int(request.POST.get("max_value", 100))
        color = request.POST.get("color", "#70e0ff")

        if not name or max_value <= 0:
            return JsonResponse({"success": False, "error": "Dados inválidos"})

        bar = NPCBar.objects.create(
            npc=npc, name=name, max_value=max_value, current=max_value, color=color
        )
        if _pediu_sem_recarregar(request):
            return _pedaco(
                request,
                "hud/_barra_da_ficha.html",
                {"bar": bar, "fn_mod": "modifyNPCBar", "fn_del": "deleteNPCBar",
                 "pode_editar": True, "pode_apagar": True},
            )
        return JsonResponse(
            {
                "success": True,
                "bar": {
                    "id": bar.id,
                    "name": bar.name,
                    "current": bar.current,
                    "max_value": bar.max_value,
                    "color": bar.color,
                },
            }
        )

    return JsonResponse({"success": False, "error": "Método não permitido"}, status=405)


@login_required
@require_POST
def modify_npc_bar(request: HttpRequest, npc_pk: int, bar_id: int) -> JsonResponse:
    """Modifica o valor atual de uma barra do NPC."""
    npc = get_object_or_404(NPC, pk=npc_pk)
    campaign = npc.campaign
    bar = get_object_or_404(NPCBar, id=bar_id, npc=npc)

    if not campaign or campaign.master != request.user:
        return JsonResponse({"success": False, "error": "Não autorizado"}, status=403)

    if request.method == "POST":
        action = request.POST.get("action", "increase")
        passo = _passo_da_barra(request)
        if action == "increase":
            bar.current = min(bar.current + passo, bar.max_value)
        elif action == "decrease":
            bar.current = max(bar.current - passo, 0)
        bar.save()
        return JsonResponse({"success": True, "current": bar.current})

    return JsonResponse({"success": False, "error": "Método não permitido"}, status=405)


@login_required
@require_POST
def delete_npc_bar(request: HttpRequest, npc_pk: int, bar_id: int) -> JsonResponse:
    """Deleta uma barra do NPC."""
    npc = get_object_or_404(NPC, pk=npc_pk)
    campaign = npc.campaign
    bar = get_object_or_404(NPCBar, id=bar_id, npc=npc)

    if not campaign or campaign.master != request.user:
        return JsonResponse({"success": False, "error": "Não autorizado"}, status=403)

    if request.method == "POST":
        bar.delete()
        return JsonResponse({"success": True})

    return JsonResponse({"success": False, "error": "Método não permitido"}, status=405)


@login_required
def enemy_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """A ficha do inimigo. Igual à do personagem, sem a aba de inventário."""
    enemy = get_object_or_404(Enemy, pk=pk)
    campaign = enemy.campaign

    is_master = False
    is_player = False

    if campaign:
        is_master = campaign.master == request.user
        # O jogador só abre o que o mestre já revelou: uma ficha escondida
        # entregaria a vida e as habilidades do que ainda nem apareceu na mesa.
        is_player = request.user in campaign.players.all() and enemy.visible

    if request.GET.get("mode") == "player":
        is_master = False

    if not campaign or (not is_master and not is_player):
        return HttpResponseForbidden("Você não tem acesso a este inimigo.")

    skill_form = EnemySkillForm(prefix="skill")
    ability_form = EnemyAbilityForm(prefix="ability")
    attack_form = EnemyAttackForm(prefix="attack")
    enemy_form = EnemyForm(instance=enemy, prefix="enemy")

    if request.method == "POST" and is_master:
        form_type = request.POST.get("form_type")
        if form_type == "enemy":
            enemy_form = EnemyForm(request.POST, request.FILES, instance=enemy, prefix="enemy")
            if enemy_form.is_valid():
                enemy_form.save()
                messages.success(request, "Inimigo atualizado.")
                return redirect("enemy_detail", pk=enemy.pk)
        elif form_type == "skill":
            skill_form = EnemySkillForm(request.POST, prefix="skill")
            if skill_form.is_valid():
                skill = skill_form.save(commit=False)
                skill.enemy = enemy
                skill.save()
                messages.success(request, "Perícia adicionada.")
                return redirect("enemy_detail", pk=enemy.pk)
        elif form_type == "attack":
            attack_form = EnemyAttackForm(request.POST, prefix="attack")
            if attack_form.is_valid():
                attack = attack_form.save(commit=False)
                attack.enemy = enemy
                attack.order = enemy.attacks.count()
                attack.save()
                messages.success(request, "Ataque adicionado.")
                return redirect("enemy_detail", pk=enemy.pk)
        elif form_type == "ability":
            ability_form = EnemyAbilityForm(request.POST, prefix="ability")
            if ability_form.is_valid():
                ability = ability_form.save(commit=False)
                ability.enemy = enemy
                ability.save()
                messages.success(request, "Habilidade adicionada.")
                return redirect("enemy_detail", pk=enemy.pk)
        elif form_type == "attribute":
            name = request.POST.get("attribute-name", "").strip()
            value = request.POST.get("attribute-value", "").strip()
            if name and value:
                EnemyAttribute.objects.create(
                    enemy=enemy, name=name, value=value, order=enemy.attributes.count()
                )
                messages.success(request, "Atributo adicionado.")
                return redirect("enemy_detail", pk=enemy.pk)
            messages.error(request, "Nome e valor do atributo são obrigatórios.")

    return render(
        request,
        "hud/enemy_detail.html",
        {
            "enemy": enemy,
            "is_master": is_master,
            "is_player": is_player,
            "enemy_form": enemy_form,
            "skill_form": skill_form,
            "ability_form": ability_form,
            "attack_form": attack_form,
            "campaign": campaign,
        },
    )


def _inimigo_do_mestre(request: HttpRequest, pk: int) -> Enemy | None:
    """O inimigo, se quem pede for o mestre da campanha dele. Senão, None."""
    enemy = get_object_or_404(Enemy, pk=pk)
    if not enemy.campaign or enemy.campaign.master != request.user:
        return None
    return enemy


@login_required
@require_POST
def update_enemy_framing(request: HttpRequest, enemy_id: int) -> JsonResponse:
    """Guarda o corte do retrato do inimigo."""
    enemy = _inimigo_do_mestre(request, enemy_id)
    if enemy is None:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    dados = _ler_enquadramento(request)
    if dados is None:
        return JsonResponse({"error": "Enquadramento inválido"}, status=400)

    _guardar_enquadramento(request, enemy, dados)
    return JsonResponse(
        {"success": True, "zoom": enemy.image_zoom,
         "x": enemy.image_focus_x, "y": enemy.image_focus_y}
    )


@login_required
@require_POST
def update_item_framing(request: HttpRequest, item_id: int) -> JsonResponse:
    """Guarda o corte da imagem do item. Item é da mesa, quem enquadra é o mestre."""
    item = get_object_or_404(Item, pk=item_id)
    if item.campaign:
        if item.campaign.master != request.user:
            return JsonResponse({"error": "Sem permissão"}, status=403)
    elif item.created_by != request.user:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    dados = _ler_enquadramento(request)
    if dados is None:
        return JsonResponse({"error": "Enquadramento inválido"}, status=400)

    item.image_zoom, item.image_focus_x, item.image_focus_y = dados
    item.save(update_fields=["image_zoom", "image_focus_x", "image_focus_y"])
    return JsonResponse({"success": True})


@login_required
@require_POST
def update_avatar_framing(request: HttpRequest) -> JsonResponse:
    """Guarda o corte do próprio avatar. Cada um enquadra o seu, e só o seu."""
    perfil = request.user.profile

    dados = _ler_enquadramento(request)
    if dados is None:
        return JsonResponse({"error": "Enquadramento inválido"}, status=400)

    perfil.image_zoom, perfil.image_focus_x, perfil.image_focus_y = dados
    perfil.save(update_fields=["image_zoom", "image_focus_x", "image_focus_y"])
    return JsonResponse({"success": True})


@login_required
@require_POST
def toggle_enemy_visibility(request: HttpRequest, enemy_id: int) -> JsonResponse:
    """Revela ou esconde o inimigo para a mesa. Só o mestre."""
    enemy = _inimigo_do_mestre(request, enemy_id)
    if enemy is None:
        return JsonResponse({"error": "Sem permissão"}, status=403)

    enemy.visible = not enemy.visible
    enemy.save()
    return JsonResponse({"success": True, "visible": enemy.visible})


@login_required
@require_POST
def delete_enemy(request: HttpRequest, pk: int) -> HttpResponse:
    enemy = _inimigo_do_mestre(request, pk)
    if enemy is None:
        return HttpResponseForbidden("Sem permissão")
    campaign_id = enemy.campaign_id
    enemy.delete()
    if _pediu_sem_recarregar(request):
        return JsonResponse({"ok": True})
    messages.success(request, "Inimigo deletado.")
    return redirect("campaign_detail", pk=campaign_id)


@login_required
@require_POST
def add_enemy_bar(request: HttpRequest, pk: int) -> JsonResponse:
    """Adiciona uma barra dinâmica ao inimigo."""
    enemy = _inimigo_do_mestre(request, pk)
    if enemy is None:
        return JsonResponse({"success": False, "error": "Não autorizado"}, status=403)

    name = request.POST.get("name", "").strip()
    try:
        max_value = int(request.POST.get("max_value", 100))
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "Dados inválidos"})
    color = request.POST.get("color", "#e11d2e")

    if not name or max_value <= 0:
        return JsonResponse({"success": False, "error": "Dados inválidos"})

    bar = EnemyBar.objects.create(
        enemy=enemy, name=name, max_value=max_value, current=max_value, color=color
    )
    if _pediu_sem_recarregar(request):
        return _pedaco(
            request,
            "hud/_barra_da_ficha.html",
            {"bar": bar, "fn_mod": "modifyEnemyBar", "fn_del": "deleteEnemyBar",
             "pode_editar": True, "pode_apagar": True},
        )
    return JsonResponse(
        {
            "success": True,
            "bar": {
                "id": bar.id,
                "name": bar.name,
                "current": bar.current,
                "max_value": bar.max_value,
                "color": bar.color,
            },
        }
    )


@login_required
@require_POST
def modify_enemy_bar(request: HttpRequest, enemy_pk: int, bar_id: int) -> JsonResponse:
    """Sobe ou desce em um o valor atual de uma barra do inimigo."""
    enemy = _inimigo_do_mestre(request, enemy_pk)
    if enemy is None:
        return JsonResponse({"success": False, "error": "Não autorizado"}, status=403)

    bar = get_object_or_404(EnemyBar, id=bar_id, enemy=enemy)
    action = request.POST.get("action", "increase")
    passo = _passo_da_barra(request)
    if action == "increase":
        bar.current = min(bar.current + passo, bar.max_value)
    elif action == "decrease":
        bar.current = max(bar.current - passo, 0)
    bar.save()
    return JsonResponse({"success": True, "current": bar.current})


@login_required
@require_POST
def delete_enemy_bar(request: HttpRequest, enemy_pk: int, bar_id: int) -> JsonResponse:
    """Deleta uma barra do inimigo."""
    enemy = _inimigo_do_mestre(request, enemy_pk)
    if enemy is None:
        return JsonResponse({"success": False, "error": "Não autorizado"}, status=403)

    bar = get_object_or_404(EnemyBar, id=bar_id, enemy=enemy)
    bar.delete()
    return JsonResponse({"success": True})


@login_required
@require_GET
def token_do_player(request: HttpRequest) -> JsonResponse:
    """Emite um access curto para o widget de áudio da página.

    O painel é autenticado por sessão e a API só entende JWT, de propósito. Em
    vez de aceitar cookie na API — o que traria CSRF de volta por uma porta onde
    ninguém olha — a página pede aqui um token de quinze minutos e usa ele nas
    chamadas.

    Não há aumento de privilégio: o usuário já poderia obter este mesmo token
    mandando a própria senha em `/api/token/`. E o refresh não passa por aqui,
    porque um refresh de sete dias dentro do HTML seria bem pior do que um
    access que morre sozinho.
    """
    from rest_framework_simplejwt.tokens import AccessToken

    return JsonResponse({"access": str(AccessToken.for_user(request.user))})
