#!/usr/bin/env python3
import time
import subprocess
import requests
import os
import re
import html
import threading
import datetime

# --- Config ---
BOT_TOKEN = "8569857436:AAHA-cnRCaTCGNHfA60xBrZsyZ4eMm_KR4g"
ALLOWED_CHAT_ID = 1690477581
BUILD_DIR = "/home/ubuntu/evolution"
BUILD_SCRIPT = os.path.join(BUILD_DIR, "build.sh")
AGY_BIN = "/home/ubuntu/.gemini/bin/agy"
TUNNEL_LOG = "/home/ubuntu/tunnel.log"
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# State tracker for auto-updates & milestone broadcasts
state_lock = threading.Lock()
bot_state = {
    "live_msg_id": None,
    "live_chat_id": None,
    "last_percent": -1,
    "last_milestone": 0,
    "was_running": False,
    "last_handled_log": None,
    "is_fixing": False
}

def get_tunnel_url():
    if os.path.exists(TUNNEL_LOG):
        try:
            with open(TUNNEL_LOG, "r") as f:
                content = f.read()
                matches = re.findall(r'https://[-a-zA-Z0-9@:%._\+~#=]+\.trycloudflare\.com', content)
                if matches:
                    return matches[-1]
        except Exception:
            pass
    return "http://168.138.188.221:8080"

def is_build_running():
    try:
        res = subprocess.run(["tmux", "has-session", "-t", "build"], capture_output=True)
        return res.returncode == 0
    except Exception:
        return False

def make_progress_bar(percent, length=10):
    filled = int(round(length * percent / 100))
    filled = max(0, min(length, filled))
    bar = "🟩" * filled + "⬜" * (length - filled)
    return bar

def get_build_progress():
    if not is_build_running():
        try:
            log_files = subprocess.check_output(f"ls -t {BUILD_DIR}/build_*.log 2>/dev/null", shell=True, text=True).strip().split()
            if log_files:
                last_log = log_files[0]
                tail_content = subprocess.check_output(["tail", "-n", "30", last_log], text=True)
                if "BUILD SUCCESSFUL" in tail_content or "Package Complete" in tail_content:
                    return {
                        "running": False,
                        "status": "✅ <b>Selesai (Success 100%)</b>",
                        "percent": 100,
                        "bar": make_progress_bar(100),
                        "text": "Build terakhir telah selesai 100% dengan sukses."
                    }
                elif "BUILD FAILED" in tail_content or "failed to build" in tail_content:
                    return {
                        "running": False,
                        "status": "❌ <b>Gagal (Failed)</b>",
                        "percent": 0,
                        "bar": make_progress_bar(0),
                        "text": "Build terakhir gagal. Tekan 🤖 Auto-Fix AI untuk memperbaiki otomatis."
                    }
        except Exception:
            pass
        return {
            "running": False,
            "status": "⚪ <b>Tidak Ada Build Aktif (Idle)</b>",
            "percent": 0,
            "bar": make_progress_bar(0),
            "text": "Tekan tombol 🔨 Start Build untuk memulai proses compile."
        }

    lines = []
    try:
        res = subprocess.run(["tmux", "capture-pane", "-pt", "build:0", "-S", "-1000"], capture_output=True, text=True)
        lines = res.stdout.strip().split("\n")
    except Exception:
        pass

    if not lines or len(lines) < 5:
        try:
            log_files = subprocess.check_output(f"ls -t {BUILD_DIR}/build_*.log 2>/dev/null", shell=True, text=True).strip().split()
            if log_files:
                res = subprocess.run(["tail", "-n", "1000", log_files[0]], capture_output=True, text=True)
                lines = res.stdout.strip().split("\n")
        except Exception:
            pass

    percent = 0
    cur_task = 0
    total_tasks = 0
    current_action = "Menyiapkan build..."
    phase = "Kompilasi"

    p1 = re.compile(r'\[\s*(\d+)%\s+(\d+)/(\d+).*?\]\s*(.*)')
    p2 = re.compile(r'\[\s*(\d+)%\s+(\d+)/(\d+)\]\s*(.*)')
    p3 = re.compile(r'\[\s*(\d+)%\s*\]\s*(.*)')
    p4 = re.compile(r'\[\s*(\d+)/(\d+)\]\s*(.*)')

    for line in reversed(lines):
        line_clean = line.strip()
        m = p1.search(line_clean)
        if m:
            percent = int(m.group(1))
            cur_task = int(m.group(2))
            total_tasks = int(m.group(3))
            current_action = m.group(4).strip()
            phase = "Kompilasi Kode (Ninja Build)"
            break

        m = p2.search(line_clean)
        if m:
            percent = int(m.group(1))
            cur_task = int(m.group(2))
            total_tasks = int(m.group(3))
            current_action = m.group(4).strip()
            phase = "Inisialisasi Blueprint (Soong)"
            break

        m = p3.search(line_clean)
        if m:
            percent = int(m.group(1))
            current_action = m.group(2).strip()
            phase = "Proses Build"
            break

        m = p4.search(line_clean)
        if m:
            cur_task = int(m.group(1))
            total_tasks = int(m.group(2))
            if total_tasks > 0:
                percent = int(round((cur_task / total_tasks) * 100))
            current_action = m.group(3).strip()
            phase = "Proses Build"
            break

        if "initializing Make module parser" in line_clean or "including out/soong" in line_clean:
            phase = "Evaluasi Makefiles (ckati)"
            percent = max(percent, 5)
            current_action = line_clean
            break
        elif "bootstrap blueprint" in line_clean or "analyzing Android.bp" in line_clean:
            phase = "Inisialisasi Blueprint (Soong)"
            percent = max(percent, 2)
            current_action = line_clean
            break

    bar = make_progress_bar(percent)
    task_info = f"{cur_task:,} / {total_tasks:,} tasks" if total_tasks > 0 else "Menghitung tasks..."
    
    if len(current_action) > 90:
        current_action = current_action[:87] + "..."

    return {
        "running": True,
        "status": "🟢 <b>Sedang Mengompilasi (Building)</b>",
        "phase": phase,
        "percent": percent,
        "bar": bar,
        "tasks": task_info,
        "action": current_action or "Sedang berjalan..."
    }

