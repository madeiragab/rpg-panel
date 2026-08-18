> 🇬🇧 **English** · 🇧🇷 [Português](api.pt-BR.md)

# REST API

The API lives under `/api/` and is an **addition, not a replacement**: the HTML
panel keeps working exactly as before, on Django sessions. API clients use JWT
and no cookie.

That is deliberate. Accepting a session cookie on a writing API would bring the
CSRF problem back through a door nobody is watching, so `SessionAuthentication`
is not in the DRF authentication list.

## Authentication

Three endpoints, all throttled at ten per minute per IP:

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/api/token/` | Trades `username` and `password` for an `access` + `refresh` pair |
| `POST` | `/api/token/refresh/` | Trades a valid `refresh` for a fresh `access` (and a fresh `refresh`) |
| `POST` | `/api/token/logout/` | Sends the given `refresh` to the blacklist |

```bash
curl -X POST https://galibinja.pythonanywhere.com/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "mestre", "password": "..."}'
```

The response carries both tokens. The `access` goes on every later request:

```bash
curl https://galibinja.pythonanywhere.com/api/campaigns/ \
  -H "Authorization: Bearer <access>"
```

### Lifetimes and rotation

- **access: 15 minutes.** Short because it cannot be revoked — while it is
  valid, it is valid. Checking revocation per request would cost a database
  round trip on every call, which is exactly what JWT exists to avoid.
- **refresh: 7 days, rotating.** Each use returns a new refresh and blacklists
  the old one. A copied refresh only works until the owner uses theirs; from
  that point the copy gets a 401.

The blacklist is the `rest_framework_simplejwt.token_blacklist` app, which is
why it sits in `INSTALLED_APPS`: without it rotation issues a new token but
never invalidates the old one.

Logout kills the `refresh`, not the `access`. Someone signing out keeps up to
15 minutes of access on the token already in hand. That is the price of not
hitting the database per request; kicking someone out instantly would require a
revocation list consulted on every call, which is the opposite design.

## Resources

Everything below requires `Authorization: Bearer`. Lists are paginated 50 at a
time (`?page=`).

| Method | Endpoint | Who may |
|---|---|---|
| `GET` | `/api/me/` | any authenticated user (their own profile) |
| `PATCH` | `/api/me/` | the owner — `role` is read-only |
| `GET` `POST` | `/api/campaigns/` | read: yours; create: anyone (becomes master) |
| `GET` | `/api/campaigns/{id}/` | the campaign's master and players |
| `PATCH` `DELETE` | `/api/campaigns/{id}/` | master only |
| `POST` | `/api/campaigns/{id}/players/` | master only — body `{"user": id}` |
| `DELETE` | `/api/campaigns/{id}/players/{user_id}/` | master only |
| `POST` | `/api/campaigns/{id}/leave/` | players (the master does not leave their own table) |
| `GET` `POST` | `/api/characters/` | read: visible ones in your campaigns, plus yours; create: master |
| `GET` | `/api/characters/{id}/` | master, players (if visible) and the owner |
| `PATCH` | `/api/characters/{id}/` | master: the whole sheet · owner: only `hp_current` and `sp_current` |
| `DELETE` | `/api/characters/{id}/` | master only |
| `GET` `POST` | `/api/characters/{id}/bars/` | read: whoever sees the sheet; create: master |
| `PATCH` | `/api/characters/{id}/bars/{bar_id}/` | master: everything · owner: only `current` |
| `DELETE` | `/api/characters/{id}/bars/{bar_id}/` | master only |
| `GET` | `/api/characters/{id}/slots/` | whoever sees the sheet |
| `PUT` | `/api/characters/{id}/slots/{position}/` | master only — body `{"item": id}` or `{"item": null}` |
| `GET` `POST` | `/api/npcs/` | read: yours, by the rules below; create: master |
| `GET` | `/api/npcs/{id}/` | master always; a player only if visible **and** linked to one of their characters |
| `PATCH` `DELETE` | `/api/npcs/{id}/` | master only |
| `GET` `PUT` | `/api/npcs/{id}/slots/{position}/` | master only |
| `GET` `POST` `PATCH` `DELETE` | `/api/npcs/{id}/bars/...` | master only |
| `GET` `POST` | `/api/items/` | read: those of your campaigns; create: master |
| `PATCH` `DELETE` | `/api/items/{id}/` | master only |

## Scope: why 404 and not 403

The campaign filter lives in `get_queryset`, not in the permission. Asking for
`/api/campaigns/7/` on a table that is not yours returns **404**, not 403.

The difference is not cosmetic: a 403 would confirm that campaign 7 exists.
Anyone sweeping ids would learn the size and numbering of the database without
ever seeing a record. Outside the queryset, the id simply does not exist.

## Roles

The rules come from `api/permissions.py`, the same set the HTML panel applies.
The API does not hold a second version of them — two copies of an access rule
become two different rules the first time someone fixes only one.

- **campaign master**: rules everything that belongs to it;
- **campaign player**: sees whatever is marked visible;
- **player assigned to a character**: moves that character's status — health,
  energy, bars — and not the sheet. This is not a field list checked by hand
  inside `update`: it is a separate serializer (`CharacterStatusSerializer`)
  that the view picks from the caller's role. Sending `name` in a player's
  PATCH raises no error; the field just does not exist on that serializer and
  is ignored.
- **NPCs** belong to the master. A player only sees an NPC that is visible and
  linked to one of their characters.

## Item from another campaign

`PUT /api/characters/{id}/slots/{position}/` refuses an item that does not
belong to the character's campaign, with a 400. Without that check the endpoint
would hand back the name and image of another table's material to anyone
guessing item ids.

## Browsable interface

With `DEBUG=True` DRF serves its browsable HTML interface, handy for poking at
the API by hand. Production is JSON only — the browsable renderer is one more
surface with no gain for a real client.
