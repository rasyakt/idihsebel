"""
=============================================================================
Growtopia Punch Joystick Auto-Hold for LDPlayer (Enhanced Anti-Drop)
Dibuat khusus untuk menahan joystick punch Growtopia selama mungkin di LDPlayer.
Mendukung:
1. Mode Background (Bisa sambil browsing, multitasking tanpa lepas).
2. Auto-Recovery Anti-Lepas: Otomatis re-hold seketika jika Anda klik mouse di luar LDPlayer!
3. Mode Foreground (Direct Mouse fisik).
=============================================================================
"""

import sys
import os
import time
import json
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox

# Windows sound
try:
    import winsound
except ImportError:
    winsound = None

# Win32 API
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP   = 0x0202
WM_MOUSEMOVE   = 0x0200
MK_LBUTTON     = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004
MOUSEEVENTF_MOVE     = 0x0001

VK_F6       = 0x75
VK_ESCAPE   = 0x1B
VK_LBUTTON  = 0x01

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gt_config.json")

DEFAULT_CONFIG = {
    "mode": "background",
    "direction": "down",
    "center_ratio_x": 0.7596,
    "center_ratio_y": 0.7883,
    "drag_distance_ratio": 0.1140,
    "hotkey": "F6",
    "anti_afk_jitter": True,
    "auto_recover_click": True,   # Otomatis re-hold jika user klik di luar LDPlayer
    "sound_beep": True,
    "always_on_top": True,
    "auto_rehold_min": 5
}

class GTPunchHolderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Growtopia Punch Auto-Hold (LDPlayer)")
        self.root.geometry("450x660")
        self.root.minsize(440, 620)
        self.root.configure(bg="#141619")

        self.load_config()
        self.is_holding = False
        self.hold_thread = None
        self.start_time = 0
        self.hwnd_render = None
        self.hwnd_main = None

        try:
            hDesk = user32.OpenDesktopW('default', 0, False, 0x10000000 | 0x01FF)
            if hDesk:
                user32.SetThreadDesktop(hDesk)
        except Exception:
            pass

        self.setup_ui()
        self.start_hotkey_listener()
        self.update_timer_loop()

    def load_config(self):
        self.config = dict(DEFAULT_CONFIG)
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except Exception:
                pass

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print("Gagal menyimpan config:", e)

    def setup_ui(self):
        if self.config.get("always_on_top", True):
            self.root.attributes("-topmost", True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#141619", foreground="#dcdcdc", font=("Segoe UI", 9))
        style.configure("TFrame", background="#141619")
        style.configure("Card.TFrame", background="#1d2024", relief="flat")
        style.configure("Header.TLabel", background="#141619", foreground="#00e5ff", font=("Segoe UI", 13, "bold"))
        style.configure("Sub.TLabel", background="#141619", foreground="#8a9099", font=("Segoe UI", 8))
        style.configure("TRadiobutton", background="#1d2024", foreground="#ffffff", font=("Segoe UI", 9))
        style.map("TRadiobutton", background=[("active", "#1d2024")])
        style.configure("TCheckbutton", background="#1d2024", foreground="#ffffff", font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", "#1d2024")])

        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Header
        header_box = ttk.Frame(main_frame)
        header_box.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_box, text="⚡ GROWTOPIA PUNCH HOLDER", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Label(header_box, text="Auto-Hold Anti-Lepas Khusus LDPlayer | Tekan F6 untuk Mulai/Stop", style="Sub.TLabel").pack(anchor=tk.W)

        # 2. Main Action Card (Status & Big Button)
        status_card = ttk.Frame(main_frame, style="Card.TFrame", padding=12)
        status_card.pack(fill=tk.X, pady=(0, 10))

        self.lbl_status = tk.Label(status_card, text="● STATUS: STANDBY / IDLE", bg="#1d2024", fg="#aaaaaa", font=("Segoe UI", 11, "bold"))
        self.lbl_status.pack(anchor=tk.CENTER, pady=(0, 4))

        self.lbl_timer = tk.Label(status_card, text="Durasi Menahan: 00:00:00", bg="#1d2024", fg="#00e5ff", font=("Consolas", 11))
        self.lbl_timer.pack(anchor=tk.CENTER, pady=(0, 8))

        self.btn_toggle = tk.Button(
            status_card,
            text="▶ MULAI TAHAN JOYSTICK (F6)",
            font=("Segoe UI", 12, "bold"),
            bg="#00b894",
            fg="#ffffff",
            activebackground="#00a383",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=8,
            command=self.toggle_hold
        )
        self.btn_toggle.pack(fill=tk.X, pady=(4, 2))

        # 3. Mode Selection Card
        mode_card = ttk.Frame(main_frame, style="Card.TFrame", padding=12)
        mode_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(mode_card, text="PILIH MODE EKSEKUSI:", bg="#1d2024", fg="#00e5ff", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 4))

        self.var_mode = tk.StringVar(value=self.config.get("mode", "background"))
        rb_bg = ttk.Radiobutton(
            mode_card,
            text="🌐 Mode Background (Bisa Sambil Browsing/YouTube, Mouse Tetap Bebas!)",
            value="background",
            variable=self.var_mode,
            command=self.on_mode_change
        )
        rb_bg.pack(anchor=tk.W, pady=2)

        rb_fg = ttk.Radiobutton(
            mode_card,
            text="🖱️ Mode Foreground (Direct Mouse - Menggerakkan Kursor Fisik)",
            value="foreground",
            variable=self.var_mode,
            command=self.on_mode_change
        )
        rb_fg.pack(anchor=tk.W, pady=2)

        # 4. Direction Card
        dir_card = ttk.Frame(main_frame, style="Card.TFrame", padding=12)
        dir_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(dir_card, text="ARAH PUNCH JOYSTICK:", bg="#1d2024", fg="#00e5ff", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 4))

        self.var_dir = tk.StringVar(value=self.config.get("direction", "down"))
        dir_grid = ttk.Frame(dir_card, style="Card.TFrame")
        dir_grid.pack(fill=tk.X, pady=2)

        ttk.Radiobutton(dir_grid, text="⬇️ Bawah (Default Farming)", value="down", variable=self.var_dir, command=self.on_dir_change).grid(row=0, column=0, sticky="w", pady=2, padx=4)
        ttk.Radiobutton(dir_grid, text="➡️ Kanan", value="right", variable=self.var_dir, command=self.on_dir_change).grid(row=0, column=1, sticky="w", pady=2, padx=4)
        ttk.Radiobutton(dir_grid, text="⬅️ Kiri", value="left", variable=self.var_dir, command=self.on_dir_change).grid(row=1, column=0, sticky="w", pady=2, padx=4)
        ttk.Radiobutton(dir_grid, text="⬆️ Atas", value="up", variable=self.var_dir, command=self.on_dir_change).grid(row=1, column=1, sticky="w", pady=2, padx=4)
        ttk.Radiobutton(dir_grid, text="↘️ Bawah-Kanan", value="down_right", variable=self.var_dir, command=self.on_dir_change).grid(row=2, column=0, sticky="w", pady=2, padx=4)
        ttk.Radiobutton(dir_grid, text="↙️ Bawah-Kiri", value="down_left", variable=self.var_dir, command=self.on_dir_change).grid(row=2, column=1, sticky="w", pady=2, padx=4)

        # 5. Options & Anti-Drop Auto-Recovery
        opt_card = ttk.Frame(main_frame, style="Card.TFrame", padding=12)
        opt_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(opt_card, text="FITUR ANTI-LEPAS (BACKGROUND AUTO-RECOVERY):", bg="#1d2024", fg="#00e5ff", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 4))

        self.var_recover = tk.BooleanVar(value=self.config.get("auto_recover_click", True))
        cb_recover = ttk.Checkbutton(
            opt_card,
            text="🛡️ Auto-Recovery: Re-hold otomatis seketika bila mouse diklik di luar LDPlayer",
            variable=self.var_recover,
            command=self.on_opt_change
        )
        cb_recover.pack(anchor=tk.W, pady=2)

        self.var_jitter = tk.BooleanVar(value=self.config.get("anti_afk_jitter", True))
        cb_jitter = ttk.Checkbutton(
            opt_card,
            text="🔄 Anti-AFK / Anti-Stuck Jitter (Mikro gerakan kontinu agar tahan selamanya)",
            variable=self.var_jitter,
            command=self.on_opt_change
        )
        cb_jitter.pack(anchor=tk.W, pady=2)

        self.var_sound = tk.BooleanVar(value=self.config.get("sound_beep", True))
        cb_sound = ttk.Checkbutton(opt_card, text="Suara Bip saat Aktif / Berhenti", variable=self.var_sound, command=self.on_opt_change)
        cb_sound.pack(anchor=tk.W, pady=2)

        self.var_top = tk.BooleanVar(value=self.config.get("always_on_top", True))
        cb_top = ttk.Checkbutton(opt_card, text="Jendela Selalu di Atas (Always on Top)", variable=self.var_top, command=self.toggle_topmost)
        cb_top.pack(anchor=tk.W, pady=2)

        # 6. Detection & Calibration
        btn_box = ttk.Frame(main_frame)
        btn_box.pack(fill=tk.X, pady=(0, 5))

        self.btn_detect = tk.Button(
            btn_box,
            text="🔍 Auto-Deteksi LDPlayer",
            font=("Segoe UI", 9),
            bg="#2d3436",
            fg="#dfe6e9",
            activebackground="#3e484b",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            command=self.auto_detect_joystick
        )
        self.btn_detect.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.btn_reset = tk.Button(
            btn_box,
            text="↺ Reset Koordinat",
            font=("Segoe UI", 9),
            bg="#2d3436",
            fg="#dfe6e9",
            activebackground="#3e484b",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            command=self.reset_coordinates
        )
        self.btn_reset.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

        # Bottom info
        self.lbl_info = tk.Label(main_frame, text="LDPlayer Siap. Tekan F6 untuk Aktifkan.", bg="#141619", fg="#636e72", font=("Segoe UI", 8))
        self.lbl_info.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))

    def on_mode_change(self):
        self.config["mode"] = self.var_mode.get()
        self.save_config()

    def on_dir_change(self):
        self.config["direction"] = self.var_dir.get()
        self.save_config()

    def on_opt_change(self):
        self.config["auto_recover_click"] = self.var_recover.get()
        self.config["anti_afk_jitter"] = self.var_jitter.get()
        self.config["sound_beep"] = self.var_sound.get()
        self.save_config()

    def toggle_topmost(self):
        val = self.var_top.get()
        self.config["always_on_top"] = val
        self.root.attributes("-topmost", val)
        self.save_config()

    def find_ldplayer_windows(self):
        hwnd_main = user32.FindWindowW("LDPlayerMainFrame", None)
        if not hwnd_main:
            def cb(hwnd, lparam):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if "LDPlayer" in buf.value:
                        lparam[0] = hwnd
                        return False
                return True
            found = [0]
            cb_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.HWND))
            user32.EnumWindows(cb_type(cb), ctypes.cast(found, wintypes.LPARAM))
            hwnd_main = found[0]

        if not hwnd_main:
            return None, None

        hwnd_render = user32.FindWindowExW(hwnd_main, None, "RenderWindow", "TheRender")
        if not hwnd_render:
            hwnd_render = user32.FindWindowExW(hwnd_main, None, "subWin", "sub")
        if not hwnd_render:
            hwnd_render = user32.FindWindowExW(hwnd_main, None, "RenderWindow", None)

        return hwnd_main, hwnd_render

    def auto_detect_joystick(self):
        hwnd_main, hwnd_render = self.find_ldplayer_windows()
        if not hwnd_main or not hwnd_render:
            messagebox.showerror("Error", "Jendela LDPlayer tidak ditemukan!\nPastikan LDPlayer sudah dijalankan.")
            return

        rect = wintypes.RECT()
        user32.GetClientRect(hwnd_render, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        self.hwnd_main = hwnd_main
        self.hwnd_render = hwnd_render

        msg = f"LDPlayer Berhasil Ditemukan!\nHwnd: {hex(hwnd_main)} | Canvas: {w}x{h}\n\nFitur Auto-Recovery Anti-Lepas aktif."
        self.lbl_info.config(text=f"LDPlayer terhubung ({w}x{h}). Tekan F6 untuk Mulai.", fg="#00cec9")
        messagebox.showinfo("Terhubung", msg)

    def reset_coordinates(self):
        self.config["center_ratio_x"] = DEFAULT_CONFIG["center_ratio_x"]
        self.config["center_ratio_y"] = DEFAULT_CONFIG["center_ratio_y"]
        self.config["drag_distance_ratio"] = DEFAULT_CONFIG["drag_distance_ratio"]
        self.save_config()
        messagebox.showinfo("Reset", "Koordinat berhasil dikembalikan ke standar default Growtopia!")

    def toggle_hold(self):
        if self.is_holding:
            self.stop_hold()
        else:
            self.start_hold()

    def start_hold(self):
        if self.is_holding:
            return

        hwnd_main, hwnd_render = self.find_ldplayer_windows()
        if not hwnd_main or not hwnd_render:
            self.lbl_info.config(text="Gagal: LDPlayer tidak ditemukan!", fg="#ff7675")
            if self.config.get("sound_beep") and winsound:
                winsound.Beep(400, 200)
            return

        self.hwnd_main = hwnd_main
        self.hwnd_render = hwnd_render
        self.is_holding = True
        self.start_time = time.time()

        self.lbl_status.config(text="● STATUS: SEDANG MENAHAN JOYSTICK", fg="#00b894")
        self.btn_toggle.config(text="⏹ HENTIKAN HOLD (F6)", bg="#d63031", activebackground="#c0392b")
        mode_text = "Background (Anti-Lepas Aktif)" if self.config.get("mode") == "background" else "Foreground"
        self.lbl_info.config(text=f"Aktif [{mode_text}]. Tekan F6/ESC utk stop.", fg="#55efc4")

        if self.config.get("sound_beep") and winsound:
            winsound.Beep(1000, 150)

        self.hold_thread = threading.Thread(target=self._run_hold_loop, daemon=True)
        self.hold_thread.start()

    def stop_hold(self):
        if not self.is_holding:
            return

        self.is_holding = False
        self.lbl_status.config(text="● STATUS: STANDBY / IDLE", fg="#aaaaaa")
        self.btn_toggle.config(text="▶ MULAI TAHAN JOYSTICK (F6)", bg="#00b894", activebackground="#00a383")
        self.lbl_info.config(text="Hold dihentikan. Tekan F6 untuk mengaktifkan kembali.", fg="#636e72")

        if self.config.get("sound_beep") and winsound:
            winsound.Beep(600, 150)

    def _get_target_offsets(self, distance):
        direction = self.config.get("direction", "down")
        dx, dy = 0, 0
        if direction == "down":
            dy = distance
        elif direction == "up":
            dy = -distance
        elif direction == "right":
            dx = distance
        elif direction == "left":
            dx = -distance
        elif direction == "down_right":
            dx = int(distance * 0.707)
            dy = int(distance * 0.707)
        elif direction == "down_left":
            dx = -int(distance * 0.707)
            dy = int(distance * 0.707)
        return dx, dy

    def _run_hold_loop(self):
        mode = self.config.get("mode", "background")
        hwnd_render = self.hwnd_render

        if mode == "background":
            self._run_background_hold(hwnd_render)
        else:
            self._run_foreground_hold(hwnd_render)

    def _run_background_hold(self, hwnd_render):
        """Menahan joystick dengan sistem Auto-Recovery Anti-Lepas saat klik luar"""
        def make_lparam(x, y):
            return (int(y) << 16) | (int(x) & 0xFFFF)

        rect = wintypes.RECT()
        user32.GetClientRect(hwnd_render, ctypes.byref(rect))
        w = max(rect.right - rect.left, 100)
        h = max(rect.bottom - rect.top, 100)

        cx_ratio = self.config.get("center_ratio_x", DEFAULT_CONFIG["center_ratio_x"])
        cy_ratio = self.config.get("center_ratio_y", DEFAULT_CONFIG["center_ratio_y"])
        dist_ratio = self.config.get("drag_distance_ratio", DEFAULT_CONFIG["drag_distance_ratio"])

        start_x = int(w * cx_ratio)
        start_y = int(h * cy_ratio)
        dist_px = int(h * dist_ratio)
        dx, dy = self._get_target_offsets(dist_px)
        end_x = start_x + dx
        end_y = start_y + dy

        def perform_drag():
            # Inisiasi sentuhan di pusat joystick lalu drag ke arah target
            user32.PostMessageW(hwnd_render, WM_MOUSEMOVE, 0, make_lparam(start_x, start_y))
            time.sleep(0.01)
            user32.PostMessageW(hwnd_render, WM_LBUTTONDOWN, MK_LBUTTON, make_lparam(start_x, start_y))
            time.sleep(0.015)
            steps = 8
            for i in range(1, steps + 1):
                cur_x = int(start_x + (end_x - start_x) * (i / float(steps)))
                cur_y = int(start_y + (end_y - start_y) * (i / float(steps)))
                user32.PostMessageW(hwnd_render, WM_MOUSEMOVE, MK_LBUTTON, make_lparam(cur_x, cur_y))
                time.sleep(0.01)

        # 1. Mulai drag awal
        perform_drag()

        # 2. Main Loop dengan Auto-Recovery Deteksi Klik Fisik di Luar Jendela
        counter = 0
        phys_mouse_was_down = False
        last_heartbeat = time.time()
        last_rehold = time.time()
        rehold_interval = self.config.get("auto_rehold_min", 5) * 60

        while self.is_holding:
            counter += 1

            # Deteksi apakah user baru saja mengklik mouse fisik di luar jendela LDPlayer
            if self.config.get("auto_recover_click", True):
                is_phys_down = (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0
                if is_phys_down and not phys_mouse_was_down:
                    phys_mouse_was_down = True
                elif not is_phys_down and phys_mouse_was_down:
                    # User baru saja melepaskan klik mouse di luar (misal setelah klik link Chrome)
                    phys_mouse_was_down = False
                    # Beri jeda 25ms agar pesan release dari Windows selesai, lalu langsung re-drag!
                    time.sleep(0.025)
                    perform_drag()

            # Heartbeat check: setiap 4 detik, perbarui sentuhan agar tidak ada time-out dari driver
            if time.time() - last_heartbeat > 4.0:
                last_heartbeat = time.time()
                user32.PostMessageW(hwnd_render, WM_MOUSEMOVE, MK_LBUTTON, make_lparam(end_x, end_y))

            # Auto re-hold interval berkala
            if rehold_interval > 0 and (time.time() - last_rehold) > rehold_interval:
                last_rehold = time.time()
                perform_drag()

            # Micro-jitter kontinu
            jitter_state = 1 if (self.config.get("anti_afk_jitter", True) and counter % 2 == 0) else 0
            user32.PostMessageW(hwnd_render, WM_MOUSEMOVE, MK_LBUTTON, make_lparam(end_x, end_y + jitter_state))

            time.sleep(0.05)

        # 3. Lepaskan klik saat dimatikan
        user32.PostMessageW(hwnd_render, WM_LBUTTONUP, 0, make_lparam(end_x, end_y))

    def _run_foreground_hold(self, hwnd_render):
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd_render, ctypes.byref(rect))
        w = max(rect.right - rect.left, 100)
        h = max(rect.bottom - rect.top, 100)

        cx_ratio = self.config.get("center_ratio_x", DEFAULT_CONFIG["center_ratio_x"])
        cy_ratio = self.config.get("center_ratio_y", DEFAULT_CONFIG["center_ratio_y"])
        dist_ratio = self.config.get("drag_distance_ratio", DEFAULT_CONFIG["drag_distance_ratio"])

        start_client_x = int(w * cx_ratio)
        start_client_y = int(h * cy_ratio)
        dist_px = int(h * dist_ratio)
        dx, dy = self._get_target_offsets(dist_px)
        end_client_x = start_client_x + dx
        end_client_y = start_client_y + dy

        pt_start = wintypes.POINT(start_client_x, start_client_y)
        user32.ClientToScreen(hwnd_render, ctypes.byref(pt_start))

        pt_end = wintypes.POINT(end_client_x, end_client_y)
        user32.ClientToScreen(hwnd_render, ctypes.byref(pt_end))

        user32.SetForegroundWindow(self.hwnd_main)
        time.sleep(0.1)

        user32.SetCursorPos(pt_start.x, pt_start.y)
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)

        steps = 15
        for i in range(1, steps + 1):
            if not self.is_holding:
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                return
            cx = int(pt_start.x + (pt_end.x - pt_start.x) * (i / float(steps)))
            cy = int(pt_start.y + (pt_end.y - pt_start.y) * (i / float(steps)))
            user32.SetCursorPos(cx, cy)
            time.sleep(0.015)

        counter = 0
        while self.is_holding:
            counter += 1
            if self.config.get("anti_afk_jitter", True):
                jitter = 1 if (counter % 2 == 0) else 0
                user32.SetCursorPos(pt_end.x, pt_end.y + jitter)
            time.sleep(0.05)

        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def start_hotkey_listener(self):
        def listener():
            f6_was_down = False
            esc_was_down = False
            while True:
                time.sleep(0.02)
                try:
                    f6_state = (user32.GetAsyncKeyState(VK_F6) & 0x8000) != 0
                    if f6_state and not f6_was_down:
                        f6_was_down = True
                        self.root.after(0, self.toggle_hold)
                    elif not f6_state:
                        f6_was_down = False

                    esc_state = (user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0
                    if esc_state and not esc_was_down:
                        esc_was_down = True
                        if self.is_holding:
                            self.root.after(0, self.stop_hold)
                    elif not esc_state:
                        esc_was_down = False
                except Exception:
                    pass

        t = threading.Thread(target=listener, daemon=True)
        t.start()

    def update_timer_loop(self):
        if self.is_holding and self.start_time > 0:
            elapsed = int(time.time() - self.start_time)
            h = elapsed // 3600
            m = (elapsed % 3600) // 60
            s = elapsed % 60
            self.lbl_timer.config(text=f"Durasi Menahan: {h:02d}:{m:02d}:{s:02d}")
        elif not self.is_holding:
            self.lbl_timer.config(text="Durasi Menahan: 00:00:00")

        self.root.after(500, self.update_timer_loop)

def main():
    root = tk.Tk()
    app = GTPunchHolderApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