def get_server_specs():
    try:
        ram = subprocess.check_output("free -h | awk '/Mem:/{print $3 \" / \" $2}'", shell=True, text=True).strip()
        swap = subprocess.check_output("free -h | awk '/Swap:/{print $3 \" / \" $2}'", shell=True, text=True).strip()
        disk = subprocess.check_output("df -h /home/ubuntu | awk 'NR==2{print $3 \" / \" $2 \" (Free: \" $4 \")\"}'", shell=True, text=True).strip()
        cpu_load = subprocess.check_output("uptime | awk -F'load average:' '{print $2}'", shell=True, text=True).strip()
        return f"🖥 <b>Server Specs & Usage:</b>\n\n🧠 RAM: <code>{ram}</code>\n🔄 Swap: <code>{swap}</code>\n💾 Disk: <code>{disk}</code>\n⚡ Load: <code>{cpu_load}</code>"
    except Exception as e:
        return f"Error: {e}"

def get_build_log(lines=20):
    if is_build_running():
        try:
            res = subprocess.run(["tmux", "capture-pane", "-pt", "build:0", "-S", f"-{lines}"], capture_output=True, text=True)
            output = res.stdout.strip().split("\n")
            recent = "\n".join(output[-lines:])
            return f"📜 <b>Live Output (Last {lines} lines):</b>\n<pre>{html.escape(recent)}</pre>"
        except Exception as e:
            return f"Error capturing tmux: {e}"
    else:
        try:
            log_files = subprocess.check_output(f"ls -t {BUILD_DIR}/build_*.log 2>/dev/null", shell=True, text=True).strip().split()
            if log_files:
                res = subprocess.run(["tail", f"-n{lines}", log_files[0]], capture_output=True, text=True)
                return f"📜 <b>Log Terakhir:</b>\n<pre>{html.escape(res.stdout[-3000:])}</pre>"
        except Exception:
            pass
        return "ℹ️ Tidak ada log build yang tersedia."

