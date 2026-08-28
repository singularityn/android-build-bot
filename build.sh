#!/bin/bash

# ============================================================
# Android ROM Build Script with Remote Monitoring
# - tmux session persistence
# - ttyd web terminal (local & Cloudflare HTTPS Tunnel)
# - Telegram notification on complete/fail
# ============================================================

# --- Config ---
BUILD_DIR="$HOME/evolution"
DEVICE="lineage_sweet"
BUILD_TYPE="cp2a-user"
BUILD_TARGET="evolution"
JOBS=$(nproc)
TTYD_PORT=8080
TTYD_USER="user"
TTYD_PASS="singularity"
SESSION_NAME="build"
LOG_FILE="$BUILD_DIR/build_$(date +%Y%m%d_%H%M%S).log"

# --- Telegram Config ---
TELEGRAM_BOT_TOKEN="8569857436:AAHA-cnRCaTCGNHfA60xBrZsyZ4eMm_KR4g"
TELEGRAM_CHAT_ID="1690477581"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Functions ---
send_telegram() {
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="$TELEGRAM_CHAT_ID" \
            -d parse_mode="HTML" \
            -d text="$1" > /dev/null 2>&1
    fi
}

get_tunnel_url() {
    grep -o 'https://[-a-zA-Z0-9@:%._\+~#=]\+\.trycloudflare\.com' /home/ubuntu/tunnel.log 2>/dev/null | tail -1
}

show_help() {
    echo ""
    echo -e "${CYAN}Usage: ./build.sh [OPTIONS]${NC}"
    echo ""
    echo "Options:"
    echo "  --device NAME     Device target (default: lineage_sweet)"
    echo "  --type TYPE       Build type (default: cp2a-user)"
    echo "  --target TARGET   Build target (default: evolution)"
    echo "  --jobs N          Parallel jobs (default: $(nproc))"
    echo "  --monitor         Attach to running build session in SSH"
    echo "  --url             Show web monitor URL"
    echo "  --stop            Stop running build"
    echo "  --help            Show this help"
    echo ""
}

# --- Parse Arguments ---
MODE="build"

while [[ $# -gt 0 ]]; do
    case $1 in
        --device) DEVICE="$2"; shift 2;;
        --type) BUILD_TYPE="$2"; shift 2;;
        --target) BUILD_TARGET="$2"; shift 2;;
        --jobs) JOBS="$2"; shift 2;;
        --monitor) MODE="monitor"; shift;;
        --url) MODE="url"; shift;;
        --stop) MODE="stop"; shift;;
        --help) show_help; exit 0;;
        *) echo "Unknown option: $1"; show_help; exit 1;;
    esac
done

# --- URL mode ---
if [ "$MODE" = "url" ]; then
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "168.138.188.221")
    TUNNEL_URL=$(get_tunnel_url)
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}  Web Monitor URLs (Login: ${TTYD_USER} / ${TTYD_PASS})${NC}"
    echo -e "${CYAN}============================================================${NC}"
    if [ -n "$TUNNEL_URL" ]; then
        echo -e "  🌐 ${GREEN}HTTPS (Mobile / HP) : ${TUNNEL_URL}${NC}"
    fi
    echo -e "  🌐 Direct IP          : http://${PUBLIC_IP}:${TTYD_PORT}"
    echo ""
    exit 0
fi

# --- Stop mode ---
if [ "$MODE" = "stop" ]; then
    echo -e "${YELLOW}Stopping build...${NC}"
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null
    echo -e "${GREEN}Build stopped.${NC}"
    exit 0
fi

# --- Monitor mode ---
if [ "$MODE" = "monitor" ]; then
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo -e "${GREEN}Attaching to build session...${NC}"
        tmux attach -t "$SESSION_NAME"
    else
        echo -e "${RED}No active build session found.${NC}"
        exit 1
    fi
    exit 0
fi

# --- Build mode ---

# Check if build already running
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo -e "${YELLOW}Build session already running!${NC}"
    echo -e "Use ${CYAN}./build.sh --monitor${NC} to attach in terminal"
    echo -e "Use ${CYAN}./build.sh --url${NC} to view web monitor link"
    echo -e "Use ${CYAN}./build.sh --stop${NC} to stop"
    exit 1
fi

# Ensure web monitor and tunnel services are running
sudo systemctl is-active --quiet build-monitor || sudo systemctl start build-monitor
sudo systemctl is-active --quiet build-tunnel || sudo systemctl start build-tunnel
sleep 1

PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "168.138.188.221")
TUNNEL_URL=$(get_tunnel_url)

echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Android ROM Build - Remote Monitoring${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo -e "  Device    : ${GREEN}${DEVICE}${NC}"
echo -e "  Type      : ${GREEN}${BUILD_TYPE}${NC}"
echo -e "  Target    : ${GREEN}${BUILD_TARGET}${NC}"
echo -e "  Jobs      : ${GREEN}-j${JOBS}${NC}"
echo -e "  Log       : ${GREEN}${LOG_FILE}${NC}"
echo -e "  Auth      : ${GREEN}${TTYD_USER}:${TTYD_PASS}${NC}"
if [ -n "$TUNNEL_URL" ]; then
    echo -e "  📱 Monitor HP (HTTPS) : ${GREEN}${TUNNEL_URL}${NC}"
fi
echo -e "  📱 Monitor IP         : http://${PUBLIC_IP}:${TTYD_PORT}"
echo ""

# Create build script for tmux
BUILD_SCRIPT=$(mktemp /tmp/build_cmd_XXXXXX.sh)
cat > "$BUILD_SCRIPT" << INNEREOF
#!/bin/bash
cd $BUILD_DIR

echo "============================================"
echo "  Build started at: \$(date)"
echo "  Device: ${DEVICE}-${BUILD_TYPE}"
echo "  Target: ${BUILD_TARGET} -j${JOBS}"
echo "============================================"
echo ""

# Source build environment
. build/envsetup.sh

# Ensure clean progress output
export NINJA_STATUS="[%p %f/%t] "
export USE_CCACHE=1

# Lunch
lunch ${DEVICE}-${BUILD_TYPE}

# Record start time
START_TIME=\$(date +%s)

# Build
m ${BUILD_TARGET} -j${JOBS} 2>&1 | tee ${LOG_FILE}
BUILD_EXIT=\${PIPESTATUS[0]}

# Calculate duration
END_TIME=\$(date +%s)
DURATION=\$(( (END_TIME - START_TIME) / 60 ))

echo ""
echo "============================================"
if [ \$BUILD_EXIT -eq 0 ]; then
    echo "  ✅ BUILD SUCCESSFUL!"
    OUT_FILE=\$(find $BUILD_DIR/out/target/product/sweet/ -maxdepth 1 -name "*.zip" -newer ${LOG_FILE} 2>/dev/null | head -1)
    OUT_SIZE=\$(du -h "\$OUT_FILE" 2>/dev/null | cut -f1)
    echo "  Output: \$OUT_FILE"
    echo "  Size: \$OUT_SIZE"
else
    echo "  ❌ BUILD FAILED (exit code: \$BUILD_EXIT)"
    echo "  Last errors:"
    grep -i "error:" ${LOG_FILE} | tail -5
fi
echo "  Duration: \${DURATION} minutes"
echo "  Finished: \$(date)"
echo "============================================"

# Send Telegram notification
if [ -n "${TELEGRAM_BOT_TOKEN}" ] && [ -n "${TELEGRAM_CHAT_ID}" ]; then
    if [ \$BUILD_EXIT -eq 0 ]; then
        MSG="✅ <b>Build Selesai!</b>%0A%0A📱 Device: ${DEVICE}%0A⏱ Durasi: \${DURATION} menit%0A📦 File: \$(basename \$OUT_FILE)%0A💾 Size: \$OUT_SIZE%0A🕐 \$(date)"
    else
        LAST_ERR=\$(grep -i "error:" ${LOG_FILE} | tail -3 | head -c 500)
        MSG="❌ <b>Build Gagal!</b>%0A%0A📱 Device: ${DEVICE}%0A⏱ Durasi: \${DURATION} menit%0A🕐 \$(date)%0A%0A<pre>\${LAST_ERR}</pre>"
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="${TELEGRAM_CHAT_ID}" \
            -d parse_mode="HTML" \
            -d text="\$MSG" > /dev/null 2>&1
        
        # Kirim file log full ke Telegram
        if [ -f "${LOG_FILE}" ]; then
            curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
                -F chat_id="${TELEGRAM_CHAT_ID}" \
                -F caption="📋 Full Build Error Log ($(basename ${LOG_FILE}))" \
                -F document=@"${LOG_FILE}" > /dev/null 2>&1
        fi
    fi

echo ""
echo "Build session will stay open. Run './build.sh --stop' when done."
while true; do sleep 3600; done
INNEREOF
chmod +x "$BUILD_SCRIPT"

# Start tmux session with build
echo -e "${CYAN}Starting build in tmux session '${SESSION_NAME}'...${NC}"
tmux new-session -d -s "$SESSION_NAME" "bash $BUILD_SCRIPT"

# Send Telegram start notification
MONITOR_LINK="${TUNNEL_URL:-http://${PUBLIC_IP}:${TTYD_PORT}}"
send_telegram "🔨 <b>Build Dimulai!</b>%0A%0A📱 Device: ${DEVICE}-${BUILD_TYPE}%0A🎯 Target: ${BUILD_TARGET} -j${JOBS}%0A🕐 $(date)%0A%0A🖥 <b>Live Monitor:</b>%0A${MONITOR_LINK}%0A🔑 Login: <code>${TTYD_USER}</code> / <code>${TTYD_PASS}</code>"

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  ✅ Build is running in background!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
if [ -n "$TUNNEL_URL" ]; then
    echo -e "  📱 ${CYAN}Monitor dari HP (HTTPS)${NC} : ${GREEN}${TUNNEL_URL}${NC}"
fi
echo -e "  🌐 ${CYAN}Monitor Direct IP${NC}       : http://${PUBLIC_IP}:${TTYD_PORT}"
echo -e "  🔑 ${CYAN}Login Web${NC}               : ${GREEN}${TTYD_USER}${NC} / ${GREEN}${TTYD_PASS}${NC}"
echo -e "  🖥  ${CYAN}Attach terminal SSH${NC}     : ./build.sh --monitor"
echo -e "  🛑 ${CYAN}Stop build${NC}              : ./build.sh --stop"
echo -e "  📋 ${CYAN}Log file${NC}                : ${LOG_FILE}"
echo ""
echo -e "${YELLOW}Anda bisa langsung menutup terminal SSH ini. Build dan Web Monitor tetap berjalan.${NC}"
