> 🇧🇷 [Português](README.pt-BR.md) · 🇬🇧 **English**

# RPG Panel 🎲

[![ci](https://github.com/madeiragab/rpg-panel/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/madeiragab/rpg-panel/actions/workflows/ci.yml)

RPG Panel is a private web panel for managing tabletop RPG campaigns.
It centralizes campaigns, players, characters, NPCs and inventory with clear
role separation between game masters and players.

This is **not a public product**, **not a game engine**, and **not a complete RPG system**.
It exists to replace scattered PDFs, notes, and spreadsheets when a campaign grows.

## Documentation

| Doc | What's inside |
|---|---|
| [docs/architecture.md](docs/architecture.md) | App layout, request flow, permission model, signals |
| [docs/data-model.md](docs/data-model.md) | Every model, relationship and invariant |
| [docs/deployment.md](docs/deployment.md) | Environment variables, deploy, static/media files |

---

## Purpose

Provide a simple and consistent way to organize RPG campaign data:

- Campaigns
- Players
- Characters and NPCs
- Inventory
- Access control (master vs player)

No rule automation.
No dice engine.
No attempt to replace the tabletop experience.

---

## Roles

Roles are **per campaign**, not global: the same account is the master of the
campaigns it created and a player in the campaigns it was invited to.

### Game Master
- Create, edit, and delete campaigns
- Manage players inside a campaign
- Create and assign characters and NPCs
- Manage items and inventory
- Reassign characters between players
- Toggle character/NPC visibility for players
- Preview the campaign as a player with `?mode=player`

### Player
- View campaigns they belong to
- View visible campaign characters
- Fully access only their assigned character
- Manage their own profile

---

## Features

### Campaigns
- Create, edit, and delete campaigns
- Optional banner image per campaign
- Master is automatically added as a player
- Safe deletion with exact-name confirmation
- Players can leave a campaign

### Players
- Add players via live search (nickname, name, or username)
- List all campaign participants
- Controlled removal by the master

### Characters
- Characters always belong to a campaign
- Each character is assigned to a player
- Player reassignment via dropdown
- Central character detail view
- Character navigation bar for quick switching
- Visibility toggle (hide work-in-progress characters from players)

### NPCs
- Campaign-scoped NPCs with the same sheet structure as characters
- Hidden from players by default (`visible = False`)
- Can be linked to a character (familiars, companions, mounts)

### Character sheets
Each character and NPC supports:
- **Bars** — custom named resources with current/max values and a color
  (HP and SP were migrated into this generic system)
- **Attributes** — free-form name/value pairs (Strength, Dexterity, …)
- **Skills** — name plus optional value
- **Abilities** — named abilities
- All of them are user-ordered via an `order` field

### Inventory
- Slot-based inventory system, rendered as a 4-column grid
- Configurable capacity per character/NPC (default 16 slots)
- Slots are created automatically and kept in sync when capacity changes
- Empty slots are guaranteed, so the UI never has holes

### User Accounts
- Registration and authentication
- Password reset by e-mail with expiring single-use tokens
- User profile with display name, nickname (used for search) and avatar

---

## Tech Stack

### Backend
- Python 3.11
- Django 5.2 LTS
- SQLite (development)
- Pillow (image handling)
- Gunicorn + WhiteNoise (production)

### Frontend
- Django Templates
- CSS (glass-morphism style)
- Vanilla JavaScript (inventory drag/drop, live search, AJAX bar updates)

No SPA.
No frontend frameworks.
No unnecessary dependencies.

---

## Running locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on Linux)
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000.

For local development you can run with `DEBUG=True`; a development-only
`SECRET_KEY` fallback is used automatically. **In production both
`DJANGO_SECRET_KEY` and the e-mail credentials must be set** — see
[docs/deployment.md](docs/deployment.md).

---

## Project Structure

```text
rpg-panel/
├─ manage.py
├─ Procfile                    → gunicorn entry point for deploy
├─ nixpacks.toml               → build config
├─ requirements.txt
│
├─ rpg_panel/                  → project configuration
│  ├─ settings.py              → env-driven settings (secret key, e-mail, DB)
│  ├─ urls.py                  → root URLs + media serving
│  ├─ wsgi.py / asgi.py
│
├─ hud/                        → the single application
│  ├─ models.py                → Campaign, Character, NPC, Item, slots, bars…
│  ├─ views.py                 → all views (pages + JSON endpoints)
│  ├─ forms.py                 → ModelForms for every editable entity
│  ├─ urls.py                  → app routes
│  ├─ admin.py                 → Django admin registration
│  ├─ context_processors.py    → injects the user role into every template
│  ├─ templatetags/            → custom template filters
│  ├─ migrations/
│  └─ static/hud/              → styles.css, inventory.js, drag.js
│
└─ templates/
   ├─ base.html
   ├─ hud/                     → dashboards, campaign/character/NPC pages
   └─ registration/            → login, register, password reset
```

---

Made by **Gabriel Madeira** · [github.com/madeiragab](https://github.com/madeiragab)
