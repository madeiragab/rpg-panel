# RPG Panel 🎲

A modern, role-based web application for managing tabletop RPG campaigns, characters, and inventory in real-time. Built with Django, this platform provides game masters and players with an intuitive interface to create campaigns, manage characters, and interact collaboratively within a shared game world.

## 📋 Table of Contents

- [Overview](#overview)
- [Why RPG Panel?](#why-rpg-panel)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [Project Architecture](#project-architecture)
- [Data Models](#data-models)
- [API Endpoints](#api-endpoints)
- [Future Improvements](#future-improvements)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

**RPG Panel** is a web-based campaign management system designed to streamline the organization and execution of tabletop RPG sessions. Whether you're running Dungeons & Dragons, Pathfinder, or any custom RPG system, RPG Panel provides the tools to manage campaigns, characters, items, and player interactions seamlessly.

The application enforces a clear role-based permission model:
- **Game Masters (Masters)**: Full control over campaign content, character assignments, and player management
- **Players**: Read-only access to campaign data with the ability to view and manage only their own characters

---

## Why RPG Panel?

### Problem Statement
Traditional RPG sessions often lack centralized management of:
- Character sheets and inventory
- Campaign information and player assignments
- Real-time collaboration between game master and players
- Visual organization of campaign details

### Solution
RPG Panel solves these problems by providing:

1. **Centralized Campaign Hub**
   - Single source of truth for all campaign data
   - Campaign banners as visual identifiers
   - Organized character and item management

2. **Role-Based Access Control**
   - Game masters have administrative control
   - Players have safe, read-only access to necessary information
   - Clear separation of responsibilities

3. **Intuitive UI/UX**
   - Glass-morphism design for modern aesthetics
   - Character navigation bar for quick switching
   - Responsive design for desktop and mobile
   - Transparent panels that showcase campaign visuals

4. **Player Management**
   - Live search for adding players to campaigns
   - Automatic character assignment to players
   - Player reassignment via dropdown interface
   - Player profile customization with avatars

5. **Inventory System**
   - Character inventory with configurable capacity
   - Item creation and management
   - Slot-based inventory system (visual representation)

6. **User Accounts**
   - Registration with full name breakdown (first name, last name, nickname)
   - Profile customization with avatar uploads
   - User authentication and authorization

---

## Key Features

### For Game Masters
- ✅ **Campaign Management**: Create, edit, and delete campaigns with custom banners
- ✅ **Character Management**: Create characters and assign them to players
- ✅ **Item Management**: Create and manage campaign items
- ✅ **Player Management**: Search and add players to campaigns with live typeahead
- ✅ **Character Reassignment**: Reassign characters to different players via dropdown
- ✅ **Campaign Overview**: Dashboard showing all managed campaigns
- ✅ **Exact-Name Deletion**: Confirm destructive actions by typing campaign names
- ✅ **Character Navigation**: Quick-access navbar showing all campaign characters

### For Players
- ✅ **Campaign Discovery**: View all campaigns they belong to as visually appealing cards
- ✅ **Character Viewing**: Browse all campaign characters with read-only access
- ✅ **Character Details**: View full character sheets for assigned characters
- ✅ **Player List**: See all players in the campaign
- ✅ **Profile Management**: Customize profile with avatar and nickname
- ✅ **Inventory Viewing**: See assigned character's inventory

### General Features
- 🎨 **Glass-Morphism Design**: Modern UI with backdrop filters and transparency
- 🖼️ **Campaign Banners**: Upload custom banner images that serve as campaign backgrounds
- 🔐 **Secure Authentication**: Django's built-in user authentication system
- 📱 **Responsive Design**: Works on desktop and mobile devices
- ⚡ **Fast Search**: Live player search with 200ms debounce for performance
- 🎭 **User Avatars**: Custom profile pictures with fallback to default

---

## Tech Stack

### Backend
- **Framework**: Django 5.1.3
- **Language**: Python 3.11.14
- **Database**: SQLite (local) / MySQL (production ready)
- **Image Processing**: Pillow 10.0.0

### Frontend
- **Templating**: Django Template Language (DTL)
- **Styling**: CSS3 with Glass-Morphism
- **Interactivity**: Vanilla JavaScript (no heavy dependencies)
- **Features**: Dynamic search, tab switching, form toggling

### Environment
- **Package Manager**: Conda
- **Version Control**: Git

---

## Installation

### Prerequisites
- Python 3.11+ 
- Conda or pip
- Git

### Step 1: Clone the Repository
```bash
git clone https://github.com/yourusername/rpg-panel.git
cd rpg-panel
```

### Step 2: Create Virtual Environment
```bash
conda create -n rpg-panel python=3.11
conda activate rpg-panel
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Create Database
```bash
python manage.py migrate
```

### Step 5: Create Superuser (Admin)
```bash
python manage.py createsuperuser
```

### Step 6: Run Development Server
```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` in your browser.

---

## Configuration

### Environment Variables
Create a `.env` file in the project root (for production):

```env
DEBUG=False
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=mysql://user:password@localhost/rpg_panel
```

### Settings File (`rpg_panel/settings.py`)

**Development Mode:**
```python
DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
```

**Production Mode:**
```python
DEBUG = False
ALLOWED_HOSTS = ['yourdomain.com']
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

### Static Files Configuration
```python
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

### Allowed File Types for Uploads
- Images: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.avif`
- Max file size: 5MB (configurable)

---

## Usage Guide

### For Game Masters

#### 1. Create a Campaign
1. Navigate to Master Dashboard (`/hud/master/`)
2. Click "Criar Campanha" (Create Campaign)
3. Fill in campaign name and description
4. Upload a banner image (optional, used as campaign background)
5. Click "Criar"
6. **Automatically added as player** to your own campaign

#### 2. Add Players to Campaign
1. Open campaign detail page
2. Navigate to "Jogadores" (Players) tab
3. Search for players by:
   - Nickname (apelido)
   - Display name
   - Username
4. Click search result to add instantly
5. Page reloads to show updated player list

#### 3. Create Characters
1. Open campaign detail page
2. Navigate to "Personagens" (Characters) tab
3. Click "+" button to open character creation form
4. Fill in character details:
   - Name
   - Image (optional)
   - Assigned Player (required, filtered to campaign players)
5. Set inventory capacity (number of slots)
6. Click "Criar"

#### 4. Manage Items
1. Open campaign detail page
2. Navigate to "Itens" (Items) tab
3. Click "+" button to create item
4. Fill in item name and image
5. Items available for assignment to character inventory

#### 5. Edit Campaign
1. Click the pencil icon (✏️) on campaign page
2. Update campaign name, description, or banner
3. Click "Salvar" (Save)
4. Changes reflect immediately

#### 6. Delete Campaign
1. Click pencil icon to open edit panel
2. Scroll to "Excluir Campanha" (Delete Campaign) section
3. Type exact campaign name to confirm
4. Click "Excluir" (Delete)
5. **Cascading delete**: All characters and items deleted automatically

#### 7. Reassign Characters
1. Open character detail page
2. Below player avatar, click dropdown arrow (▼)
3. Select new player from list
4. Click "Alterar Jogador" (Change Player)
5. Character reassignment reflected immediately

#### 8. Character Navigation
- Character navbar appears below topbar showing all campaign characters
- Click any character avatar to instantly switch to that character's sheet
- Useful for quickly reviewing all characters in campaign

### For Players

#### 1. View Campaigns
1. Log in and navigate to Player Dashboard (`/hud/player/`)
2. See all campaigns you belong to as cards
3. Each card shows:
   - Campaign banner
   - Campaign name
   - Campaign description (truncated)
   - Game master's name
4. Click any card to open campaign

#### 2. View Campaign Details
1. Click campaign card to open campaign detail
2. Two tabs available:
   - **Personagens** (Characters): All campaign characters
   - **Jogadores** (Players): All campaign players

#### 3. Access Your Character
1. In "Personagens" tab
2. Find your assigned character (click "Ver Meu" button)
3. View character sheet in read-only mode
4. See character stats, inventory, and assignments

#### 4. Manage Profile
1. Click user avatar in topbar
2. Navigate to profile page
3. Update:
   - Nickname (apelido)
   - Email
   - Avatar image
   - Password (optional)
4. Changes saved immediately

---

## Project Architecture

### Directory Structure
```
rpg-panel/
├── hud/                          # Main Django app
│   ├── migrations/               # Database migration history
│   ├── templates/
│   │   ├── base.html             # Main layout template
│   │   ├── role_choice.html       # Role selection (master/player)
│   │   ├── hud/
│   │   │   ├── master_dashboard.html
│   │   │   ├── player_dashboard.html
│   │   │   ├── campaign_detail.html
│   │   │   ├── character_detail.html
│   │   │   └── user_page.html
│   │   └── registration/
│   │       ├── register.html
│   │       └── login.html
│   ├── static/hud/
│   │   ├── styles.css            # Main stylesheet
│   │   ├── inventory.js          # Inventory management
│   │   ├── character-navbar.js   # Character navigation
│   │   └── drag.js               # Drag-drop utilities
│   ├── admin.py                  # Django admin configuration
│   ├── context_processors.py     # Template context helpers
│   ├── forms.py                  # Django forms (models and validation)
│   ├── models.py                 # Data models
│   ├── urls.py                   # URL routing
│   └── views.py                  # View logic and handlers
├── rpg_panel/                    # Django project settings
│   ├── settings.py               # Configuration
│   ├── urls.py                   # Root URL configuration
│   ├── asgi.py                   # ASGI configuration
│   └── wsgi.py                   # WSGI configuration
├── media/                        # User uploads (avatars, campaign banners, etc.)
├── static/                       # Collected static files (production)
├── manage.py                     # Django management script
├── db.sqlite3                    # Development database
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

### Request Flow

#### Campaign Detail View
The `campaign_detail` view handles multiple actions via `form_type` dispatch:

```
POST Request → campaign_detail() view
    ↓
Check form_type parameter:
    ├─ "campaign" → Update campaign (edit)
    ├─ "delete_campaign" → Delete campaign with confirmation
    ├─ "character" → Create character
    ├─ "item" → Create item
    ├─ "add_player" → Add player to campaign
    ├─ "remove_player" → Remove player from campaign
    └─ "change_player" → Reassign character to different player
    ↓
Validate permissions (is_master for edits)
    ↓
Execute appropriate action
    ↓
Redirect with updated context
```

---

## Data Models

### Campaign
```python
class Campaign(models.Model):
    master = ForeignKey(User, on_delete=CASCADE)
    players = ManyToManyField(User, related_name='campaigns_as_player')
    name = CharField(max_length=200)
    description = TextField()
    banner = ImageField(upload_to='campaigns/', blank=True, null=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

**Why separate `master` and `players`?**
- Master has administrative control (only master can edit)
- Players are tracked separately for collaborative access
- Enables permission checks: `if campaign.master == request.user`

### Character
```python
class Character(models.Model):
    campaign = ForeignKey(Campaign, on_delete=CASCADE)
    assigned_to = ForeignKey(User, on_delete=SET_NULL, null=True)
    name = CharField(max_length=200)
    image = ImageField(upload_to='characters/', blank=True, null=True)
    inventory_capacity = IntegerField(default=15)
    
    def ensure_slots(self):
        # Creates InventorySlot for each position up to capacity
        # Prevents inventory display inconsistencies
```

**Why `ensure_slots()`?**
- Guarantees all 15 slots (or custom capacity) display in UI
- Empty slots show as clickable + for item addition
- Prevents "missing slots" visual bugs

### InventorySlot
```python
class InventorySlot(models.Model):
    character = ForeignKey(Character, on_delete=CASCADE)
    position = IntegerField()  # 1-based slot position
    item = ForeignKey(Item, on_delete=SET_NULL, null=True, blank=True)
```

**Why slot-based inventory?**
- Visual representation (15 squares for 15 capacity)
- Easy drag-drop implementation (future)
- Natural RPG inventory metaphor

### UserProfile
```python
class UserProfile(models.Model):
    user = OneToOneField(User, on_delete=CASCADE)
    display_name = CharField(max_length=255)  # Combined "Firstname Lastname Nickname"
    nickname = CharField(max_length=100)      # Searchable alias
    avatar = ImageField(upload_to='avatars/', blank=True, null=True)
```

**Why extended User model?**
- Django's User model not flexible enough for RPG context
- Nickname enables fast search without username
- Display name provides formatted name across interface
- Avatar shows player identity visually

---

## API Endpoints

### Authentication
- `GET /accounts/login/` - Login page
- `GET /accounts/logout/` - Logout
- `POST /hud/register/` - User registration
- `GET /hud/me/` - User profile page
- `POST /hud/me/` - Update profile

### Campaign Management
- `GET /hud/` - Home (role choice)
- `GET /hud/master/` - Master dashboard
- `GET /hud/player/` - Player dashboard
- `GET /hud/campaign/<id>/` - Campaign detail
- `POST /hud/campaign/<id>/` - Campaign actions (create, edit, delete, add player, etc.)

### Character Management
- `GET /hud/character/<id>/` - Character detail
- `POST /hud/character/<id>/` - Character actions (update, reassign, add skill/ability)
- `POST /hud/character/<id>/delete/` - Delete character
- `GET /hud/campaign/<id>/search-players/?q=<query>` - Search players (JSON)

### Item Management
- `POST /hud/item/<id>/delete/` - Delete item

### Form Types (POST)
All campaign and character detail POSTs use `form_type` parameter:

```
form_type values:
- "campaign" → CampaignForm (edit)
- "delete_campaign" → Confirmation (exact name required)
- "character" → CharacterForm (create)
- "item" → ItemForm (create)
- "add_player" → Add player to campaign
- "remove_player" → Remove player from campaign
- "change_player" → Reassign character to player
- "skill" → CharacterSkillForm (add skill)
- "ability" → CharacterAbilityForm (add ability)
```

---

## Future Improvements

### Phase 1: Enhanced RPG Features
- [ ] Character attributes (STR, INT, WIS, DEX, CON, CHA)
- [ ] Automatic modifier calculations
- [ ] Level and experience system
- [ ] Character classes and races
- [ ] Dice roller (d20, d12, d100 with history)

### Phase 2: Campaign Features
- [ ] Campaign notes and timeline (master-only)
- [ ] Session history and log
- [ ] Status effects and buffs/debuffs with duration
- [ ] Initiative tracker
- [ ] Turn order management

### Phase 3: UI/UX Enhancements
- [ ] Animations and transitions
- [ ] Toast notifications for actions
- [ ] Loading spinners for async operations
- [ ] Mobile responsive modals
- [ ] Dark/light theme toggle
- [ ] Breadcrumb navigation

### Phase 4: Performance & Reliability
- [ ] Query optimization (select_related, prefetch_related)
- [ ] Database indexing for frequent queries
- [ ] Caching layer (Redis)
- [ ] Image optimization and CDN
- [ ] Unit and integration tests

### Phase 5: Security & Moderation
- [ ] Rate limiting on search and API endpoints
- [ ] Soft delete for campaigns (archive instead of destroy)
- [ ] Audit logging (who did what, when)
- [ ] Image sanitization for uploads
- [ ] File size validation and limits

### Phase 6: Deployment & DevOps
- [ ] Docker containerization
- [ ] GitHub Actions CI/CD
- [ ] Production database (PostgreSQL)
- [ ] AWS S3 for media storage
- [ ] Email notifications
- [ ] Background job queue (Celery)

---

## Contributing

### How to Contribute
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Coding Standards
- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add comments for complex logic
- Test features before submitting PR
- Update README if adding new features

---

## License

This project is licensed under the MIT License - see LICENSE file for details.

---

## Support

For questions, issues, or suggestions:
- Open an issue on GitHub
- Contact the development team
- Check the wiki for detailed guides

---

## Acknowledgments

Built with Django, Pillow, and Glass-Morphism CSS design principles.

Inspired by the needs of tabletop RPG communities for better campaign management tools.

---

**Happy Gaming! 🎲🎭**

Last Updated: December 2025
