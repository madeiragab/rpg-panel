> 🇧🇷 **Português** · 🇬🇧 [English](api.md)

# API REST

A API vive em `/api/` e é **adição, não substituição**: o painel HTML continua funcionando exatamente como antes, na sessão do Django. Quem fala com a API usa JWT e não usa cookie.

Isso é de propósito. Aceitar cookie de sessão numa API que escreve traria o problema de CSRF de volta por uma porta onde ninguém está olhando, então `SessionAuthentication` não está na lista de autenticação do DRF.

## Autenticação

Três endereços, todos com freio de dez por minuto por IP:

| Método | Endereço | O que faz |
|---|---|---|
| `POST` | `/api/token/` | Troca `username` e `password` por um par `access` + `refresh` |
| `POST` | `/api/token/refresh/` | Troca um `refresh` válido por um `access` novo (e um `refresh` novo) |
| `POST` | `/api/token/logout/` | Manda o `refresh` recebido para a blacklist |

```bash
curl -X POST https://galibinja.pythonanywhere.com/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "mestre", "password": "..."}'
```

A resposta traz os dois tokens. O `access` vai em toda requisição seguinte:

```bash
curl https://galibinja.pythonanywhere.com/api/campaigns/ \
  -H "Authorization: Bearer <access>"
```

### Tempos de vida e rotação

- **access: 15 minutos.** Curto porque não dá para revogar — enquanto vale, vale. Checar revogação a cada requisição custaria uma ida ao banco por chamada, que é exatamente o que o JWT existe para evitar.
- **refresh: 7 dias, com rotação.** Cada uso devolve um refresh novo e manda o antigo para a blacklist. Um refresh copiado só serve até o dono usar o dele — a partir daí o copiado dá 401.

A blacklist é o app `rest_framework_simplejwt.token_blacklist`, e é por isso que ele está no `INSTALLED_APPS`: sem ele a rotação emite token novo mas não invalida o velho.

O logout mata o `refresh`, não o `access`. Quem sair continua com até 15 minutos de acesso no token que já tinha em mãos. Aceitar isso é o preço de não consultar o banco a cada requisição; para expulsar na hora seria preciso uma lista de revogação consultada em toda chamada, que é o desenho oposto.

## Recursos

Tudo abaixo exige `Authorization: Bearer`. As listas são paginadas de 50 em 50 (`?page=`).

| Método | Endereço | Quem pode |
|---|---|---|
| `GET` | `/api/me/` | qualquer autenticado (o próprio perfil) |
| `PATCH` | `/api/me/` | o dono — `role` é somente leitura |
| `GET` `POST` | `/api/campaigns/` | ver: as suas; criar: qualquer um (vira mestre) |
| `GET` | `/api/campaigns/{id}/` | mestre e jogadores da campanha |
| `PATCH` `DELETE` | `/api/campaigns/{id}/` | só o mestre |
| `POST` | `/api/campaigns/{id}/players/` | só o mestre — corpo `{"user": id}` |
| `DELETE` | `/api/campaigns/{id}/players/{user_id}/` | só o mestre |
| `POST` | `/api/campaigns/{id}/leave/` | jogador (o mestre não sai da própria mesa) |
| `GET` `POST` | `/api/characters/` | ver: os visíveis das suas campanhas, mais os seus; criar: mestre |
| `GET` | `/api/characters/{id}/` | mestre, jogadores (se visível) e o dono |
| `PATCH` | `/api/characters/{id}/` | mestre: a ficha toda · dono: só `hp_current` e `sp_current` |
| `DELETE` | `/api/characters/{id}/` | só o mestre |
| `GET` `POST` | `/api/characters/{id}/bars/` | ver: quem vê a ficha; criar: mestre |
| `PATCH` | `/api/characters/{id}/bars/{bar_id}/` | mestre: tudo · dono: só `current` |
| `DELETE` | `/api/characters/{id}/bars/{bar_id}/` | só o mestre |
| `GET` | `/api/characters/{id}/slots/` | quem vê a ficha |
| `PUT` | `/api/characters/{id}/slots/{posição}/` | só o mestre — corpo `{"item": id}` ou `{"item": null}` |
| `GET` `POST` | `/api/npcs/` | ver: os seus, pelas regras abaixo; criar: mestre |
| `GET` | `/api/npcs/{id}/` | mestre sempre; jogador só se visível **e** vinculado a um personagem dele |
| `PATCH` `DELETE` | `/api/npcs/{id}/` | só o mestre |
| `GET` `PUT` | `/api/npcs/{id}/slots/{posição}/` | só o mestre |
| `GET` `POST` `PATCH` `DELETE` | `/api/npcs/{id}/bars/...` | só o mestre |
| `GET` `POST` | `/api/items/` | ver: os das suas campanhas; criar: mestre |
| `PATCH` `DELETE` | `/api/items/{id}/` | só o mestre |

## Escopo: por que 404 e não 403

O filtro por campanha está no `get_queryset`, não na permissão. Pedir `/api/campaigns/7/` de uma mesa que não é sua devolve **404**, não 403.

A diferença não é cosmética: um 403 confirmaria que a campanha 7 existe. Quem estivesse varrendo ids aprenderia o tamanho e a numeração do banco sem nunca ver um dado. Fora do queryset, o id simplesmente não existe.

## Papéis

As regras vêm de `api/permissions.py`, que é o mesmo conjunto aplicado pelo painel HTML. A API não tem uma segunda versão delas — duas cópias de uma regra de acesso viram duas regras diferentes na primeira vez que alguém corrigir só uma.

- **mestre da campanha**: manda em tudo que pertence a ela;
- **jogador da campanha**: vê o que está marcado como visível;
- **jogador atribuído a um personagem**: mexe nos status dele — vida, energia, barras — e não na ficha. Isso não é uma lista de campos conferida na mão dentro do `update`: é um serializer separado (`CharacterStatusSerializer`) que a view escolhe pelo papel de quem pediu. Mandar `name` num PATCH de jogador não dá erro; o campo simplesmente não existe naquele serializer e é ignorado.
- **NPC** é do mestre. O jogador só enxerga um NPC visível e vinculado a um personagem dele.

## Item de outra campanha

`PUT /api/characters/{id}/slots/{posição}/` recusa item que não seja da campanha do personagem, com 400. Sem essa checagem o endereço devolveria nome e imagem do material de outra mesa para quem chutasse ids de item.

## Interface navegável

Com `DEBUG=True` o DRF serve a interface HTML navegável, útil para conferir a API na mão. Em produção fica só JSON — a navegável é uma superfície a mais sem ganho nenhum para um cliente de verdade.
