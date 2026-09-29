# ☁️ AWS EC2 (Ubuntu) Hosting Guide with Docker

This guide explains step-by-step how to host your Discord bot 24/7 on an **AWS EC2 Ubuntu instance** using **Docker & Docker Compose**, configured and managed from your **Windows** local machine.

---

## 📑 Table of Contents
1. [Overview & Prerequisites](#1-overview--prerequisites)
2. [Step 1: Launch an AWS EC2 Ubuntu Instance](#step-1-launch-an-aws-ec2-ubuntu-instance)
3. [Step 2: Connect via SSH from Windows](#step-2-connect-via-ssh-from-windows)
4. [Step 3: Install Docker & Docker Compose on Ubuntu](#step-3-install-docker--docker-compose-on-ubuntu)
5. [Step 4: Deploy the Bot onto the Server](#step-4-deploy-the-bot-onto-the-server)
6. [Step 5: Start the Bot & Verify Live Logs](#step-5-start-the-bot--verify-live-logs)
7. [Step 6: Managing the Bot (Stop, Restart, Update)](#step-6-managing-the-bot-stop-restart-update)
8. [Step 7: Backing Up the SQLite Database to Windows](#step-7-backing-up-the-sqlite-database-to-windows)
9. [Troubleshooting & Tips](#troubleshooting--tips)

---

## 1. Overview & Prerequisites

- **Cloud Provider:** Amazon Web Services (AWS)
- **Server OS:** Ubuntu 24.04 LTS (or 22.04 LTS)
- **Local Machine:** Windows 10 / 11 (PowerShell or Windows Terminal)
- **Containerization:** Docker & Docker Compose
- **Network Requirement:** Discord bots make **outbound** connections to Discord's servers via WebSockets. **No inbound ports (like 80 or 443) are required.** Only SSH (port 22) is needed for server administration.

---

## Step 1: Launch an AWS EC2 Ubuntu Instance

1. Log in to the [AWS Management Console](https://console.aws.amazon.com/) and go to the **EC2 Dashboard**.
2. Click **Launch Instance**.
3. Configure the instance settings:
   - **Name:** `discord-reaction-bot` (or any name you prefer).
   - **Application and OS Images (AMI):** Select **Ubuntu** (choose `Ubuntu Server 24.04 LTS` or `22.04 LTS`, 64-bit (x86)).
   - **Instance Type:** `t3.micro` (or `t2.micro` depending on region, eligible for AWS Free Tier).
   - **Key Pair (login):**
     - Click **Create new key pair**.
     - Key pair name: `discord-bot-key`.
     - Key pair type: `RSA`.
     - Private key file format: `.pem` (OpenSSH format).
     - Click **Create key pair** and save the downloaded file on your Windows machine (e.g., `C:\Users\Sanc\.ssh\discord-bot-key.pem`).
   - **Network Settings (Firewall / Security Group):**
     - Select **Create security group**.
     - Check **Allow SSH traffic from**:
       - Recommended: Choose **My IP** (so only your home IP can access SSH).
       - Or choose **Anywhere** (`0.0.0.0/0`) if your home IP changes frequently.
     - *Leave HTTP/HTTPS unchecked* (not needed for this bot).
   - **Configure Storage:** Default 8 GiB gp3 is plenty.
4. Click **Launch Instance**.
5. Once launched, click on your instance to view its details. Note its **Public IPv4 address** (e.g., `3.85.123.45`).

---

## Step 2: Connect via SSH from Windows

Windows 10/11 includes OpenSSH natively in PowerShell.

### 2.1 Set Correct Permissions for `.pem` Key on Windows
AWS requires strict permissions on your private key file. If permissions are too open, SSH will reject the connection (`UNPROTECTED PRIVATE KEY FILE!`).

Open **PowerShell** on Windows as your normal user and run:

```powershell
# Adjust the path to match where your .pem file was saved
$keyPath = "$HOME\.ssh\discord-bot-key.pem"

# Reset inheritance and assign read permission only to your current Windows user
icacls.exe $keyPath /reset
icacls.exe $keyPath /grant:r "$($env:USERNAME):(R)"
icacls.exe $keyPath /inheritance:r
```

### 2.2 SSH into the Ubuntu Server
In your Windows PowerShell:

```powershell
ssh -i "$HOME\.ssh\discord-bot-key.pem" ubuntu@<YOUR_EC2_PUBLIC_IP>
```
*(Replace `<YOUR_EC2_PUBLIC_IP>` with your actual EC2 public IP).*

When prompted:
```text
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```
Type `yes` and press **Enter**. You are now logged into your Ubuntu EC2 terminal!

---

## Step 3: Install Docker & Docker Compose on Ubuntu

Run these commands inside your **EC2 Ubuntu terminal** to install the official Docker Engine and Compose plugin:

### 3.1 Update system packages
```bash
sudo apt update && sudo apt upgrade -y
```

### 3.2 Install prerequisites and Docker repository
```bash
sudo apt install -y ca-certificates curl gnupg

# Add Docker's official GPG key:
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
```

### 3.3 Install Docker Engine & Docker Compose
```bash
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 3.4 Enable non-root Docker usage & system start on boot
```bash
# Add current user (ubuntu) to docker group to run docker without sudo
sudo usermod -aG docker $USER

# Enable Docker service on system boot
sudo systemctl enable docker
sudo systemctl start docker

# Apply group changes to current session
newgrp docker
```

### 3.5 Verify Installation
```bash
docker --version
docker compose version
```
Both commands should return the installed versions without errors.

---

## Step 4: Deploy the Bot onto the Server

Choose **Option A** (Git) or **Option B** (Direct SCP from Windows).

### Option A: Using Git (Recommended)
If your repository is pushed to GitHub/GitLab:

1. In the EC2 terminal:
   ```bash
   git clone https://github.com/<your-username>/<your-repo-name>.git ~/discordbot-sanc
   cd ~/discordbot-sanc
   ```

2. Create the `.env` file on the server:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Paste your real Discord token and prefix:
   ```env
   DISCORD_TOKEN=your_actual_discord_bot_token_here
   COMMAND_PREFIX=!
   ```
   Save and exit (`Ctrl + O`, `Enter`, then `Ctrl + X`).

---

### Option B: Uploading Files Directly from Windows (Using SCP)
If you haven't pushed to Git, transfer files directly from your **Windows PowerShell**:

1. In your **Windows PowerShell**, navigate to your project directory:
   ```powershell
   cd C:\Users\Sanc\GitHub\discordbot-sanc
   ```

2. First, create the destination folder on the EC2 instance:
   ```powershell
   ssh -i "$HOME\.ssh\discord-bot-key.pem" ubuntu@<YOUR_EC2_PUBLIC_IP> "mkdir -p ~/discordbot-sanc"
   ```

3. Transfer the project files:
   ```powershell
   scp -i "$HOME\.ssh\discord-bot-key.pem" `
       Dockerfile docker-compose.yml requirements.txt bot.py database.py .env `
       ubuntu@<YOUR_EC2_PUBLIC_IP>:~/discordbot-sanc/
   ```
   *(Note: This uploads your local `.env` directly so you don't need to retype it).*

---

## Step 5: Start the Bot & Verify Live Logs

In the EC2 terminal:

```bash
cd ~/discordbot-sanc

# Ensure data directory exists for database mounting
mkdir -p data

# Build the image and start the container in detached (background) mode
docker compose up -d --build
```

### Check Logs & Status
```bash
# View real-time output
docker compose logs -f
```

You should see output similar to:
```text
reaction_tracker_bot | Database initialized at data/reactions.db
reaction_tracker_bot | Logged in as YourBotName#1234 (ID: ...)
reaction_tracker_bot | Connected to X guilds.
reaction_tracker_bot | Bot is ready!
```

> 💡 Press **`Ctrl + C`** to exit the log view. The bot will keep running in the background.

---

## Step 6: Managing the Bot (Stop, Restart, Update)

All these commands are run inside `~/discordbot-sanc` on the EC2 instance:

| Task | Command |
|---|---|
| **View Live Logs** | `docker compose logs -f` |
| **View Container Status** | `docker compose ps` |
| **Restart Bot** | `docker compose restart` |
| **Stop Bot** | `docker compose down` |
| **Start Bot** | `docker compose up -d` |
| **Rebuild After Code Changes** | `docker compose up -d --build` |

### Auto-Restart on Server Reboot
The `docker-compose.yml` file is configured with `restart: always`. If the AWS EC2 instance restarts for maintenance or updates, Docker will **automatically start the bot container back up** as soon as the operating system boots.

---

## Step 7: Backing Up the SQLite Database to Windows

Your bot's reaction statistics are stored in `./data/reactions.db`.

To download a backup to your Windows machine, run this command in **Windows PowerShell**:

```powershell
# Create a local backups directory
mkdir -Force "$HOME\Desktop\discord_bot_backups"

# Download the database from EC2
scp -i "$HOME\.ssh\discord-bot-key.pem" `
    ubuntu@<YOUR_EC2_PUBLIC_IP>:~/discordbot-sanc/data/reactions.db `
    "$HOME\Desktop\discord_bot_backups\reactions_$(Get-Date -Format 'yyyyMMdd_HHmmss').db"
```

To restore a backup to the server later:
```powershell
# Upload backup file to server
scp -i "$HOME\.ssh\discord-bot-key.pem" `
    "$HOME\Desktop\discord_bot_backups\your_backup.db" `
    ubuntu@<YOUR_EC2_PUBLIC_IP>:~/discordbot-sanc/data/reactions.db

# Restart container to load restored data
ssh -i "$HOME\.ssh\discord-bot-key.pem" ubuntu@<YOUR_EC2_PUBLIC_IP> "cd ~/discordbot-sanc && docker compose restart"
```

---

## Troubleshooting & Tips

### 1. SSH "Connection timed out"
- Check that the AWS Security Group allows inbound traffic on **Port 22** from your current IP. If your ISP changed your home IP, update the rule in the AWS EC2 Security Group settings.

### 2. "Permission denied (publickey)"
- Ensure you are using user `ubuntu` (not `root` or `admin`): `ssh -i ... ubuntu@<IP>`.
- Verify the `.pem` file permissions using the `icacls.exe` command from [Step 2.1](#21-set-correct-permissions-for-pem-key-on-windows).

### 3. Public IP changes after Stop/Start
- When you **Stop** and **Start** an EC2 instance, AWS assigns a new public IP.
- **Tip:** If you need a permanent IP address, allocate an **Elastic IP** in the EC2 Console and associate it with your instance (Free Tier covers 1 attached in-use Elastic IP).

### 4. Bot doesn't track reactions in Discord
- Ensure **Privileged Gateway Intents** (`MESSAGE CONTENT INTENT`, `SERVER MEMBERS INTENT`) are enabled in the [Discord Developer Portal](https://discord.com/developers/applications) under **Bot -> Privileged Gateway Intents**.
