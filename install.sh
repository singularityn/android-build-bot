#!/bin/bash
set -e

# ============================================================
# 1-Click Installer for Android Build Controller & Telegram Bot
# Author: singularityn
# ============================================================

echo "🚀 Starting Automated Server Setup for Android Build Suite..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/evolution"

mkdir -p "$TARGET_DIR"

# 1. Update and install packages
echo "📦 Installing required dependencies (ttyd, iptables, python3, tmux)..."
sudo apt-get update -y
sudo apt-get install -y ttyd tmux iptables-persistent python3-requests python3-pip curl wget

# 2. Install Cloudflare Tunnel (cloudflared)
if ! command -v cloudflared &> /dev/null; then
    echo "☁️ Installing Cloudflare Tunnel (cloudflared)..."
    TMP_DEB=$(mktemp /tmp/cloudflared_XXXXXX.deb)
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o "$TMP_DEB"
    sudo dpkg -i "$TMP_DEB"
    rm -f "$TMP_DEB"
fi

# 3. Configure Firewall (Port 8080)
echo "🛡️ Configuring Firewall (iptables)..."
if ! sudo iptables -C INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 5 -m state --state NEW -p tcp --dport 8080 -j ACCEPT
    sudo sh -c 'iptables-save > /etc/iptables/rules.v4'
fi

# 4. Copy scripts to workspace
echo "📂 Copying build scripts to $TARGET_DIR..."
cp "$SCRIPT_DIR/build.sh" "$TARGET_DIR/build.sh"
cp "$SCRIPT_DIR/tg_bot.py" "$TARGET_DIR/tg_bot.py"
if [ -f "$SCRIPT_DIR/singularity.sh" ]; then
    cp "$SCRIPT_DIR/singularity.sh" "$TARGET_DIR/singularity.sh"
fi
chmod +x "$TARGET_DIR/build.sh" "$TARGET_DIR/tg_bot.py" "$TARGET_DIR/singularity.sh" 2>/dev/null || true

# 5. Install Systemd Services
echo "⚙️ Setting up systemd services..."
sudo cp "$SCRIPT_DIR/services/build-monitor.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/services/build-tunnel.service" /etc/systemd/system/
sudo cp "$SCRIPT_DIR/services/telegram-build-bot.service" /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now build-monitor
sudo systemctl enable --now build-tunnel
sudo systemctl enable --now telegram-build-bot

echo ""
echo "============================================================"
echo "  ✅ Setup Selesai! Semua Service Telah Aktif."
echo "============================================================"
echo "  1. Telegram Bot     : Active (telegram-build-bot.service)"
echo "  2. Web Monitor ttyd : Active (build-monitor.service)"
echo "  3. HTTPS Tunnel     : Active (build-tunnel.service)"
echo ""
echo "  Buka Telegram Anda dan ketik /start untuk mengontrol server."
echo "============================================================"
