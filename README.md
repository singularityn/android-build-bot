# 🤖 Android Build Remote Suite & Telegram Bot Controller

Suite otomatisasi untuk kompilasi Custom ROM Android (AOSP / Evolution X / LineageOS) dengan fitur **Remote Monitoring (Web HTTPS)**, **Full Telegram Bot Controller**, dan **Antigravity AI Self-Healing Engine**.

---

## ✨ Fitur Utama

1. **📱 Full Remote Control via Telegram**:
   - `🔨 Start Build` (`/build`): Memulai proses build ROM di background.
   - `📈 Progress Live` (`/progress`): Real-time visual loading bar yang ter-update otomatis in-place setiap 10 detik.
   - `🤖 Auto-Fix AI` (`/autofix`): Menjalankan Antigravity AI Agent untuk membaca error log dan memperbaiki kode/sepolicy/makefile secara otomatis.
   - `📊 Status Lengkap` (`/status`): Memantau RAM, Swap, CPU Load, Disk, dan status kompilasi.
   - `🌐 Web Monitor` (`/monitor`): Link live streaming terminal terminal via Cloudflare HTTPS Tunnel.
   - `📜 Live Logs` (`/log`): Mengambil cuplikan log terminal terbaru langsung ke chat.
   - `🛑 Stop Build` (`/stop`): Membatalkan atau menghentikan proses build kapan saja.

2. **📋 Auto-Upload Full Log on Failure**:
   - Jika terjadi build error, bot otomatis mengunggah file `.log` lengkap sebagai dokumen ke chat Telegram Anda.

3. **☁️ Cloudflare HTTPS Tunnel**:
   - Tidak perlu port forwarding router / IP publik statis. Link HTTPS dengan sertifikat SSL resmi aktif 24/7.

4. **⚡ 24/7 Systemd Daemon**:
   - Bot dan monitor berjalan sebagai background service yang otomatis hidup kembali jika server restart.

---

## 🚀 Cara Setup Cepat di Server Baru (1-Click Install)

Di server baru (Ubuntu 22.04+):

```bash
# 1. Clone repository ini
git clone https://github.com/singularityn/android-build-bot.git
cd android-build-bot

# 2. Jalankan installer otomatis
sudo bash install.sh
```

---

## ⚙️ Konfigurasi Telegram Bot

Edit file `~/evolution/tg_bot.py` dan `~/evolution/build.sh` jika ingin mengganti token/chat ID:

```python
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ALLOWED_CHAT_ID = 1690477581  # Chat ID Telegram Anda
```

Lalu restart service:
```bash
sudo systemctl restart telegram-build-bot
```

---

## 📂 Struktur File

| File / Folder | Keterangan |
|---|---|
| `build.sh` | Wrapper script kompilasi ROM Android (tmux + environment setup + notification) |
| `tg_bot.py` | Daemon Python Telegram Bot dengan real-time progress & AI Auto-Fix engine |
| `singularity.sh` | Generator signing keys AOSP (10 key pairs) |
| `services/` | File service systemd (`build-monitor`, `build-tunnel`, `telegram-build-bot`) |
| `install.sh` | Script instalasi 1-klik untuk server baru |

---

*Dibuat khusus untuk Xiaomi Sweet (Redmi Note 10 Pro) & Evolution X ROM Builder.*