def get_main_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🔨 Start Build", "callback_data": "start_build"},
                {"text": "📈 Progress Live", "callback_data": "progress"}
            ],
            [
                {"text": "🤖 Auto-Fix AI", "callback_data": "autofix"},
                {"text": "📊 Status Lengkap", "callback_data": "status"}
            ],
            [
                {"text": "🌐 Web Monitor", "callback_data": "monitor"},
                {"text": "📜 Live Logs", "callback_data": "logs"}
            ],
            [
                {"text": "🖥 Server Specs", "callback_data": "specs"},
                {"text": "🛑 Stop Build", "callback_data": "stop_build"}
            ]
        ]
    }

def format_progress_message(prog):
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    tunnel_url = get_tunnel_url()
    if prog["running"]:
        return (
            f"📈 <b>Live Progres Build Android</b> (Update: <code>{now_str}</code>):\n\n"
            f"• Status: {prog['status']}\n"
            f"• Tahap: <b>{prog['phase']}</b>\n\n"
            f"<b>Progres:</b> {prog['percent']}%\n"
            f"<code>[{prog['bar']}]</code>\n"
            f"📦 <b>Tasks:</b> <code>{prog['tasks']}</code>\n"
            f"⚙️ <b>Action:</b> <code>{html.escape(prog['action'])}</code>\n\n"
            f"🌐 <b>Web Live:</b> {tunnel_url}\n"
            f"<i>Pesan ini diperbarui otomatis secara real-time setiap beberapa detik.</i>"
        )
    else:
        return (
            f"📈 <b>Status Build:</b>\n\n"
            f"• Status: {prog['status']}\n\n"
            f"{prog['text']}\n\n"
            f"🌐 <b>Web Monitor:</b> {tunnel_url}"
        )

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("result", {}).get("message_id")
    except Exception as e:
        print(f"Error sending message: {e}")
    return None

def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(f"{BASE_URL}/editMessageText", json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Error editing message: {e}")
    return False

def send_document(chat_id, file_path, caption=None):
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "rb") as f:
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption[:1000]
                data["parse_mode"] = "HTML"
            resp = requests.post(f"{BASE_URL}/sendDocument", data=data, files={"document": f}, timeout=60)
            return resp.status_code == 200
    except Exception as e:
        print(f"Error sending document {file_path}: {e}")
    return False

