"""
keep_active_pro.py
Keep-active tool with session tracking and 5 colour themes.

- Types a random letter every N seconds, then deletes it (Backspace).
- Shows the exact START time, END time, live ELAPSED timer and CYCLE count.
- The timer and counters reset on every Start, so each session is measured on its own.
- Never stops by itself: it runs until YOU press Stop or ESC (a 9-hour target bar
  is shown, and when reached the app simply keeps going).
- Every finished session is appended to keep_active_sessions.csv.

Install:  pip install pyautogui pynput
Run:      python keep_active_pro.py
"""

import csv
import os
import random
import string
import time
import tkinter as tk
from datetime import datetime

import pyautogui
from pynput import keyboard

pyautogui.PAUSE = 0.05
pyautogui.FAILSAFE = True  # mouse into a screen corner = emergency stop

TARGET_SECONDS = 9 * 3600  # 9-hour target (informational, never auto-stops)
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "keep_active_sessions.csv")
TIME_FMT = "%d %b %Y, %I:%M:%S %p"

THEMES = {
    "Light": dict(bg="#f3f5fb", card="#ffffff", fg="#1d2233", muted="#7a8194",
                  accent="#4f46e5", accent_fg="#ffffff", danger="#e5484d",
                  input="#eef0f7", border="#d9dcea", disabled="#cfd3e2"),
    "Dark": dict(bg="#111318", card="#1b1e26", fg="#e9ebf2", muted="#8b91a3",
                 accent="#7c8cff", accent_fg="#0d0f14", danger="#ff6369",
                 input="#252936", border="#2c3140", disabled="#2f3445"),
    "Ocean": dict(bg="#0a2036", card="#102f4d", fg="#e5f4ff", muted="#8fb4d0",
                  accent="#2bb8ff", accent_fg="#06223a", danger="#ff6b6b",
                  input="#163a5c", border="#1f4a72", disabled="#244e75"),
    "Forest": dict(bg="#0f221a", card="#16322a", fg="#e6f6ec", muted="#8fb5a0",
                   accent="#4cd18a", accent_fg="#0b2418", danger="#ff7a70",
                   input="#1d4136", border="#285244", disabled="#2b4f41"),
    "Sunset": dict(bg="#2a1425", card="#3a1c34", fg="#fff0e8", muted="#d2a9b8",
                   accent="#ff7a59", accent_fg="#2a1010", danger="#ff4f6d",
                   input="#4a2644", border="#5d3256", disabled="#5a3454"),
}


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class FlatButton(tk.Label):
    """Label-based button so colours work the same on Windows, macOS and Linux."""

    def __init__(self, master, text, command):
        super().__init__(master, text=text, font=("Segoe UI", 11, "bold"),
                         padx=14, pady=10, cursor="hand2")
        self.command = command
        self.enabled = True
        self.colors = ("#000", "#fff", "#888", "#ccc")
        self.bind("<Button-1>", self._click)

    def _click(self, _event):
        if self.enabled:
            self.command()

    def set_colors(self, bg, fg, dis_bg, dis_fg):
        self.colors = (bg, fg, dis_bg, dis_fg)
        self._paint()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._paint()

    def _paint(self):
        bg, fg, dis_bg, dis_fg = self.colors
        if self.enabled:
            self.configure(bg=bg, fg=fg)
        else:
            self.configure(bg=dis_bg, fg=dis_fg)


class KeepActiveApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.running = False
        self.job = None          # countdown / typing job
        self.clock_job = None    # elapsed-time job
        self.count = 0
        self.start_time = None   # datetime
        self.start_mono = None   # monotonic seconds
        self.target_logged = False
        self.theme_name = "Dark"
        self.widgets = []        # (widget, role) for theming

        root.title("Keep Active Pro")
        root.geometry("460x840")
        root.minsize(420, 680)       # can be resized / maximized / minimized freely
        root.resizable(True, True)
        self.topmost_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.apply_theme(self.theme_name)

        self.listener = keyboard.Listener(on_press=self._on_key)
        self.listener.start()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------ UI build
    def reg(self, widget, role):
        self.widgets.append((widget, role))
        return widget

    def _stat_card(self, parent, title, var, big=False, accent=False):
        card = self.reg(tk.Frame(parent, padx=12, pady=10), "card")
        self.reg(tk.Label(card, text=title, font=("Segoe UI", 9), anchor="w"),
                 "card_muted").pack(fill="x")
        self.reg(tk.Label(card, textvariable=var, anchor="w", justify="left",
                          font=("Consolas", 20 if big else 10, "bold")),
                 "card_accent" if accent else "card_fg").pack(fill="x")
        return card

    def _build_ui(self):
        main = self.reg(tk.Frame(self.root, padx=18, pady=14), "bg")
        main.pack(fill="both", expand=True)

        # Header
        self.reg(tk.Label(main, text="Keep Active Pro", anchor="w",
                          font=("Segoe UI", 19, "bold")), "bg_fg").pack(fill="x")
        self.reg(tk.Label(main, anchor="w", justify="left",
                          text="Types a random letter, then deletes it.\n"
                               "Runs until you press Stop or ESC.",
                          font=("Segoe UI", 9)), "bg_muted").pack(fill="x", pady=(0, 10))

        # Theme swatches
        theme_row = self.reg(tk.Frame(main), "bg")
        theme_row.pack(fill="x", pady=(0, 10))
        self.reg(tk.Label(theme_row, text="Theme", font=("Segoe UI", 9)),
                 "bg_muted").pack(side="left", padx=(0, 10))
        self.swatches = {}
        for name in THEMES:
            c = tk.Canvas(theme_row, width=30, height=30, highlightthickness=0,
                          cursor="hand2")
            c.pack(side="left", padx=3)
            c.bind("<Button-1>", lambda _e, n=name: self.apply_theme(n))
            self.swatches[name] = self.reg(c, "bg")
        self.theme_label_var = tk.StringVar()
        self.reg(tk.Label(theme_row, textvariable=self.theme_label_var,
                          font=("Segoe UI", 9, "bold")), "bg_fg").pack(side="left", padx=8)

        # Stats
        self.started_var = tk.StringVar(value="—")
        self.ended_var = tk.StringVar(value="—")
        self.elapsed_var = tk.StringVar(value="00:00:00")
        self.count_var = tk.StringVar(value="0")

        grid = self.reg(tk.Frame(main), "bg")
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="a")
        self._stat_card(grid, "STARTED", self.started_var).grid(
            row=0, column=0, sticky="nsew", padx=(0, 4), pady=(0, 8))
        self._stat_card(grid, "ENDED", self.ended_var).grid(
            row=0, column=1, sticky="nsew", padx=(4, 0), pady=(0, 8))
        self._stat_card(grid, "ELAPSED", self.elapsed_var, big=True, accent=True).grid(
            row=1, column=0, sticky="nsew", padx=(0, 4), pady=(0, 8))
        self._stat_card(grid, "TIMES PERFORMED", self.count_var, big=True, accent=True).grid(
            row=1, column=1, sticky="nsew", padx=(4, 0), pady=(0, 8))

        # 9-hour target progress
        prog = self.reg(tk.Frame(main, padx=12, pady=10), "card")
        prog.pack(fill="x", pady=(0, 8))
        self.target_var = tk.StringVar(value="9-hour target: 0%")
        self.reg(tk.Label(prog, textvariable=self.target_var, anchor="w",
                          font=("Segoe UI", 9)), "card_muted").pack(fill="x")
        self.progress = self.reg(tk.Canvas(prog, height=12, highlightthickness=0), "card")
        self.progress.pack(fill="x", pady=(6, 0))
        self.progress.bind("<Configure>", lambda _e: self.draw_progress(self.progress_value))
        self.progress_value = 0.0

        # Settings
        settings = self.reg(tk.Frame(main, padx=12, pady=10), "card")
        settings.pack(fill="x", pady=(0, 8))
        self.interval_var = tk.DoubleVar(value=2.0)
        self.delay_var = tk.IntVar(value=5)
        self.minimize_var = tk.BooleanVar(value=True)

        self.reg(tk.Label(settings, text="Interval (sec)", font=("Segoe UI", 10)),
                 "card_fg").grid(row=0, column=0, sticky="w")
        self.reg(tk.Spinbox(settings, from_=0.5, to=60, increment=0.5, width=6,
                            textvariable=self.interval_var, relief="flat",
                            highlightthickness=1), "entry").grid(row=0, column=1, padx=10, pady=2)
        self.reg(tk.Label(settings, text="Start delay (sec)", font=("Segoe UI", 10)),
                 "card_fg").grid(row=1, column=0, sticky="w")
        self.reg(tk.Spinbox(settings, from_=1, to=30, width=6,
                            textvariable=self.delay_var, relief="flat",
                            highlightthickness=1), "entry").grid(row=1, column=1, padx=10, pady=2)
        self.reg(tk.Checkbutton(settings, text="Minimize window on start",
                                variable=self.minimize_var, font=("Segoe UI", 10),
                                bd=0, highlightthickness=0),
                 "check").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.reg(tk.Checkbutton(settings, text="Keep window always on top",
                                variable=self.topmost_var, command=self.toggle_topmost,
                                font=("Segoe UI", 10), bd=0, highlightthickness=0),
                 "check").grid(row=3, column=0, columnspan=2, sticky="w")

        # Buttons
        btns = self.reg(tk.Frame(main), "bg")
        btns.pack(fill="x", pady=(0, 8))
        btns.columnconfigure((0, 1, 2), weight=1, uniform="b")
        self.start_btn = FlatButton(btns, "▶ Start", self.start)
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.stop_btn = FlatButton(btns, "■ Stop", self.stop)
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=3)
        self.clear_btn = FlatButton(btns, "🗑 Clear Log", self.clear_log)
        self.clear_btn.grid(row=0, column=2, sticky="ew", padx=(3, 0))
        self.stop_btn.set_enabled(False)

        # Status
        self.status_var = tk.StringVar(value="Idle")
        self.reg(tk.Label(main, textvariable=self.status_var, anchor="w",
                          font=("Segoe UI", 11, "bold")), "bg_fg").pack(fill="x")

        # Log
        self.log = self.reg(tk.Text(main, height=4, state="disabled", relief="flat",
                                    font=("Consolas", 9), padx=8, pady=6, wrap="word"),
                            "log")
        self.log.pack(fill="both", expand=True, pady=(6, 0))

    # ------------------------------------------------------------ theming
    def apply_theme(self, name):
        self.theme_name = name
        t = THEMES[name]
        self.theme = t
        self.theme_label_var.set(name)
        self.root.configure(bg=t["bg"])

        for w, role in self.widgets:
            if role == "bg":
                w.configure(bg=t["bg"])
            elif role == "bg_fg":
                w.configure(bg=t["bg"], fg=t["fg"])
            elif role == "bg_muted":
                w.configure(bg=t["bg"], fg=t["muted"])
            elif role == "card":
                w.configure(bg=t["card"])
            elif role == "card_fg":
                w.configure(bg=t["card"], fg=t["fg"])
            elif role == "card_muted":
                w.configure(bg=t["card"], fg=t["muted"])
            elif role == "card_accent":
                w.configure(bg=t["card"], fg=t["accent"])
            elif role == "entry":
                w.configure(bg=t["input"], fg=t["fg"], insertbackground=t["fg"],
                            buttonbackground=t["input"],
                            highlightbackground=t["border"],
                            highlightcolor=t["accent"],
                            disabledbackground=t["input"])
            elif role == "check":
                w.configure(bg=t["card"], fg=t["fg"], selectcolor=t["input"],
                            activebackground=t["card"], activeforeground=t["fg"])
            elif role == "log":
                w.configure(bg=t["input"], fg=t["fg"])

        self.start_btn.set_colors(t["accent"], t["accent_fg"], t["disabled"], t["muted"])
        self.stop_btn.set_colors(t["danger"], "#ffffff", t["disabled"], t["muted"])
        self.clear_btn.set_colors(t["input"], t["fg"], t["disabled"], t["muted"])

        # swatches: filled circle in each theme's accent, ring on the selected one
        for n, c in self.swatches.items():
            c.configure(bg=t["bg"])
            c.delete("all")
            c.create_oval(5, 5, 25, 25, fill=THEMES[n]["accent"],
                          outline=t["fg"] if n == name else THEMES[n]["card"],
                          width=3 if n == name else 2)
        self.draw_progress(self.progress_value)

    def draw_progress(self, fraction):
        self.progress_value = fraction
        c, t = self.progress, self.theme
        w = max(c.winfo_width(), 10)
        c.delete("all")
        c.create_rectangle(0, 0, w, 12, fill=t["input"], outline="")
        c.create_rectangle(0, 0, int(w * fraction), 12, fill=t["accent"], outline="")

    # ------------------------------------------------------------ helpers
    def _on_key(self, key):
        if key == keyboard.Key.esc and self.running:
            self.root.after(0, self.stop)  # hand over to the Tk thread

    def write_log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def save_session(self, start, end, seconds, cycles):
        try:
            new_file = not os.path.exists(LOG_FILE)
            with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if new_file:
                    writer.writerow(["start", "end", "duration", "cycles"])
                writer.writerow([start.strftime(TIME_FMT), end.strftime(TIME_FMT),
                                 fmt_duration(seconds), cycles])
        except OSError as exc:
            self.write_log(f"Could not save session log: {exc}")

    # ------------------------------------------------------------ controls
    def start(self):
        if self.running:
            return
        try:
            self.interval = max(0.5, float(self.interval_var.get()))
            delay = max(1, int(self.delay_var.get()))
        except (tk.TclError, ValueError):
            self.status_var.set("Invalid settings")
            return

        # ---- full reset for a fresh session ----
        self.count = 0
        self.start_time = None
        self.start_mono = None
        self.target_logged = False
        self.started_var.set("—")
        self.ended_var.set("—")
        self.elapsed_var.set("00:00:00")
        self.count_var.set("0")
        self.target_var.set("9-hour target: 0%")
        self.draw_progress(0)

        self.running = True
        self.start_btn.set_enabled(False)
        self.stop_btn.set_enabled(True)
        self.clear_btn.set_enabled(False)
        self.write_log(f"Starting in {delay}s - click your target window.")
        if self.minimize_var.get():
            self.root.iconify()
        self.countdown(delay)

    def countdown(self, remaining):
        if not self.running:
            return
        if remaining > 0:
            self.status_var.set(f"Starting in {remaining}...")
            self.job = self.root.after(1000, self.countdown, remaining - 1)
            return
        # Timer starts NOW, at the real current time
        self.start_time = datetime.now()
        self.start_mono = time.monotonic()
        self.started_var.set(self.start_time.strftime("%d %b %Y\n%I:%M:%S %p"))
        self.status_var.set("Running")
        self.write_log("Session started.")
        self.update_clock()
        self.tick()

    def update_clock(self):
        if not self.running or self.start_mono is None:
            return
        elapsed = time.monotonic() - self.start_mono
        self.elapsed_var.set(fmt_duration(elapsed))
        fraction = min(elapsed / TARGET_SECONDS, 1.0)
        self.draw_progress(fraction)
        if elapsed >= TARGET_SECONDS:
            self.target_var.set("9-hour target reached ✔  (still running)")
            if not self.target_logged:
                self.target_logged = True
                self.write_log("9-hour target reached. Still running until you stop.")
        else:
            left = fmt_duration(TARGET_SECONDS - elapsed)
            self.target_var.set(f"9-hour target: {fraction * 100:.1f}%   |   {left} left")
        self.clock_job = self.root.after(250, self.update_clock)

    def tick(self):
        if not self.running:
            return
        try:
            letter = random.choice(string.ascii_lowercase)
            pyautogui.write(letter)
            time.sleep(0.15)
            pyautogui.press("backspace")
            self.count += 1
            self.count_var.set(str(self.count))
            self.write_log(f"Typed and removed '{letter}'")
        except pyautogui.FailSafeException:
            self.write_log("Fail-safe triggered (mouse in corner).")
            self.stop()
            return
        except Exception as exc:  # keep the app alive on odd input errors
            self.write_log(f"Error: {exc}")
        self.job = self.root.after(int(self.interval * 1000), self.tick)

    def stop(self):
        if not self.running:
            return
        self.running = False
        for job in (self.job, self.clock_job):
            if job:
                self.root.after_cancel(job)
        self.job = self.clock_job = None

        self.start_btn.set_enabled(True)
        self.stop_btn.set_enabled(False)
        self.clear_btn.set_enabled(True)
        self.root.deiconify()
        self.root.lift()

        if self.start_time is None:  # stopped during the countdown
            self.status_var.set("Cancelled before start")
            self.write_log("Cancelled before the session began.")
            return

        end_time = datetime.now()
        seconds = time.monotonic() - self.start_mono
        self.ended_var.set(end_time.strftime("%d %b %Y\n%I:%M:%S %p"))
        self.elapsed_var.set(fmt_duration(seconds))
        self.status_var.set(f"Stopped - {self.count} cycles in {fmt_duration(seconds)}")
        self.write_log(f"Session ended. Duration {fmt_duration(seconds)}, "
                       f"{self.count} cycles.")
        self.save_session(self.start_time, end_time, seconds, self.count)

    def clear_log(self):
        """Wipe the log and reset all cycle/time displays (only when stopped).
        The saved CSV history is not touched."""
        if self.running:
            return
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.count = 0
        self.start_time = None
        self.start_mono = None
        self.started_var.set("—")
        self.ended_var.set("—")
        self.elapsed_var.set("00:00:00")
        self.count_var.set("0")
        self.target_var.set("9-hour target: 0%")
        self.draw_progress(0)
        self.status_var.set("Idle - log cleared")

    def toggle_topmost(self):
        self.root.attributes("-topmost", bool(self.topmost_var.get()))

    def on_close(self):
        if self.running:
            self.stop()
        self.listener.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    KeepActiveApp(root)
    root.mainloop()
    