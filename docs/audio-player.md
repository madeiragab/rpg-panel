> 🇬🇧 **English** · 🇧🇷 [Português](audio-player.pt-BR.md)

# Campaign audio player

A floating widget on the campaign and character screens. The master builds the
soundtrack from YouTube links, drags to reorder and controls what plays;
everyone at the table hears it together.

## What travels (and what does not)

**No audio leaves the server.** What lives in the database is one row saying
*which track*, *from what second*, and *whether it is playing*. Each browser
plays the video on its own from that.

That is why the player fits a free plan: five people on the same soundtrack cost
the server five lines of JSON, not five audio streams.

## The thumbnail is visible on purpose

The YouTube API Terms do not allow hiding the player or separating audio from
video. A one-pixel iframe would work technically and could cost the account.

So the widget shows the video at 200×113, with the panel's controls around it.
The size lives in the widget's own CSS (`templates/hud/_audio_player.html`), in
one place.

## Everyone hears at their own volume

Volume and mute are local, and stay local on purpose: the master controls *what*
plays, not *how loud* each person hears it. Someone on headphones and someone on
speakers should not depend on each other.

## The mandatory click — everyone's

No browser lets audio start without a human gesture. That is why the
**"Entrar no áudio"** button exists, and it is for everyone: the master is no
exception, because their browser asks for the same click.

The master's click on the controls counts as that gesture — hitting ▶ joins the
audio too, so there are never two buttons to press.

There is no way around it; it is a browser rule, not a project choice.

## Who is listening

Joining the audio puts the person's **character** into a row of portraits inside
the widget. That is the answer to the click: you click, and you see yourself
there.

The character sheet comes before the avatar because during a session people
*are* their characters. Anyone without a sheet at the table — the master first
among them — shows up as their profile avatar, and so does anyone whose sheet is
hidden: the soundtrack must not become a side door to a name the master has not
revealed yet.

### Presence is a timestamp, not a switch

`AudioListener` stores campaign, person and `last_seen`. There is no
"is listening" field.

The reason is that browsers have no reliable way to say they closed: tabs die,
laptops sleep, connections drop. A switch written to the database would leave
people listening forever at a table that ended. So whoever is in the audio
repeats "still here", and anyone past **45 seconds** without saying so drops out
of the row on their own. The row stays in the database; it just stops counting.

A closing tab still tries to say so immediately, with a `keepalive` fetch — that
is what lets a request leave a page that is dying. When it cannot, the stale
`last_seen` handles it.

### The heartbeat is the polling

There is no separate timer for presence. Whoever is in the audio fetches state
from the presence endpoint, which returns the same body and stamps `last_seen`
along the way — one request where there were two.

At a table of six that is the difference between 60 and 36 requests a minute. On
a free-tier host that arithmetic is what decides whether the panel stays up
mid-session, and that comes before the elegance of one endpoint per concern.

Heartbeats do **not** become Pusher events either: it would be over 2,000 pushes
an hour to say nothing changed. Only joins and leaves are published.

## Synchronisation

`PlaybackState` stores `position_seconds` **and** `updated_at`. The position
alone would not be enough: it is the position *at that instant*. Whoever opens
the page mid-song adds the elapsed time and joins where the table is, not where
the song was when the master hit play.

And the position does not sit still between responses: the client adds the time
elapsed since it received them, measured with `performance.now()`. The system
clock will not do — user clocks are off by minutes, and a minute of error here
would become a jump into the middle of the song every second.

That lets the browser compare itself against the table **every second**, without
talking to the server. It only seeks when the gap exceeds 1.5 seconds:
correcting anything smaller would sound like a stutter on every pass, and nobody
at an RPG table notices a second and a half of ambient music.

### Ads

The ad belongs to the viewer, not to the table: YouTube picks on its own, and
anyone with Premium sees none. There is no way to even that out through the
embed — and hiding the player to dodge the Terms would cost the account.

What can be guaranteed is the reunion. During an ad YouTube reports the *ad's*
time and ignores `seekTo`; unhandled, whoever is watching an ad would get one
pointless jump per second. So attempts are spaced 2.5 seconds apart: during the
ad they are rare and harmless, and the moment it ends the first one lands on its
feet, at the exact second the rest of the table is on.

