# 🩸 Blood on the Clocktower — Storyteller Assistant Discord Bot

A Python Discord bot built with `discord.py` (v2.x) to help Storytellers run **Blood on the Clocktower** games effortlessly on Discord.

## ✨ Features

- **Zero-Config Smart Channel Discovery:** Works out-of-the-box with your existing Discord server without tedious channel-by-channel mapping:
  - Automatically finds your **Town Square** voice channel (by name or whichever channel the Storyteller is in) and treats its parent category as the **Day Category**.
  - Automatically finds your **Cabins / Night Category** (or creates one the first time you run Night).
  - Automatically tracks whoever clicks the Storyteller Panel buttons (or runs Storyteller commands) as the **Active Storyteller** for the session—so Storytellers who occasionally play as normal players don't need to add/remove roles.
- **Private Night Cabins (`/night`):**
  - Sends all active players **and the Storyteller** (so night-order timing stays hidden!) into individual, locked `🔒 Cabin • <Name>` voice channels.
  - Applies permission overwrites so each player can **only** see their own cabin—players cannot see other cabins or who the Storyteller is visiting and in what order.
  - Reuses each player's cabin across Night phases to avoid Discord API rate limits, and cleans them up on demand via `/setup delete-auto`.
- **Gather to Town Square (`/square`):**
  - Pulls all players from Whisper rooms and Night Cabins back to the Town Square.
- **Storyteller Floor (`🔇 Hush Square` / `🔊 Unhush All`):**
  - Server-mutes everyone in Town Square *except* the Storyteller so you can announce morning deaths or manage nominations cleanly.
  - Includes automatic safety nets that unmute everyone when starting a Day timer or sending players to Night Cabins.
- **1-Minute Fidelity Day Timers (`/timer start`):**
  - Broadcasts the countdown embed to your public **General Alert Text Channel** (even when triggered from a private `#storyteller` channel).
  - Updates every minute, posts a **1-minute warning** in chat, automatically gathers everyone back to the Town Square at `0:00`, and deletes expired timer messages to keep chat clean.
- **Interactive Storyteller Control Panel (`/panel`):**
  - Posts a persistent dashboard (ideal for a private `#storyteller` text channel) with one-click buttons for `☀️ Gather to Town Square`, `🌙 Send to Cabins`, `🔇 Hush Square`, `🔊 Unhush All`, quick timers (`8m`, `5m`, `3m`, `1m`, `+1m`, `Stop`), a `🧭 Visit Player Cabin` dropdown menu, and `📚 Player Help & Scripts`.
- **Player Resources (`/help`):**
  - Displays official links to the Base 3 Character Sheets & Almanacs (*Trouble Brewing*, *Bad Moon Rising*, *Sects & Violets*), the official BotC Wiki, Script Tool, and a quick-reference rules summary.

---

## 🛠️ Local Setup Guide (Step-by-Step)

### Step 1: Create & Configure the Discord Application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application** (top-right). Give it a name (e.g., `Clocktower Assistant`).
2. **Get Your Bot Token & Enable Intents:**
   - In the left sidebar, click **Bot** (puzzle-piece icon).
   - Under the **Token** section near the top, click **Reset Token**, confirm, and **copy the token** (this is your `DISCORD_TOKEN`—*not* the Application ID or Public Key on the General Information tab).
   - Scroll down on the same **Bot** page to **Privileged Gateway Intents** and toggle **ON**:
     - ✅ **Server Members Intent** *(Required so the bot can see who is in voice channels)*
   - Click **Save Changes**.
