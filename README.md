# 🩸 Blood on the Clocktower — Storyteller Assistant Discord Bot

A Python Discord bot built with `discord.py` (v2.x) to help Storytellers run **Blood on the Clocktower** games effortlessly on Discord.

## ✨ Features

- **Zero-Config Smart Channel Discovery:** Works out-of-the-box with your existing Discord server without tedious channel-by-channel mapping:
  - Automatically finds your **Town Square** voice channel (by name or whichever channel the Storyteller is in) and treats its parent category as the **Day Category**.
  - Automatically finds your **Cabins / Night Category** (or creates one the first time you run Night).
- **Dynamic Night Cabins (`/night`):**
  - Sends all active players (excluding the Storyteller and any Spectators) into private Cabins.
  - Uses any pre-existing empty Cabin channels first, and **dynamically creates temporary Cabins on the fly** if you have more players than cabins.
  - Automatically cleans up temporary Cabins when everyone returns to the Town Square.
- **Gather to Town Square (`/square`):**
  - Pulls all players from Whisper rooms and Night Cabins back to the Town Square.
- **1-Minute Fidelity Day Timers (`/timer start`):**
  - Updates an embedded countdown every minute, posts a **1-minute warning** in chat, and automatically gathers everyone back to the Town Square when time reaches `0:00`.
- **Interactive Storyteller Control Panel (`/panel`):**
  - Posts a persistent dashboard with one-click buttons for `☀️ Gather to Town Square`, `🌙 Send to Cabins`, quick timers (`8m`, `5m`, `3m`, `1m`, `+1m`, `Stop`), a `🧭 Visit Player Cabin` dropdown menu, and `📚 Player Help & Scripts`.
- **Player Resources (`/help`):**
  - Displays official links to the Base 3 Character Sheets & Almanacs (*Trouble Brewing*, *Bad Moon Rising*, *Sects & Violets*), the official BotC Wiki, Script Tool, and a quick-reference rules summary.

---

## 🚀 Quick Start

### 1. Create a Discord Bot Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Go to the **Bot** tab:
   - Click **Reset Token** and copy your Bot Token.
   - Under **Privileged Gateway Intents**, enable **Server Members Intent**.
3. Go to **OAuth2 -> URL Generator**:
   - Check scopes: `bot` and `applications.commands`.
   - Check Bot Permissions:
     - `View Channels`
     - `Send Messages`
     - `Embed Links`
     - `Connect`
     - `Move Members` *(Required to move players between Town Square & Cabins)*
     - `Mute Members` *(Required for Storyteller Floor `/hush` & `/unhush`)*
     - `Manage Channels` *(Required for dynamic temporary Cabins and `/setup auto-create`)*
   - Copy the generated URL and open it in your browser to invite the bot to your server.

### 2. Install & Run Locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and paste your DISCORD_TOKEN (and optionally DISCORD_GUILD_ID for instant command sync)

python bot.py
```

---

## 🎮 Commands Reference

| Command | Description |
| :--- | :--- |
| `/panel` | 🎛️ Post the interactive Storyteller Control Panel with buttons for movement, timers, and cabin visits. |
| `/square` | ☀️ Gather all players from Whispers and Cabins back to the Town Square. |
| `/night [include_me]` | 🌙 Send all players (except Storytellers) to private Night Cabins. |
| `/hush` | 🔇 Server-mute players in Town Square (Storytellers stay unmuted) for morning announcements/nominations. |
| `/unhush` | 🔊 Unmute all hushed players across the BotC voice channels. |
| `/visit <player>` | 🧭 Move yourself directly into the voice channel `<player>` is currently in. |
| `/timer start <minutes> [auto_gather]` | ⏱️ Start a Day countdown timer (1-minute fidelity) with optional auto-gather at `0:00`. |
| `/timer add <minutes>` | ➕ Add extra minutes to the running Day timer. |
| `/timer cancel` | 🛑 Stop the active Day timer. |
| `/help [public]` | 📚 Show player resources, Base 3 script links, rules summary, and server instructions. |
| `/setup status` | 🔍 Inspect which Town Square, Alert Text Channel, and Categories the bot has auto-detected. |
| `/setup configure` | ⚙️ Optional override to specify the General Alert Text Channel, Town Square, or Categories. |
| `/setup auto-create` | 🏗️ Build (or link existing) BotC Day & Cabins categories, Town Square, and Whisper channels. |
| `/setup delete-auto` | 🗑️ Delete auto-generated BotC channels & categories by name match (either temporary cabins only or the full setup). |