def answer_callback(callback_id, text=None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    try:
        requests.post(f"{BASE_URL}/answerCallbackQuery", json=payload, timeout=5)
    except Exception:
        pass

def extract_error_details():
    failed_cmd_file = os.path.join(BUILD_DIR, "out/siso_failed_commands.sh")
    failed_cmd = ""
    error_output = ""

    if os.path.exists(failed_cmd_file):
        try:
            with open(failed_cmd_file, "r") as f:
                failed_cmd = f.read().strip()
            res = subprocess.run(["bash", failed_cmd_file], cwd=BUILD_DIR, capture_output=True, text=True, timeout=15)
            error_output = res.stderr.strip() or res.stdout.strip()
        except Exception:
            pass

    if not error_output or len(error_output) < 20:
        try:
            log_files = subprocess.check_output(f"ls -t {BUILD_DIR}/build_*.log 2>/dev/null", shell=True, text=True).strip().split()
            if log_files:
                tail_lines = subprocess.check_output(["tail", "-n", "80", log_files[0]], text=True).split("\n")
                matched = [l for l in tail_lines if any(k in l.lower() for k in ["error:", "fatal:", "failed:", "duplicate declaration", "syntax error"])]
                error_output = "\n".join(matched[-10:]) if matched else "\n".join(tail_lines[-30:])
        except Exception:
            pass

    return failed_cmd, error_output

# --- Antigravity AI Auto-Fix Worker ---
def execute_antigravity_fix_thread(chat_id):
    global bot_state
    try:
        with state_lock:
            bot_state["is_fixing"] = True

        failed_cmd, error_output = extract_error_details()
        err_preview = error_output[:300] if error_output else "Menganalisis log build..."

        send_message(
            chat_id,
            f"🤖 <b>Antigravity AI Agent Aktif!</b>\n\n"
            f"🔍 <b>Error Terdeteksi:</b>\n<code>{html.escape(err_preview)}</code>\n\n"
            f"⏳ <i>Antigravity sedang membuka file sumber dan menerapkan perbaikan kode secara otomatis...</i>"
        )

        prompt = (
            "Terjadi build error saat mengompilasi custom ROM Android Evolution X untuk device lineage_sweet (sm6150-common / sweet).\n\n"
            f"Detail error compiler:\n{error_output[:2000]}\n\n"
            f"Perintah yang gagal:\n{failed_cmd[:600]}\n\n"
            "Tugas Anda:\n"
            "1. Buka file sumber/sepolicy/Android.bp/makefile yang disebutkan pada error di atas.\n"
            "2. Lakukan perbaikan langsung pada file kode sumber yang bermasalah.\n"
            "3. Berikan ringkasan singkat 2-3 kalimat penjelasan perbaikan."
        )

        cmd = [
            AGY_BIN,
            "--add-dir", BUILD_DIR,
            "-p", prompt,
            "--mode", "accept-edits",
            "--dangerously-skip-permissions",
            "--print-timeout", "10m0s"
        ]

        start_t = time.time()
        res = subprocess.run(cmd, cwd=BUILD_DIR, capture_output=True, text=True, timeout=600)
        elapsed = int(time.time() - start_t)

        # Check git status for modified files
        git_diff_summary = ""
        try:
            status_out = subprocess.check_output(
                "git status -s 2>/dev/null",
                shell=True,
                cwd=BUILD_DIR,
                text=True
            ).strip()
            if not status_out:
                # Check inside device and vendor sub-repositories
                status_out = subprocess.check_output(
                    "git -C device/xiaomi/sm6150-common status -s 2>/dev/null; git -C device/xiaomi/sweet status -s 2>/dev/null; git -C vendor/xiaomi/sm6150-common status -s 2>/dev/null",
                    shell=True,
                    cwd=BUILD_DIR,
                    text=True
                ).strip()
            git_diff_summary = status_out if status_out else "Perbaikan diterapkan langsung pada file workspace."
        except Exception:
            git_diff_summary = "Perbaikan selesai."

        # Extract agent's final answer
        agent_out = res.stdout.strip()
        if not agent_out:
            agent_out = res.stderr.strip()

        # Clean summary for Telegram display
        summary_clean = agent_out[-1500:] if len(agent_out) > 1500 else agent_out
        if not summary_clean:
            summary_clean = "Perbaikan selesai diterapkan pada source tree."

        reply_keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🚀 Start Build Sekarang", "callback_data": "start_build"},
                    {"text": "📊 Status", "callback_data": "status"}
                ],
                [
                    {"text": "📜 Live Logs", "callback_data": "logs"},
                    {"text": "🌐 Web Monitor", "callback_data": "monitor"}
                ]
            ]
        }

        report_msg = (
            f"✨ <b>Antigravity AI Auto-Fix Selesai!</b> (⏱ {elapsed}s)\n\n"
            f"📝 <b>File yang Dimodifikasi:</b>\n<code>{html.escape(git_diff_summary[:300])}</code>\n\n"
            f"📋 <b>Ringkasan Diagnosa & Solusi:</b>\n<pre>{html.escape(summary_clean)}</pre>\n\n"
            f"🚀 <i>Silakan tekan tombol di bawah untuk melanjutkan proses build ROM:</i>"
        )
        send_message(chat_id, report_msg, reply_keyboard)

    except subprocess.TimeoutExpired:
        send_message(chat_id, "⚠️ <b>Waktu Analisis AI Habis (Timeout)</b>\n\nAntigravity membutuhkan waktu lebih lama. Silakan coba tekan /autofix kembali.")
    except Exception as e:
        send_message(chat_id, f"❌ <b>Gagal menjalankan Antigravity AI Auto-Fix:</b> {e}")
    finally:
        with state_lock:
            bot_state["is_fixing"] = False