3. **Invite the Bot to Your Discord Server:**
   - In the left sidebar, click **OAuth2** and scroll down to **OAuth2 URL Generator**.
   - Under **Scopes**, check **BOTH** boxes:
     - ✅ `bot` *(Crucial: without `bot`, only slash commands are installed and the bot user won't join the server!)*
     - ✅ `applications.commands`
   - In the **Bot Permissions** box that appears below Scopes, check:
     - ✅ `Manage Roles` *(Also called "Manage Permissions" — required so the bot can make Night Cabins private to each player)*
     - ✅ `Manage Channels` *(Required to create/delete Night Cabins and `/setup auto-create`)*
     - ✅ `View Channels`
     - ✅ `Send Messages`
     - ✅ `Manage Messages` *(Optional/Recommended to cleanly delete timer alerts)*
     - ✅ `Embed Links`
     - ✅ `Connect`
     - ✅ `Mute Members` *(Required for `🔇 Hush Square` / `🔊 Unhush All`)*
     - ✅ `Move Members` *(Required to move players between Town Square, Whispers, and Cabins)*
   - Scroll to the bottom, **Copy** the generated URL, paste it into your browser, and authorize the bot into your server.

> **Tip for Private `#storyteller` Channels:** If you plan to run `/panel` inside a private `#storyteller-chat` text channel, make sure the Bot's Role is granted access to view and send messages in that channel!

---

### Step 2: Clone & Install Dependencies

Make sure you have **Python 3.10+** installed (`python3 --version`).

```bash
# 1. Clone the repository
git clone https://github.com/thelordofscrubs/clocktower-discord-bot.git
cd clocktower-discord-bot

# 2. Create a Python virtual environment (includes pip automatically even if global pip isn't installed)
python3 -m venv .venv

# 3. Install dependencies into the virtual environment
.venv/bin/pip install -r requirements.txt
```

*(Alternatively, you can activate the virtual environment first with `source .venv/bin/activate` on Linux/macOS or `.venv\Scripts\activate` on Windows, then run `pip install -r requirements.txt`).*

---

### Step 3: Configure Your `.env` File

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` in your editor and fill in your values:
   ```ini
   # Paste the Bot Token from the Discord Developer Portal -> Bot tab -> Reset Token
   DISCORD_TOKEN=your_actual_bot_token_here

   # Highly Recommended: Paste your Discord Server (Guild) ID for instant slash-command syncing!
   # (To copy your Server ID: in Discord Settings -> Advanced -> enable Developer Mode,
   #  then right-click your Server icon on the left sidebar and click "Copy Server ID")
   DISCORD_GUILD_ID=123456789012345678
   ```

---

### Step 4: Start the Bot

Run the bot using the virtual environment's Python binary:

```bash
.venv/bin/python bot.py
```

You should see output similar to:
```text
INFO | clocktower_bot | Loaded extension: cogs.movement
INFO | clocktower_bot | Loaded extension: cogs.timer
INFO | clocktower_bot | Loaded extension: cogs.resources
INFO | clocktower_bot | Loaded extension: cogs.panel
INFO | clocktower_bot | Synced 9 slash command(s) to development guild ID ...
INFO | clocktower_bot | Logged in as ClocktowerBot#1234
```

---

### Step 5: First-Time In-Server Setup

1. **If your server already has BotC channels:**
   - Run `/setup configure alert_channel:#your-public-game-chat town_square:Town Square` to link your public timer alert channel and Town Square (or run `/setup status` to see what the bot auto-detected).
2. **If you want the bot to build the categories and channels for you:**
   - Run `/setup auto-create` — it will create (or link existing) `🕰️ BOTC - Day`, `#town-square-chat`, `☀️ Town Square`, `💬 Whisper 1..5`, and `🌙 BOTC - Cabins`.
3. **Open the Storyteller Control Panel:**
   - Go to your `#storyteller` text channel and run `/panel`. Click buttons to run your game!

---

## 🎮 Commands Reference

| Command | Description |
| :--- | :--- |
| `/panel` | 🎛️ Post the interactive Storyteller Control Panel with buttons for movement, hush, timers, and cabin visits. |
| `/square` | ☀️ Gather all players from Whispers and Cabins back to the Town Square. |
| `/night [include_me]` | 🌙 Send all players **and the Storyteller** to private Night Cabins (`include_me` defaults to `True`). |
| `/hush` | 🔇 Server-mute players in Town Square (Storyteller stays unmuted) for morning announcements/nominations. |
| `/unhush` | 🔊 Unmute all hushed players across the BotC voice channels. |
| `/visit <player>` | 🧭 Move yourself directly into the voice channel `<player>` is currently in. |
| `/timer start <minutes> [auto_gather]` | ⏱️ Start a Day countdown timer (1-minute fidelity) with optional auto-gather at `0:00`. |
| `/timer add <minutes>` | ➕ Add extra minutes to the running Day timer. |
| `/timer cancel` | 🛑 Stop and delete the active Day timer. |
| `/help [public]` | 📚 Show player resources, Base 3 script links, rules summary, and server instructions. |
| `/setup status` | 🔍 Inspect which Town Square, Alert Text Channel, Categories, and Active Storyteller the bot tracks. |
| `/setup configure` | ⚙️ Explicitly set the General Alert Text Channel, Town Square, or Categories. |
| `/setup auto-create` | 🏗️ Build (or link existing) BotC Day & Cabins categories, Town Square, and Whisper channels. |
| `/setup delete-auto` | 🗑️ Delete auto-generated BotC channels & categories by name match (either temporary cabins only or the full setup). |
