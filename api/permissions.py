"""Quem pode o quê.

As regras aqui são as mesmas que o painel HTML aplica nas views — elas só
estavam espalhadas dentro de cada view, repetidas em `if` parecidos. A API não
pode ter uma segunda versão delas: duas cópias de uma regra de acesso viram duas
regras diferentes na primeira vez que alguém corrige só uma.

Resumo do domínio:

- o mestre da campanha manda em tudo que pertence a ela;
- o jogador da campanha vê o que está marcado como visível;
- o jogador atribuído a um personagem mexe nos status dele (vida, energia,
  barras), mas não na ficha;
- NPC é do mestre. O jogador só vê um NPC se ele estiver visível *e* vinculado
  a um personagem dele.
"""

from __future__ import annotations

from django.db.models import Q

from hud.models import Campaign


def campanhas_do_usuario(user):
    """Campanhas em que o usuário é mestre ou jogador."""
    return Campaign.objects.filter(Q(master=user) | Q(players=user)).distinct()


def eh_mestre(user, campaign) -> bool:
    return bool(campaign) and campaign.master_id == user.id


def participa(user, campaign) -> bool:
    if not campaign:
        return False
    return eh_mestre(user, campaign) or campaign.players.filter(pk=user.pk).exists()


def pode_ver_personagem(user, character) -> bool:
    if eh_mestre(user, character.campaign):
        return True
    if character.assigned_to_id == user.id:
        return True
    return character.visible and participa(user, character.campaign)


def pode_editar_personagem(user, character) -> bool:
    """Ficha é do mestre: nome, imagem, capacidade, máximos, visibilidade."""
    return eh_mestre(user, character.campaign)


def pode_mexer_status(user, character) -> bool:
    """Vida, energia e barras: mestre ou o jogador atribuído à ficha."""
    return eh_mestre(user, character.campaign) or character.assigned_to_id == user.id


def pode_ver_npc(user, npc) -> bool:
    if eh_mestre(user, npc.campaign):
        return True
    if not npc.visible or not participa(user, npc.campaign):
        return False
    vinculo = npc.assigned_to_character
    return bool(vinculo) and vinculo.assigned_to_id == user.id


def pode_editar_npc(user, npc) -> bool:
    return eh_mestre(user, npc.campaign)
