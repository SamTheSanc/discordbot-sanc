# Discord Reaction Tracker Bot 🤖

A Python Discord bot built with `discord.py` and containerized with Docker. It tracks reactions given and received by users in a Discord channel, displays leaderboards for both factors, and includes an Alliance tracker to track server sizes across server groups.

---

## 📖 Deployment & Run Guides
- [🪟 Windows Local Run & Stop Guide](file:///c:/Users/Sanc/GitHub/discordbot-sanc/RUN_GUIDE.md)
- [☁️ AWS EC2 (Ubuntu) Hosting Guide with Docker](file:///c:/Users/Sanc/GitHub/discordbot-sanc/AWS_HOSTING_GUIDE.md)

## 🌟 Features

- **Live Tracking**: Automatically counts reactions added or removed in real-time.
- **Historical Channel Scanning**: Scans past messages in channels to index existing reactions using `/scan`.
- **Dual Factor Leaderboard**: Visual leaderboard displaying rankings for:
  - 📤 **Reactions Gave**: Total reactions added by a user.
  - 📥 **Reactions Received**: Total reactions added to a user's messages.
- **User Stats**: Detailed user reaction summary including top used and received emojis using `/stats`.
- **Alliance Tracker**: Group server IDs under named alliances and view aggregate member statistics.
- **Persistent Storage**: Data is saved to an SQLite database mounted via a Docker volume.
- **Hybrid Commands**: Supports both Slash Commands (`/leaderboard`, `/scan`, `/stats`, `/alliance`) and Prefix Commands (`!leaderboard`, `!scan`, `!stats`, `!alliance`).

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
| `/leaderboard` or `!leaderboard` | Hybrid | Displays top users ranked by reactions **gave** and **received**. | Everyone |
| `/stats [@user]` or `!stats [@user]` | Hybrid | Displays detailed reaction stats & top emojis for a user. | Everyone |
| `/scan [limit]` or `!scan [limit]` | Hybrid | Scans the channel history up to `limit` messages (default 100). | Administrator |

### Alliance Commands
| Command | Type | Description | Permissions |
| --- | --- | --- | --- |
| `/alliance <alliance_name>` | Hybrid | Displays total members and list of servers with member counts. | Everyone |
| `/alliance_add <name> <server_id>` | Hybrid | Adds a Discord server ID to the specified alliance. | Administrator |
| `/alliance_remove <name> <server_id>` | Hybrid | Removes a Discord server ID from an alliance. | Administrator |
| `/alliance_list` | Hybrid | Lists all registered alliances. | Everyone |

---

## 📁 Project Structure

```
├── bot.py           # Main Discord bot code & commands
├── database.py      # SQLite database handler (aiosqlite)
├── Dockerfile       # Container setup
├── docker-compose.yml # Docker Compose configuration
├── requirements.txt # Python dependencies
├── .env.example     # Environment variable template
└── data/            # Database storage directory (persisted)
```
