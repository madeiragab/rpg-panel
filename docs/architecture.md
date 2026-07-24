# Architecture

RPG Panel is a deliberately small Django project: **one project package**
(`rpg_panel`) and **one application** (`hud`). There is no API layer and no
SPA — pages are server-rendered Django templates, and the few interactive
parts (inventory, bars, player search) call small JSON endpoints in the same
views module.

```text
Browser
  │  HTML pages                          │  fetch() JSON
  ▼                                      ▼
hud/urls.py ─────────────► hud/views.py ─────────────► hud/models.py
                              │                            │
                              ├─ hud/forms.py              └─ signals
                              └─ templates/
```

## Permission model

This is the part worth understanding, because it is **not** a global role
system.

`UserProfile.role` exists and is kept for backwards compatibility, but
authorization is decided **per campaign, per request**:

```python
is_master = campaign.master == request.user
is_player = request.user in campaign.players.all()
```

Consequences:

- The same account is master of the campaigns it created and a player in the
  campaigns it was invited to — no separate accounts needed.
- Every view that touches campaign data recomputes these two flags and
  returns `HttpResponseForbidden` when both are false.
- Templates receive `is_master` and render editing controls only for the
  master.

### Player preview mode

Appending `?mode=player` to a campaign or character URL forces `is_master`
to `False` for that request. This lets the master see exactly what their
players see (including what is hidden by the `visible` flag) without
logging out.

> `_user_is_master()` in `views.py` is a **legacy stub that always returns
> `True`** — it predates the per-campaign model and is only referenced by
> old templates. Do not use it for new checks.

### Character-level access

`character_detail` is stricter than campaign access:

| Situation | Result |
|---|---|
| User is the campaign master | Full edit access |
| User is in the campaign, or the character is assigned to them | Read access |
| Character has no campaign (legacy data) | Falls back to `created_by` / `assigned_to` |
| Neither | `403 Forbidden` |

## Signals (`hud/models.py`)

Three `post_save` receivers keep the data consistent without scattering
setup code across views:

| Signal | Effect |
|---|---|
| `User` created | Creates the matching `UserProfile` |
| `Character` created | Calls `ensure_slots()` to build the inventory grid |
| `NPC` created | Same for NPC inventory |

`ensure_slots()` is idempotent and also runs after the master edits a
sheet: it bulk-creates missing slots and deletes slots beyond the new
capacity, so shrinking an inventory never leaves orphan positions.

## Views: pages vs JSON endpoints

`hud/views.py` mixes two kinds of view, distinguishable by return type:

- **Page views** return `HttpResponse` (rendered templates):
  `master_dashboard`, `player_dashboard`, `campaign_detail`,
  `character_detail`, `npc_detail`, `character_list`, `user_page`,
  `register`, `forgot_password`, `reset_password`.
- **JSON endpoints** return `JsonResponse` and are called by the page's
  JavaScript — all of them are `@require_POST` except the search:
  `search_players`, `assign_slot`, `modify_hp`, `modify_sp`, `modify_bar`,
  `add_character_bar`, `delete_bar`, `add_npc_bar`, `modify_npc_bar`,
  `delete_npc_bar`, `toggle_character_visibility`, `toggle_npc_visibility`.

Multi-form pages (like `character_detail`, which edits the sheet, skills,
abilities and attributes) dispatch on a hidden `form_type` field and use
Django form `prefix`es to keep field names from colliding.

## Password reset

Django's built-in reset flow was replaced by a custom one so the e-mail
copy and the token lifetime stay under project control:

1. `forgot_password` looks up the account and creates a
   `PasswordResetToken` with an expiry timestamp.
2. The link is e-mailed via Gmail SMTP (credentials from environment
   variables — see [deployment.md](deployment.md)).
3. `reset_password` validates the token (exists, not `used`, not expired),
   sets the new password and marks the token as used.

The confirmation screen shows a **masked** e-mail (`_mask_email`) so the
page never reveals the full address of an account.

## Frontend assets

`hud/static/hud/` holds three files, loaded by the templates that need
them:

- `styles.css` — the glass-morphism theme;
- `inventory.js` — slot rendering and item assignment;
- `drag.js` — drag-and-drop between inventory slots.

Static files are served by **WhiteNoise** in production with hashed,
compressed names (`CompressedManifestStaticFilesStorage`), so
`collectstatic` must run on every deploy.