The same path covers buffering, a hidden tab (where browsers throttle timers)
and a laptop that slept — returning to the tab triggers an immediate fetch
instead of waiting for the next tick.

### When the master disappears

The master's tab sends a heartbeat every 15 seconds. After **90 seconds**
without news the state goes *cold*: clients stop advancing the position and the
widget shows paused.

Without that, a hastily closed tab would leave the table playing on its own a
soundtrack the master stopped hearing half an hour ago.

## Real time: Pusher, with polling underneath

PythonAnywhere does not serve WebSockets. The push comes from outside: Django
publishes to Pusher, browsers listen on the campaign's channel.

**Pusher is an accelerator, not the mechanism.** The database is the source of
truth and the widget polls every 10 seconds regardless. With no key configured,
with Pusher down, or with the free plan exhausted, the player keeps working — it
just stops being instant. That is why `realtime.publicar` swallows exceptions: a
network failure there must not turn an already-saved command into a 500.

### Private channel

The channel is `private-campanha-{id}-audio`. A public channel would be simpler,
but the Pusher key goes to the browser — it is public by design — and anyone
holding it could subscribe to any table's channel and follow other people's
soundtrack.

With `private-`, Pusher asks our server before letting anyone in.
`POST /api/pusher/auth/` answers, applying the same rule as everything else: if
you are in the campaign, you are in.

## The bridge between page and API

The page is session-authenticated; the API only speaks JWT. Instead of accepting
a cookie on the API — which would bring CSRF back through an unwatched door —
the page asks `GET /audio/token/` for a 15-minute access token and uses it on
its calls.

There is no privilege escalation: the user could obtain that same token by
sending their own password to `/api/token/`. The refresh token never goes
through there, because a seven-day refresh sitting in the HTML would be far
worse than an access token that dies on its own.

## Endpoints

All under the campaign, with the usual rules — reading is for participants,
writing is for the master.

Presence is the one exception, and a narrow one: a person changes their own
presence and nothing else. That is why it does not go through the viewset's
`get_object`, which would demand write permission on the campaign and lock
players out of their own audio.

| Method | Endpoint | Who may |
|---|---|---|
| `GET` | `/api/campaigns/{id}/audio/` | master and players |
| `POST` | `/api/campaigns/{id}/audio/presence/` | participants — body `{"listening": true\|false}` |
| `POST` | `/api/campaigns/{id}/audio/tracks/` | master — body `{"url": "..."}` |
| `DELETE` | `/api/campaigns/{id}/audio/tracks/{track_id}/` | master |
| `PATCH` | `/api/campaigns/{id}/audio/order/` | master — body `{"order": [ids]}` |
| `PATCH` | `/api/campaigns/{id}/audio/state/` | master |
| `POST` | `/api/pusher/auth/` | participants of the channel's campaign |

### Why reordering sends the whole list

`{"order": [3, 1, 2]}`, not "move track 3 to position 1". Two quick drags with
the second form would cross and leave the queue in something nobody asked for.
The server also checks that the list matches the campaign's tracks exactly — if
it does not, the screen is stale and the request is refused.

### Accepted links

`api/youtube.py` normalises any format down to the eleven-character id:
`watch?v=`, `youtu.be/`, `shorts/`, `embed/`, `music.youtube.com`, with
playlists and timestamps trailing behind, or the bare id. Without it the same
song would enter the list four times depending on which YouTube button the
master used to copy it.

## Configuration

Four environment variables, all optional:

| Variable | What for |
|---|---|
| `PUSHER_APP_ID` | app id from the Pusher dashboard |
| `PUSHER_KEY` | **public** key — it goes to the browser, that is by design |
| `PUSHER_SECRET` | secret; **never leaves the server** |
| `PUSHER_CLUSTER` | the app's cluster (`mt1`, `us2`, `eu`…). Default: `mt1` |

Without them the player runs on polling. To turn real time on: create a free
Pusher account, create a Channels app, copy the four values into the host's
environment (on PythonAnywhere, the WSGI file or the Web tab variables).

Pusher's free plan gives 200k messages a day and 100 concurrent connections —
wide margin for any RPG table.
