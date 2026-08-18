"""Avisa os navegadores da campanha que o áudio mudou.

O PythonAnywhere não serve WebSocket, então o empurrão vem de fora: o Django
publica no Pusher e os clientes escutam o canal da campanha.

Duas decisões que valem registro:

**Sem chave configurada, isto vira um nada silencioso.** O widget continua
funcionando pelo `polling` lento que ele já faz por segurança — só deixa de ser
instantâneo. É o que permite rodar o projeto (e os testes) sem conta no Pusher.

**Falha de rede não derruba o pedido.** Se o Pusher estiver fora do ar, o mestre
não pode receber um 500 por causa disso: o estado já foi salvo no banco, que é a
fonte da verdade, e o `polling` entrega o resto. O empurrão é otimização, não o
mecanismo.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_cliente = None


PREFIXO = "private-campanha-"


def canal_da_campanha(campaign_id: int) -> str:
    """Canal privado, não público.

    Canal público seria mais simples, mas qualquer um com a chave — que vai para
    o navegador, é pública por desenho — poderia assinar o canal de qualquer
    campanha e acompanhar a trilha de mesas onde não entra. O `private-` obriga
    o Pusher a pedir uma assinatura ao nosso servidor antes de deixar alguém
    entrar, e é lá que conferimos se a pessoa participa da campanha.
    """
    return f"{PREFIXO}{campaign_id}-audio"


def campanha_do_canal(nome: str) -> int | None:
    """O id da campanha embutido no nome do canal, ou None se não for nosso."""
    if not nome.startswith(PREFIXO) or not nome.endswith("-audio"):
        return None
    miolo = nome[len(PREFIXO):-len("-audio")]
    return int(miolo) if miolo.isdigit() else None


def autenticar(canal: str, socket_id: str) -> dict:
    """Assinatura que o Pusher exige para liberar um canal privado.

    Quem decide se pode é a view; aqui só assinamos.
    """
    return _obter_cliente().authenticate(channel=canal, socket_id=socket_id)


def configurado() -> bool:
    return all(
        [
            getattr(settings, "PUSHER_APP_ID", ""),
            getattr(settings, "PUSHER_KEY", ""),
            getattr(settings, "PUSHER_SECRET", ""),
        ]
    )


def _obter_cliente():
    global _cliente
    if _cliente is None:
        import pusher

        _cliente = pusher.Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET,
            cluster=settings.PUSHER_CLUSTER,
            ssl=True,
        )
    return _cliente


def publicar(campaign_id: int, evento: str, dados: dict) -> bool:
    """Devolve se o empurrão saiu. Nunca levanta."""
    if not configurado():
        return False

    try:
        _obter_cliente().trigger(canal_da_campanha(campaign_id), evento, dados)
        return True
    except Exception:  # noqa: BLE001 - qualquer falha aqui é acessória
        logger.warning("Pusher não recebeu o evento %s", evento, exc_info=True)
        return False
