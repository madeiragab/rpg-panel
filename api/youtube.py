"""Extrai o id de um vídeo do YouTube a partir de qualquer link que o usuário cole.

O mestre vai colar o que o navegador dele der: link da barra de endereços, link
do botão compartilhar, link com a lista inteira pendurada atrás, link com o
tempo em que ele pausou. Tudo isso aponta para o mesmo vídeo, e a lista da
campanha não pode ficar com a mesma música quatro vezes por causa disso.

Aceita também o id cru, porque é o que sai da nossa própria API.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# O id do YouTube tem onze caracteres, no alfabeto do base64 para URL.
PADRAO_DE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

DOMINIOS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be", "www.youtu.be",
}


class LinkInvalido(ValueError):
    pass


def extrair_id(entrada: str) -> str:
    """Devolve o id de onze caracteres ou levanta `LinkInvalido`."""
    texto = (entrada or "").strip()
    if not texto:
        raise LinkInvalido("Cole um link do YouTube.")

    if PADRAO_DE_ID.match(texto):
        return texto

    # Sem esquema o urlparse trata "youtu.be/abc" como caminho, não como host.
    if "//" not in texto:
        texto = "https://" + texto

    url = urlparse(texto)
    host = (url.hostname or "").lower()
    if host not in DOMINIOS:
        raise LinkInvalido("Isso não parece um link do YouTube.")

    if host.endswith("youtu.be"):
        candidato = url.path.lstrip("/").split("/")[0]
    elif url.path.startswith(("/shorts/", "/embed/", "/v/", "/live/")):
        candidato = url.path.split("/")[2] if len(url.path.split("/")) > 2 else ""
    else:
        candidato = (parse_qs(url.query).get("v") or [""])[0]

    if not PADRAO_DE_ID.match(candidato):
        raise LinkInvalido("Não achei o vídeo nesse link.")

    return candidato