# Background worker for real-time progress editing & auto failure log delivery
def background_progress_worker():
    global bot_state
    while True:
        try:
            running = is_build_running()
            with state_lock:
                was_running = bot_state["was_running"]
                live_msg_id = bot_state["live_msg_id"]
                live_chat_id = bot_state["live_chat_id"]
                last_percent = bot_state["last_percent"]
                last_milestone = bot_state["last_milestone"]

            if running:
                prog = get_build_progress()
                cur_percent = prog["percent"]
                
                # In-place live message editing if active
                if live_msg_id and live_chat_id:
                    msg_text = format_progress_message(prog)
                    edit_message(live_chat_id, live_msg_id, msg_text, get_main_keyboard())

                # Milestone broadcast notifications (e.g. 25%, 50%, 75%, 90%)
                for milestone in [25, 50, 75, 90]:
                    if cur_percent >= milestone > last_milestone:
                        send_message(
                            ALLOWED_CHAT_ID,
                            f"🔔 <b>Milestone Tercapai: {milestone}%!</b>\n\n"
                            f"<code>[{prog['bar']}]</code>\n"
                            f"📦 Tasks: <code>{prog['tasks']}</code>\n"
                            f"⚙️ Action: <code>{html.escape(prog['action'])}</code>\n\n"
                            f"🌐 Live: {get_tunnel_url()}"
                        )
                        with state_lock:
                            bot_state["last_milestone"] = milestone
                        break

                with state_lock:
                    bot_state["last_percent"] = cur_percent
                    bot_state["was_running"] = True

            elif was_running and not running:
                time.sleep(3)
                log_files = subprocess.check_output(f"ls -t {BUILD_DIR}/build_*.log 2>/dev/null", shell=True, text=True).strip().split()
                if log_files:
                    latest_log = log_files[0]
                    with state_lock:
                        last_handled = bot_state["last_handled_log"]

                    if latest_log != last_handled:
                        tail_content = subprocess.check_output(["tail", "-n", "50", latest_log], text=True)
                        if "BUILD SUCCESSFUL" in tail_content or "Package Complete" in tail_content:
                            out_files = subprocess.check_output(f"find {BUILD_DIR}/out/target/product/sweet/ -maxdepth 1 -name '*.zip' -newer {latest_log} 2>/dev/null", shell=True, text=True).strip().split()
                            out_name = os.path.basename(out_files[0]) if out_files else "ROM .zip"
                            send_message(
                                ALLOWED_CHAT_ID,
                                f"🎉 <b>BUILD SUCCESSFUL! (100%)</b>\n\n"
                                f"📱 Device: <code>lineage_sweet</code>\n"
                                f"📦 File: <code>{out_name}</code>\n"
                                f"🕐 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                get_main_keyboard()
                            )
                        else:
                            # Build failed: extract error summary & offer auto-fix
                            err_lines = [l for l in tail_content.split("\n") if "error:" in l.lower() or "failed" in l.lower()]
                            err_summary = "\n".join(err_lines[-5:]) if err_lines else tail_content[-500:]
                            
                            fail_keyboard = {
                                "inline_keyboard": [
                                    [
                                        {"text": "🤖 Auto-Fix dengan AI", "callback_data": "autofix"},
                                        {"text": "📜 Live Logs", "callback_data": "logs"}
                                    ],
                                    [
                                        {"text": "🔨 Start Build Ulang", "callback_data": "start_build"},
                                        {"text": "🌐 Web Monitor", "callback_data": "monitor"}
                                    ]
                                ]
                            }

                            send_message(
                                ALLOWED_CHAT_ID,
                                f"❌ <b>BUILD GAGAL / ERROR!</b>\n\n"
                                f"📱 Device: <code>lineage_sweet</code>\n"
                                f"📋 <b>Cuplikan Error:</b>\n<pre>{html.escape(err_summary[:600])}</pre>\n\n"
                                f"<i>Tekan tombol di bawah untuk meminta AI Antigravity memperbaiki error secara otomatis:</i>",
                                fail_keyboard
                            )
                            send_document(
                                ALLOWED_CHAT_ID,
                                latest_log,
                                caption=f"📋 <b>Full Build Log</b>: {os.path.basename(latest_log)}"
                            )

                        with state_lock:
                            bot_state["last_handled_log"] = latest_log

                with state_lock:
                    bot_state["was_running"] = False
                    bot_state["last_milestone"] = 0
                    bot_state["live_msg_id"] = None

        except Exception as e:
            print(f"Error in background progress worker: {e}")

        time.sleep(10)

