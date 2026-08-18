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

## The player's mandatory click

No browser lets audio start without a human gesture. That is why players see an
**"Entrar no áudio"** button — it exists purely so there is a click before the
first play. After that the master drives everything.

There is no way around it; it is a browser rule, not a project choice.

## Synchronisation

`PlaybackState` stores `position_seconds` **and** `updated_at`. The position
alone would not be enough: it is the position *at that instant*. Whoever opens
the page mid-song adds the elapsed time and joins where the table is, not where
the song was when the master hit play.

The client only seeks when the gap exceeds 2.5 seconds. Correcting anything
smaller would sound like a stutter on every check, and nobody at an RPG table
notices two seconds of ambient music.

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

| Method | Endpoint | Who may |
|---|---|---|
| `GET` | `/api/campaigns/{id}/audio/` | master and players |
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
