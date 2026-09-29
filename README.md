# Discord Reaction Tracker Bot 🤖

A Python Discord bot built with `discord.py` and containerized with Docker. It tracks reactions given and received by users in a Discord channel and displays leaderboards for both factors.

---

## 📖 Deployment & Run Guides
- [🪟 Windows Local Run & Stop Guide](file:///c:/Users/Sanc/GitHub/discordbot-sanc/RUN_GUIDE.md)
- [☁️ AWS EC2 (Ubuntu) Hosting Guide with Docker](file:///c:/Users/Sanc/GitHub/discordbot-sanc/AWS_HOSTING_GUIDE.md)

## 🌟 Features

- **Live Tracking**: Automatically counts emoji reactions and ASCII emoticons added or removed in real-time.
- **ASCII Emoticon Counter**: Automatically detects and tallies emoticon usages like `:D`, `:)`, `:>`, `^-^`, `^~^`, `^_^`, `xd`, `uwu`, etc.
- **Strict Channel Scoping**: Emoji reactions and ASCII emoticons are only tracked in the designated channel (`1238775030444326952`).
- **Historical Channel Scanning**: Scans past messages in the channel to index existing reactions and emoticons using `/scan`.
- **Multi-Factor Leaderboard**: Visual leaderboard displaying rankings for:
  - 📤 **Reactions Gave**: Total emoji reactions added by a user.
  - 📥 **Reactions Received**: Total emoji reactions added to a user's messages.
  - 😊 **Emoticons Used**: Total ASCII emoticons typed in chat by a user.
- **User Stats**: Detailed user summary including top used emojis, top received emojis, and top ASCII emoticons using `/stats`.
- **Persistent Storage**: Data is saved to an SQLite database mounted via a Docker volume.
- **Hybrid Commands**: Supports both Slash Commands (`/leaderboard`, `/emoticons`, `/scan`, `/stats`) and Prefix Commands (`!leaderboard`, `!emoticons`, `!scan`, `!stats`).

---

## ⚙️ Prerequisites & Setup

### 1. Enable Discord Privileged Intents

To read messages and reactions, enable the following in the **[Discord Developer Portal](https://discord.com/developers/applications)**:

1. Open your Bot application.
2. Navigate to the **Bot** tab on the left.
3. Scroll down to **Privileged Gateway Intents** and enable:
   - ✅ **Message Content Intent**
   - ✅ **Server Members Intent**

### 2. Configure Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and paste your Bot Token:
   ```env
   DISCORD_TOKEN=your_actual_discord_bot_token_here
   COMMAND_PREFIX=!
   ```

---

## 🐳 Running with Docker

### Option 1: Docker Compose (Recommended)

Run the bot in the background:
```bash
docker-compose up -d --build
```

View logs:
```bash
docker-compose logs -f
```

Stop the bot:
```bash
docker-compose down
```

### Option 2: Docker CLI

Build the Docker image:
```bash
docker build -t discord-reaction-bot .
```

Run the container:
```bash
docker run -d \
  --name reaction_tracker_bot \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  discord-reaction-bot
```

---

## 📜 Bot Commands

### Reaction Commands
| Command | Type | Description | Permissions |
| --- | --- | --- | --- |
| `/leaderboard` or `!leaderboard` | Hybrid | Displays top users ranked by reactions gave, received, and emoticons used. | Everyone |
| `/emoticons` or `!emoticons` | Hybrid | Displays dedicated ASCII emoticon leaderboard and most used emoticons. | Everyone |
| `/stats [@user]` or `!stats [@user]` | Hybrid | Displays detailed reaction and emoticon stats & top emojis for a user. | Everyone |
| `/scan [limit]` or `!scan [limit]` | Hybrid | Scans the allowed channel history for reactions and emoticons (default 100). | Administrator |


---

## 📁 Project Structure

```
├── bot.py           # Main Discord bot code & commands
├── database.py      # SQLite database handler (aiosqlite)
├── emoticons.py     # ASCII emoticon detection and tokenization
├── Dockerfile       # Container setup
├── docker-compose.yml # Docker Compose configuration
├── requirements.txt # Python dependencies
├── .env.example     # Environment variable template
└── data/            # Database storage directory (persisted)
```