def handle_action(action, chat_id, callback_id=None):
    global bot_state
    if action in ["start", "help", "menu"]:
        if callback_id:
            answer_callback(callback_id)
        msg = (
            "🤖 <b>Singularity Android Build Bot</b>\n\n"
            "Pilih menu di bawah untuk memantau atau mengontrol build:\n\n"
            "• 🔨 /build - Mulai proses compile ROM\n"
            "• 📈 /progress - Live progress bar auto-update realtime\n"
            "• 🤖 /autofix - Perbaiki error build otomatis dengan Antigravity AI\n"
            "• 📊 /status - Cek status & pemakaian resource server\n"
            "• 🌐 /monitor - Dapatkan link Web Monitor HTTPS\n"
            "• 📜 /log - Lihat baris log terminal terbaru\n"
            "• 🖥 /specs - Cek RAM/Swap/CPU server\n"
            "• 🛑 /stop - Hentikan proses build"
        )
        send_message(chat_id, msg, get_main_keyboard())

    elif action in ["autofix", "fix"]:
        if is_build_running():
            if callback_id:
                answer_callback(callback_id, "Build sedang berjalan")
            send_message(chat_id, "⚠️ <b>Build sedang aktif berjalan!</b> Hentikan build terlebih dahulu dengan /stop jika ingin menjalankan Auto-Fix.", get_main_keyboard())
            return

        with state_lock:
            fixing = bot_state["is_fixing"]

        if fixing:
            if callback_id:
                answer_callback(callback_id, "Auto-Fix sedang berjalan")
            send_message(chat_id, "⏳ <b>Antigravity Auto-Fix sedang berjalan...</b> Mohon tunggu laporan selesai dikirimkan.")
            return

        if callback_id:
            answer_callback(callback_id, "Menjalankan Antigravity AI...")

        fix_thread = threading.Thread(target=execute_antigravity_fix_thread, args=(chat_id,), daemon=True)
        fix_thread.start()

    elif action in ["progress"]:
        if callback_id:
            answer_callback(callback_id, "Memuat progres...")
        prog = get_build_progress()
        msg_text = format_progress_message(prog)
        msg_id = send_message(chat_id, msg_text, get_main_keyboard())
        if prog["running"] and msg_id:
            with state_lock:
                bot_state["live_msg_id"] = msg_id
                bot_state["live_chat_id"] = chat_id

    elif action in ["start_build", "build"]:
        if is_build_running():
            if callback_id:
                answer_callback(callback_id, "Build sudah berjalan!")
            send_message(chat_id, "⚠️ <b>Build sedang aktif berjalan!</b>\n\nTekan /progress untuk melihat live loading bar atau /monitor untuk live web.", get_main_keyboard())
        else:
            if callback_id:
                answer_callback(callback_id, "Memulai build...")
            tunnel_url = get_tunnel_url()
            send_message(
                chat_id,
                f"🚀 <b>Memulai proses build ROM...</b>\n\n"
                f"• Target: <code>lineage_sweet-cp2a-user</code>\n"
                f"• Target Build: <code>m evolution -j8</code>\n\n"
                f"🌐 <b>Live Web Monitor:</b>\n{tunnel_url}\n"
                f"🔑 Login: <code>user</code> / <code>singularity</code>\n\n"
                f"<i>Memulai proses di background...</i>"
            )
            try:
                subprocess.Popen(["/bin/bash", BUILD_SCRIPT], cwd=BUILD_DIR)
                time.sleep(3)
                prog = get_build_progress()
                msg_text = format_progress_message(prog)
                msg_id = send_message(chat_id, msg_text, get_main_keyboard())
                if msg_id:
                    with state_lock:
                        bot_state["live_msg_id"] = msg_id
                        bot_state["live_chat_id"] = chat_id
                        bot_state["was_running"] = True
                        bot_state["last_milestone"] = 0
            except Exception as e:
                send_message(chat_id, f"❌ <b>Gagal memulai build:</b> {e}", get_main_keyboard())

    elif action in ["status"]:
        if callback_id:
            answer_callback(callback_id)
        prog = get_build_progress()
        tunnel_url = get_tunnel_url()
        
        progress_block = ""
        if prog["running"]:
            progress_block = (
                f"\n📈 <b>Persentase:</b> {prog['percent']}%\n"
                f"<code>[{prog['bar']}]</code>\n"
                f"📦 Tasks: <code>{prog['tasks']}</code>\n"
                f"⚙️ Tahap: <code>{prog['phase']}</code>\n"
            )
        else:
            progress_block = f"\n• Status: {prog['status']}\n"

        msg = (
            f"📊 <b>Status Build Server:</b>\n"
            f"• Device: <code>Xiaomi Sweet (Redmi Note 10 Pro)</code>\n"
            f"• Target: <code>lineage_sweet-cp2a-user</code>\n"
            f"{progress_block}\n"
            f"🌐 <b>Web Monitor:</b> {tunnel_url}\n\n"
            f"{get_server_specs()}"
        )
        send_message(chat_id, msg, get_main_keyboard())

    elif action in ["monitor", "link"]:
        if callback_id:
            answer_callback(callback_id)
        tunnel_url = get_tunnel_url()
        msg = (
            f"🌐 <b>Web Monitor URL:</b>\n\n"
            f"📱 <b>Link HP (HTTPS):</b>\n{tunnel_url}\n\n"
            f"🔑 <b>Login:</b>\n"
            f"Username: <code>user</code>\n"
            f"Password: <code>singularity</code>\n\n"
            f"<i>Buka link di atas pada browser HP untuk memantau terminal secara real-time.</i>"
        )
        send_message(chat_id, msg, get_main_keyboard())

    elif action in ["logs", "log"]:
        if callback_id:
            answer_callback(callback_id)
        msg = get_build_log(lines=25)
        send_message(chat_id, msg, get_main_keyboard())

    elif action in ["specs"]:
        if callback_id:
            answer_callback(callback_id)
        msg = get_server_specs()
        send_message(chat_id, msg, get_main_keyboard())

    elif action in ["stop_build", "stop"]:
        if not is_build_running():
            if callback_id:
                answer_callback(callback_id, "Tidak ada build yang berjalan")
            send_message(chat_id, "ℹ️ Tidak ada proses build yang sedang aktif.", get_main_keyboard())
        else:
            if callback_id:
                answer_callback(callback_id, "Menghentikan build...")
            subprocess.run([BUILD_SCRIPT, "--stop"], cwd=BUILD_DIR)
            with state_lock:
                bot_state["live_msg_id"] = None
            send_message(chat_id, "🛑 <b>Proses build telah dihentikan!</b>", get_main_keyboard())

