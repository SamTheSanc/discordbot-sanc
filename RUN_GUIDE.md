# 🪟 Windows Run & Stop Guide

This guide covers how to start, monitor, and stop the Discord Bot on Windows using PowerShell or Command Prompt.

---

## 📋 Prerequisites

1. Ensure your bot token is set in [`.env`](file:///c:/Users/Sanc/Documents/Testing/.env):
   ```env
   DISCORD_TOKEN=your_token_here
   COMMAND_PREFIX=!
   ```
2. Open **PowerShell** or **Command Prompt (Terminal)** in the project directory:
   ```powershell
   cd "C:\Users\Sanc\Documents\Testing"
   ```

---

## 🐳 Option 1: Using Docker Compose (Recommended)

### 🚀 To Start / Run
Build and run the bot in the background:
```powershell
docker-compose up -d --build
```

### 📜 To View Live Logs
Check if the bot connected successfully or debug errors:
```powershell
docker-compose logs -f
```
*(Press `Ctrl + C` to exit the log view without stopping the bot).*

### 🛑 To Stop / Close
Stop and shut down the bot container:
```powershell
docker-compose down
```

### 🔄 To Restart
```powershell
docker-compose restart
```

---

## 🐳 Option 2: Using Docker CLI

### 🚀 To Build & Start
1. Build the Docker image:
   ```powershell
   docker build -t discord-reaction-bot .
   ```
2. Start the container:
   ```powershell
   docker run -d --name reaction_tracker_bot --env-file .env -v "${PWD}/data:/app/data" discord-reaction-bot
   ```

### 📜 To View Logs
```powershell
docker logs -f reaction_tracker_bot
```

### 🛑 To Stop / Close
```powershell
docker stop reaction_tracker_bot
docker rm reaction_tracker_bot
```

---

## 🐍 Option 3: Running with Python (No Docker)

### 🚀 To Start / Run
1. Install dependencies (first time only):
   ```powershell
   pip install -r requirements.txt
   ```
2. Start the bot:
   ```powershell
   python bot.py
   ```

### 🛑 To Stop / Close
Press **`Ctrl + C`** in your PowerShell terminal window.

---

## 🗑️ How to Reset Data (Wipe Database)

If you want to clear all reaction stats on Windows:

```powershell
# 1. Stop Docker
docker-compose down

# 2. Remove the data directory
Remove-Item -Recurse -Force .\data\

# 3. Start Docker again
docker-compose up -d
```
