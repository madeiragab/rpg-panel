# RPG Panel 🎲

RPG Panel is a private web panel for managing tabletop RPG campaigns.  
It centralizes campaigns, players, characters, and inventory with clear role separation between game masters and players.

This is **not a public product**, **not a game engine**, and **not a complete RPG system**.  
It exists to replace scattered PDFs, notes, and spreadsheets when a campaign grows.

---

## Purpose

Provide a simple and consistent way to organize RPG campaign data:

- Campaigns
- Players
- Characters
- Inventory
- Access control (master vs player)

No rule automation.  
No dice engine.  
No attempt to replace the tabletop experience.

---

## Roles

### Game Master
- Create, edit, and delete campaigns
- Manage players inside a campaign
- Create and assign characters
- Manage items and inventory
- Reassign characters between players

### Player
- View campaigns they belong to
- View all campaign characters
- Fully access only their assigned character
- Manage their own profile

---

## Features

### Campaigns
- Create, edit, and delete campaigns
- Optional banner image per campaign
- Master is automatically added as a player
- Safe deletion with exact-name confirmation

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

### Inventory
- Slot-based inventory system
- Configurable capacity per character
- Guaranteed empty slots for consistent UI
- Structure prepared for future drag-and-drop

### User Accounts
- Registration and authentication
- User profile with:
  - Display name
  - Nickname (used for search)
  - Avatar image

---

## Tech Stack

### Backend
- Python 3.11
- Django 5.x
- SQLite (development)
- Pillow (image handling)

### Frontend
- Django Templates
- CSS (glass-morphism style)
- Vanilla JavaScript

No SPA.  
No frontend frameworks.  
No unnecessary dependencies.

---

## Project Structure

rpg-panel/
├── hud/ # Main Django app
│ ├── models.py
│ ├── views.py
│ ├── forms.py
│ ├── urls.py
│ ├── templates/
│ └── static/
├── rpg_panel/ # Project settings
├── media/ # Uploaded files
├── static/ # Collected static files
├── manage.py
└── README.md


---

## Core Models

### Campaign
- One master
- Multiple players
- Characters and items depend on the campaign

Master and players are intentionally separated to enforce permissions.

---

### Character
- Always linked to a campaign
- Always assigned to a player
- Configurable inventory capacity

The `ensure_slots()` method guarantees consistent inventory display.

---

### InventorySlot
- One slot equals one position
- Item is optional
- Designed for clear visual representation

---

### UserProfile
Explicit extension of Django’s `User` model to support:
- Searchable nickname
- Avatar
- Consistent display name across the UI

---

## Request Flow

Campaign actions are handled through a single view using a `form_type` parameter.

Example:


POST /hud/campaign/<id>/
form_type = character


This keeps logic centralized, predictable, and easy to maintain.

---

## Non-Goals

- RPG rule engine
- Public SaaS platform
- Marketplace
- Real-time multiplayer
- Commercial product

---

## Possible Future Improvements

Only if the project grows naturally:
- Character attributes
- Session logs
- Initiative tracking
- Simple action history
- UI refinements

No feature inflation.

---

## Final Notes

This project exists because:
- PDFs break
- Spreadsheets become chaos
- Long RPG campaigns need minimal structure

Nothing more.