def main():
    print("Telegram Build Bot with Antigravity AI Auto-Fix started...")
    
    worker_thread = threading.Thread(target=background_progress_worker, daemon=True)
    worker_thread.start()

    offset = 0
    while True:
        try:
            resp = requests.get(f"{BASE_URL}/getUpdates", params={"offset": offset, "timeout": 25}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    
                    if "callback_query" in update:
                        cb = update["callback_query"]
                        from_id = cb["from"]["id"]
                        if from_id == ALLOWED_CHAT_ID:
                            action = cb.get("data", "")
                            handle_action(action, from_id, cb["id"])
                        else:
                            answer_callback(cb["id"], "Unauthorized")
                        continue

                    if "message" in update and "text" in update["message"]:
                        msg = update["message"]
                        from_id = msg["from"]["id"]
                        chat_id = msg["chat"]["id"]
                        text = msg["text"].strip().lower()

                        if from_id != ALLOWED_CHAT_ID:
                            send_message(chat_id, "⛔ <b>Akses Ditolak.</b> Bot ini diproteksi khusus untuk admin server.")
                            continue

                        if text in ["/start", "/help", "help", "menu"]:
                            handle_action("menu", chat_id)
                        elif text in ["/autofix", "/fix", "autofix", "fix", "ai"]:
                            handle_action("autofix", chat_id)
                        elif text in ["/progress", "progress", "persen", "%"]:
                            handle_action("progress", chat_id)
                        elif text in ["/build", "/startbuild", "build"]:
                            handle_action("start_build", chat_id)
                        elif text in ["/status", "status"]:
                            handle_action("status", chat_id)
                        elif text in ["/monitor", "/link", "monitor", "link"]:
                            handle_action("monitor", chat_id)
                        elif text in ["/log", "/logs", "log", "logs"]:
                            handle_action("logs", chat_id)
                        elif text in ["/specs", "specs"]:
                            handle_action("specs", chat_id)
                        elif text in ["/stop", "/stopbuild", "stop"]:
                            handle_action("stop_build", chat_id)
                        else:
                            handle_action("menu", chat_id)
        except Exception as e:
            print(f"Error in polling loop: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
