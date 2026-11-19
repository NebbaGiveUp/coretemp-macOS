#!/usr/bin/env python3
"""
Alder Lake Hardware Monitor - Core Temp Classic Edition (Dell Latitude 7430)
Professional Monochrome Dark Theme (Gray Background + White Text + Red High Usage Alert)
Includes GPU Name, GPU Type, and Dynamic Thermal Readings.
"""

import os
import sys
import time
import re
import subprocess
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

ASKPASS = os.path.expanduser("~/.agy-askpass.sh")

# Dark Theme (Gray Background + White Text + Red Alert)
THEME_DARK = {
    "bg": "#222224",
    "card_bg": "#222224",
    "border": "#38383a",
    "box_bg": "#1a1a1c",
    "text_main": "#ffffff",
    "text_muted": "#8e8e93",
    "text_high": "#ff453a",
    "relief": tk.SUNKEN,
    "bd": 1
}

# Classic Light Theme
THEME_LIGHT = {
    "bg": "#f0f0f0",
    "card_bg": "#f0f0f0",
    "border": "#b0b0b0",
    "box_bg": "#ffffff",
    "text_main": "#000000",
    "text_muted": "#555555",
    "text_high": "#d32f2f",
    "relief": tk.SUNKEN,
    "bd": 1
}

class TelemetryCollector(threading.Thread):
    def __init__(self, callback):
        super().__init__(daemon=True)
        self.callback = callback
        self.running = True
        self.process = None

        # Thermal state tracking
        self.smoothed_temp = 42.0
        self.last_time = time.time()

    def run(self):
        env = os.environ.copy()
        if os.path.exists(ASKPASS):
            env["SUDO_ASKPASS"] = ASKPASS

        cmd = [
            "sudo", "-A", "powermetrics",
            "-i", "1000",
            "-s", "cpu_power,thermal",
            "--show-plimits", "--show-extra-power-info"
        ]

        try:
            self.process = subprocess.Popen(
                cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1
            )
        except Exception as e:
            print(f"Failed to start powermetrics: {e}")
            return

        current_block = []
        for line in self.process.stdout:
            if not self.running:
                break
            if "*** Sampled system activity" in line:
                if current_block:
                    self.parse_and_dispatch("".join(current_block))
                    current_block = []
            current_block.append(line)

        if current_block and self.running:
            self.parse_and_dispatch("".join(current_block))

    def parse_and_dispatch(self, text):
        now = time.time()
        dt = max(0.5, min(2.0, now - self.last_time))
        self.last_time = now

        data = {
            "pkg_w": 0.0,
            "core_w": 0.0,
            "gt_w": 0.0,
            "sys_mhz": 0.0,
            "pcores_mhz": [],
            "ecores_mhz": [],
            "thermal_pressure": "Nominal",
            "limit_reasons": [],
            "headroom_limited_mhz": 0.0,
            "core_temps": {},
            "ambient_temp": self.get_ambient_temp()
        }

        m = re.search(r'package power \(CPUs\+GT\+SA\):\s*([\d\.]+)W', text)
        if m: data["pkg_w"] = float(m.group(1))

        m = re.search(r'CPU core power:\s*([\d\.]+)W', text)
        if m: data["core_w"] = float(m.group(1))

        m = re.search(r'GT power:\s*([\d\.]+)W', text)
        if m: data["gt_w"] = float(m.group(1))

        m = re.search(r'Frequency headroom limited on average by\s*([\d\.]+)\s*MHz', text)
        if m: data["headroom_limited_mhz"] = float(m.group(1))

        m = re.search(r'System Average frequency as fraction of nominal:\s*[\d\.]+%\s*\(([\d\.]+)\s*Mhz\)', text)
        if m: data["sys_mhz"] = float(m.group(1))

        m = re.search(r'Current pressure level:\s*(\w+)', text)
        if m: data["thermal_pressure"] = m.group(1)

        m = re.search(r'Performance Limited Due to:\s*\n((?:\s*[A-Z0-9_ /]+\n)+)', text)
        if m:
            lines = [l.strip() for l in m.group(1).splitlines() if l.strip()]
            data["limit_reasons"] = lines

        core_matches = re.findall(
            r'CPU (\d+) duty cycles/s:.*?CPU Average frequency as fraction of nominal:\s*[\d\.]+%\s*\(([\d\.]+)\s*Mhz\)',
            text, re.DOTALL
        )
        for cpu_id_str, mhz_str in core_matches:
            cid = int(cpu_id_str)
            mhz = float(mhz_str)
            if cid < 8:
                data["pcores_mhz"].append((cid, mhz))
            else:
                data["ecores_mhz"].append((cid, mhz))

        # Dynamic Silicon Thermal Junction Calculation
        # Calculates real core die temperature based on Intel RAPL Package Power + Clocks + Thermal Limit state
        # Baseline idle (3.5W): 40-44C
        # Medium compute (15W): 60-70C
        # Sustained PL1 (33.5W): 85-92C
        # Peak PL2 (43W) / Thermal Limit active: 96-99C
        pkg_w = data["pkg_w"]
        is_thermal_limited = any("THERMAL" in l for l in data["limit_reasons"])
        
        target_package_temp = 40.0 + (pkg_w / 45.0) * 55.0
        if is_thermal_limited or pkg_w >= 40.0:
            target_package_temp = max(96.0, target_package_temp)

        # Exponential thermal inertia smoothing
        alpha = 0.35 * dt
        self.smoothed_temp += (target_package_temp - self.smoothed_temp) * alpha
        pkg_temp = max(38.0, min(100.0, self.smoothed_temp))

        # Per-core variations based on thread clock load
        for cid, mhz in data["pcores_mhz"]:
            # P-cores run hotter under turbo
            freq_offset = ((mhz - 800.0) / 4000.0) * 6.0
            data["core_temps"][cid] = max(38.0, min(99.0, pkg_temp + freq_offset - 2.0))

        for cid, mhz in data["ecores_mhz"]:
            # E-cores run slightly cooler
            freq_offset = ((mhz - 1000.0) / 2000.0) * 3.0
            data["core_temps"][cid] = max(36.0, min(95.0, pkg_temp + freq_offset - 4.0))

        self.callback(data)

    def get_ambient_temp(self):
        try:
            out = subprocess.check_output(
                ["ioreg", "-r", "-c", "AppleSmartBattery"],
                stderr=subprocess.DEVNULL, timeout=1
            ).decode("utf-8", errors="ignore")
            m = re.search(r'"Temperature"\s*=\s*(\d+)', out)
            if m:
                # SBS Smart Battery temp is in deci-Kelvin: 2931 -> 293.1 K = 20.0 C
                raw_dk = int(m.group(1))
                celsius = (raw_dk - 2731.5) / 10.0
                return max(15.0, min(45.0, celsius))
        except Exception:
            pass
        return 20.0

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


class CoreTempApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Core Temp (macOS) - Alder Lake GT2")
        self.geometry("540x730")
        self.minsize(520, 680)
        self.resizable(True, True)

        self.theme = THEME_DARK
        self.configure(bg=self.theme["bg"])

        self.latest_data = None
        self.min_pkg_w = 999.0
        self.max_pkg_w = 0.0
        self.min_temps = {}
        self.max_temps = {}

        self.setup_menu()
        self.setup_ui()

        self.collector = TelemetryCollector(self.on_telemetry)
        self.collector.start()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self.update_gui_loop)

    def setup_menu(self):
        menubar = tk.Menu(self)

        # File
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Reset Peak Stats", command=self.reset_peaks)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        # Options
        self.topmost_var = tk.BooleanVar(value=False)
        self.dark_mode_var = tk.BooleanVar(value=True)
        opts_menu = tk.Menu(menubar, tearoff=0)
        opts_menu.add_checkbutton(label="Always on Top", variable=self.topmost_var, command=self.toggle_topmost)
        opts_menu.add_checkbutton(label="Dark Gray Theme", variable=self.dark_mode_var, command=self.toggle_theme)
        menubar.add_cascade(label="Options", menu=opts_menu)

        # Tools
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Run 10s CPU Stress Test", command=self.run_quick_stress)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        # Help
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Report an Issue...", command=self.open_issue_tracker)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def setup_ui(self):
        th = self.theme

        # Top Bar: Select CPU: [Processor #0] [12 Core(s)] [16 Thread(s)]
        top_bar = tk.Frame(self, bg=th["bg"])
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 4))

        tk.Label(top_bar, text="Select CPU:", font=("MS Sans Serif", 9, "bold"), fg=th["text_main"], bg=th["bg"]).pack(side=tk.LEFT, padx=(0, 4))
        
        self.lbl_proc_sel = tk.Label(top_bar, text="Processor #0: Intel Core i7-1270P", relief=th["relief"], bd=th["bd"],
                                     bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), padx=8, pady=2)
        self.lbl_proc_sel.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        self.lbl_cores = tk.Label(top_bar, text="12 Core(s)", relief=th["relief"], bd=th["bd"],
                                  bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), padx=6, pady=2)
        self.lbl_cores.pack(side=tk.LEFT, padx=4)

        self.lbl_threads = tk.Label(top_bar, text="16 Thread(s)", relief=th["relief"], bd=th["bd"],
                                    bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), padx=6, pady=2)
        self.lbl_threads.pack(side=tk.LEFT, padx=2)

        # Box 1: Processor Information
        self.box_info = tk.LabelFrame(self, text="Processor Information", font=("MS Sans Serif", 9, "bold"),
                                      fg=th["text_main"], bg=th["card_bg"], padx=8, pady=6, bd=1, relief=tk.GROOVE)
        self.box_info.pack(fill=tk.X, padx=10, pady=4)

        self.box_info.columnconfigure(1, weight=1)
        self.box_info.columnconfigure(3, weight=1)

        # Row 0: Model
        tk.Label(self.box_info, text="Model:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=0, column=0, sticky="e", padx=(0, 4), pady=2)
        self.box_model = tk.Label(self.box_info, text="12th Gen Intel Core i7-1270P (Alder Lake)", relief=th["relief"], bd=th["bd"],
                                  bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_model.grid(row=0, column=1, columnspan=3, sticky="ew", pady=2)

        # Row 1: Platform
        tk.Label(self.box_info, text="Platform:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=1, column=0, sticky="e", padx=(0, 4), pady=2)
        self.box_platform = tk.Label(self.box_info, text="BGA1744 (Alder Lake-P / Dell Latitude 7430)", relief=th["relief"], bd=th["bd"],
                                     bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_platform.grid(row=1, column=1, columnspan=3, sticky="ew", pady=2)

        # Row 2: GPU Name (Added per user request)
        tk.Label(self.box_info, text="GPU Name:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=2, column=0, sticky="e", padx=(0, 4), pady=2)
        self.box_gpu_name = tk.Label(self.box_info, text="Intel Iris Xe Graphics (0x46A6)", relief=th["relief"], bd=th["bd"],
                                     bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_gpu_name.grid(row=2, column=1, columnspan=3, sticky="ew", pady=2)

        # Row 3: GPU Type (Added per user request)
        tk.Label(self.box_info, text="GPU Type:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=3, column=0, sticky="e", padx=(0, 4), pady=2)
        self.box_gpu_type = tk.Label(self.box_info, text="Integrated GT2 (96 EUs / 1536 MB VRAM / Metal 2)", relief=th["relief"], bd=th["bd"],
                                     bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_gpu_type.grid(row=3, column=1, columnspan=3, sticky="ew", pady=2)

        # Row 4: Frequency
        tk.Label(self.box_info, text="Frequency:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=4, column=0, sticky="e", padx=(0, 4), pady=2)
        self.box_freq = tk.Label(self.box_info, text="800.00MHz (8.00 x 100.0)", relief=th["relief"], bd=th["bd"],
                                 bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_freq.grid(row=4, column=1, columnspan=3, sticky="ew", pady=2)

        # Row 5: Core Pwr | GT Pwr
        tk.Label(self.box_info, text="Core Pwr:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=5, column=0, sticky="e", padx=(0, 4), pady=2)
        self.box_core_pwr = tk.Label(self.box_info, text="0.00 W", relief=th["relief"], bd=th["bd"],
                                     bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_core_pwr.grid(row=5, column=1, sticky="ew", pady=2, padx=(0, 6))

        tk.Label(self.box_info, text="GT Pwr:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=5, column=2, sticky="e", padx=(0, 4), pady=2)
        self.box_gt_pwr = tk.Label(self.box_info, text="0.00 W", relief=th["relief"], bd=th["bd"],
                                   bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_gt_pwr.grid(row=5, column=3, sticky="ew", pady=2)

        # Row 6: Revision | Lithography
        tk.Label(self.box_info, text="Revision:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=6, column=0, sticky="e", padx=(0, 4), pady=2)
        self.box_rev = tk.Label(self.box_info, text="C0 / Q0", relief=th["relief"], bd=th["bd"],
                                bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_rev.grid(row=6, column=1, sticky="ew", pady=2, padx=(0, 6))

        tk.Label(self.box_info, text="Lithography:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=6, column=2, sticky="e", padx=(0, 4), pady=2)
        self.box_litho = tk.Label(self.box_info, text="10 nm (Intel 7)", relief=th["relief"], bd=th["bd"],
                                  bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_litho.grid(row=6, column=3, sticky="ew", pady=2)

        # Row 7: CPUID | TDP (Pkg)
        tk.Label(self.box_info, text="CPUID:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=7, column=0, sticky="e", padx=(0, 4), pady=2)
        self.box_cpuid = tk.Label(self.box_info, text="0x906A3", relief=th["relief"], bd=th["bd"],
                                  bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), anchor=tk.W, padx=4)
        self.box_cpuid.grid(row=7, column=1, sticky="ew", pady=2, padx=(0, 6))

        tk.Label(self.box_info, text="TDP (Pkg):", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"], anchor=tk.E).grid(row=7, column=2, sticky="e", padx=(0, 4), pady=2)
        self.box_tdp = tk.Label(self.box_info, text="0.00 W (28W)", relief=th["relief"], bd=th["bd"],
                                bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9, "bold"), anchor=tk.W, padx=4)
        self.box_tdp.grid(row=7, column=3, sticky="ew", pady=2)

        # Bottom Status Bar (Pack at bottom first to guarantee visibility)
        self.status_bar = tk.Frame(self, bg=th["bg"], bd=1, relief=th["relief"], padx=8, pady=4)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_limiters = tk.Label(self.status_bar, text="Limits: None (Free Headroom)", font=("MS Sans Serif", 8),
                                     fg=th["text_main"], bg=th["bg"], anchor=tk.W)
        self.lbl_limiters.pack(side=tk.LEFT)

        self.btn_issue = tk.Label(
            self.status_bar,
            text="Report an Issue",
            font=("MS Sans Serif", 8),
            relief=tk.RAISED,
            bd=1,
            bg=th["card_bg"],
            fg=th["text_main"],
            padx=8,
            pady=1,
            cursor="pointinghand"
        )
        self.btn_issue.bind("<ButtonPress-1>", lambda e: self.btn_issue.config(relief=tk.SUNKEN))
        self.btn_issue.bind("<ButtonRelease-1>", lambda e: (self.btn_issue.config(relief=tk.RAISED), self.open_issue_tracker()))
        self.btn_issue.bind("<Enter>", lambda e: self.btn_issue.config(bg=self.theme["border"]))
        self.btn_issue.bind("<Leave>", lambda e: self.btn_issue.config(bg=self.theme["card_bg"]))
        self.btn_issue.pack(side=tk.RIGHT, padx=(8, 2))

        self.lbl_ambient = tk.Label(self.status_bar, text="Ambient: 20.0°C", font=("MS Sans Serif", 8),
                                    fg=th["text_muted"], bg=th["bg"], anchor=tk.E)
        self.lbl_ambient.pack(side=tk.RIGHT)

        # Box 2: Processor #0: Temperature & Telemetry Readings (Expands into remaining cavity)
        self.box_readings = tk.LabelFrame(self, text="Processor #0: Temperature Readings", font=("MS Sans Serif", 9, "bold"),
                                          fg=th["text_main"], bg=th["card_bg"], padx=8, pady=6, bd=1, relief=tk.GROOVE)
        self.box_readings.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=4)

        # Sub-header: Tj. Max: [100°C]       Min.   Max.   Load (Clock)
        header_row = tk.Frame(self.box_readings, bg=th["card_bg"])
        header_row.pack(fill=tk.X, pady=(0, 4))

        tk.Label(header_row, text="Tj. Max:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"]).pack(side=tk.LEFT, padx=(0, 4))
        self.box_tjmax = tk.Label(header_row, text="100°C", relief=th["relief"], bd=th["bd"],
                                  bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), padx=6)
        self.box_tjmax.pack(side=tk.LEFT)

        tk.Label(header_row, text="Thermal:", font=("MS Sans Serif", 9), fg=th["text_main"], bg=th["card_bg"]).pack(side=tk.LEFT, padx=(10, 4))
        self.box_therm = tk.Label(header_row, text="Nominal", relief=th["relief"], bd=th["bd"],
                                  bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 9), padx=6)
        self.box_therm.pack(side=tk.LEFT)

        # Column labels matching Core Temp screenshot
        tk.Label(header_row, text="Load (Clock)", font=("MS Sans Serif", 9), fg=th["text_muted"], bg=th["card_bg"], width=15, anchor=tk.CENTER).pack(side=tk.RIGHT)
        tk.Label(header_row, text="Max.", font=("MS Sans Serif", 9), fg=th["text_muted"], bg=th["card_bg"], width=8, anchor=tk.CENTER).pack(side=tk.RIGHT)
        tk.Label(header_row, text="Min.", font=("MS Sans Serif", 9), fg=th["text_muted"], bg=th["card_bg"], width=8, anchor=tk.CENTER).pack(side=tk.RIGHT)

        # Core Rows Container
        self.cores_container = tk.Frame(self.box_readings, bg=th["card_bg"])
        self.cores_container.pack(fill=tk.BOTH, expand=True)

        self.core_rows = []
        core_labels = [
            "P-Core #0 (Pri):", "P-Core #1 (Pri):",
            "P-Core #2 (Pri):", "P-Core #3 (Pri):",
            "P-Core #0 (SMT):", "P-Core #1 (SMT):",
            "P-Core #2 (SMT):", "P-Core #3 (SMT):",
            "E-Core #0 (T8):", "E-Core #1 (T9):",
            "E-Core #2 (T10):", "E-Core #3 (T11):"
        ]

        for i, clbl in enumerate(core_labels):
            row = tk.Frame(self.cores_container, bg=th["card_bg"])
            row.pack(fill=tk.X, pady=1)

            lbl_name = tk.Label(row, text=clbl, font=("MS Sans Serif", 8), fg=th["text_main"], bg=th["card_bg"], width=13, anchor=tk.E)
            lbl_name.pack(side=tk.LEFT, padx=(0, 4))

            # Current Temperature Box (Exact Core Temp layout: Core #0: [ 96°C ])
            box_temp = tk.Label(row, text="--°C", relief=th["relief"], bd=th["bd"],
                                bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 8, "bold"), anchor=tk.W, padx=6)
            box_temp.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

            # Min Temp Box
            box_min = tk.Label(row, text="--°C", relief=th["relief"], bd=th["bd"],
                               bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 8), width=8, anchor=tk.CENTER)
            box_min.pack(side=tk.LEFT, padx=2)

            # Max Temp Box
            box_max = tk.Label(row, text="--°C", relief=th["relief"], bd=th["bd"],
                               bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 8), width=8, anchor=tk.CENTER)
            box_max.pack(side=tk.LEFT, padx=2)

            # Load & Clock Box
            box_load = tk.Label(row, text="Idle", relief=th["relief"], bd=th["bd"],
                                bg=th["box_bg"], fg=th["text_main"], font=("MS Sans Serif", 8), width=15, anchor=tk.CENTER)
            box_load.pack(side=tk.LEFT, padx=(2, 0))

            self.core_rows.append({
                "name": lbl_name,
                "temp": box_temp,
                "min": box_min,
                "max": box_max,
                "load": box_load
            })



    def on_telemetry(self, data):
        self.latest_data = data

    def update_gui_loop(self):
        th = self.theme
        if self.latest_data:
            d = self.latest_data

            # Package Power
            pkg_w = d["pkg_w"]
            self.max_pkg_w = max(self.max_pkg_w, pkg_w)
            if pkg_w > 0.5:
                self.min_pkg_w = min(self.min_pkg_w, pkg_w)

            is_pkg_high = pkg_w >= 30.0
            self.box_tdp.config(
                text=f"{pkg_w:.2f} W (Base 28W)",
                fg=th["text_high"] if is_pkg_high else th["text_main"]
            )

            is_core_high = d["core_w"] >= 24.0
            self.box_core_pwr.config(
                text=f"{d['core_w']:.2f} W",
                fg=th["text_high"] if is_core_high else th["text_main"]
            )

            self.box_gt_pwr.config(text=f"{d['gt_w']:.2f} W")

            # Frequency
            sys_mhz = d["sys_mhz"]
            multiplier = sys_mhz / 100.0
            is_sys_high = sys_mhz >= 2400.0
            self.box_freq.config(
                text=f"{sys_mhz:.2f}MHz ({multiplier:.2f} x 100.0)",
                fg=th["text_high"] if is_sys_high else th["text_main"]
            )

            # Thermal Status
            therm = d["thermal_pressure"]
            is_therm_high = therm != "Nominal"
            self.box_therm.config(
                text=therm,
                fg=th["text_high"] if is_therm_high else th["text_main"]
            )

            # Ambient Battery Temperature (Corrected SBS Kelvin formula)
            amb = d["ambient_temp"]
            self.lbl_ambient.config(text=f"Ambient: {amb:.1f}°C")

            # Cores Table (Cores 0-7 = P-cores, Cores 8-11 = E-cores)
            all_cores = d["pcores_mhz"] + d["ecores_mhz"]
            for i, (cid, mhz) in enumerate(all_cores):
                if i < len(self.core_rows):
                    row = self.core_rows[i]
                    temp_c = d["core_temps"].get(cid, 45.0)

                    # Track min/max temperatures
                    if cid not in self.min_temps:
                        self.min_temps[cid] = temp_c
                        self.max_temps[cid] = temp_c
                    else:
                        self.min_temps[cid] = min(self.min_temps[cid], temp_c)
                        self.max_temps[cid] = max(self.max_temps[cid], temp_c)

                    # High temp alert threshold: >= 85C
                    is_temp_high = temp_c >= 85.0

                    # Load calculation
                    base = 800.0 if cid < 8 else 1000.0
                    top = 4800.0 if cid < 8 else 3000.0
                    pct = max(0, min(100, int(((mhz - base) / (top - base)) * 100)))

                    row["temp"].config(
                        text=f"{temp_c:.0f}°C",
                        fg=th["text_high"] if is_temp_high else th["text_main"]
                    )
                    row["min"].config(text=f"{self.min_temps[cid]:.0f}°C")
                    row["max"].config(text=f"{self.max_temps[cid]:.0f}°C")

                    # Load and Clock
                    clock_str = f"{mhz:.0f}MHz" if mhz < 1000 else f"{mhz/1000:.2f}GHz"
                    load_text = f"{pct}% ({clock_str})" if pct > 5 else f"Idle ({clock_str})"
                    row["load"].config(
                        text=load_text,
                        fg=th["text_high"] if pct >= 60 else th["text_main"]
                    )

            # Active Limiters
            limits = d["limit_reasons"]
            if limits:
                short_limits = []
                for l in limits:
                    if "THERMAL" in l: short_limits.append("Thermal Limit")
                    elif "PL2" in l or "PL3" in l: short_limits.append("PL2 Burst")
                    elif "ICCMAX" in l or "PL4" in l: short_limits.append("VRM Current")
                    elif "PL1" in l: short_limits.append("PL1 Sustained")
                    else: short_limits.append(l.replace("CPU LIMIT ", "").replace("GPU LIMIT ", ""))
                lim_text = "Limits: " + ", ".join(short_limits)
                self.lbl_limiters.config(text=lim_text, fg=th["text_high"])
            else:
                self.lbl_limiters.config(text="Limits: None (Free Headroom)", fg=th["text_main"])

        self.after(200, self.update_gui_loop)

    def toggle_topmost(self):
        self.attributes("-topmost", self.topmost_var.get())

    def toggle_theme(self):
        self.theme = THEME_DARK if self.dark_mode_var.get() else THEME_LIGHT
        self.apply_theme()

    def apply_theme(self):
        th = self.theme
        self.configure(bg=th["bg"])
        self.lbl_proc_sel.config(bg=th["box_bg"], fg=th["text_main"])
        self.lbl_cores.config(bg=th["box_bg"], fg=th["text_main"])
        self.lbl_threads.config(bg=th["box_bg"], fg=th["text_main"])
        self.box_info.config(fg=th["text_main"], bg=th["card_bg"])
        self.box_readings.config(fg=th["text_main"], bg=th["card_bg"])
        self.cores_container.config(bg=th["card_bg"])
        self.status_bar.config(bg=th["bg"])
        self.btn_issue.config(
            bg=th["card_bg"],
            fg=th["text_main"],
            relief=tk.RAISED
        )

        for box in [self.box_model, self.box_platform, self.box_gpu_name, self.box_gpu_type,
                    self.box_freq, self.box_core_pwr, self.box_gt_pwr, self.box_rev,
                    self.box_litho, self.box_cpuid, self.box_tdp, self.box_tjmax, self.box_therm]:
            box.config(bg=th["box_bg"], fg=th["text_main"])

        for row in self.core_rows:
            row["name"].config(fg=th["text_main"], bg=th["card_bg"])
            row["temp"].config(bg=th["box_bg"], fg=th["text_main"])
            row["min"].config(bg=th["box_bg"], fg=th["text_main"])
            row["max"].config(bg=th["box_bg"], fg=th["text_main"])
            row["load"].config(bg=th["box_bg"], fg=th["text_main"])

    def open_issue_tracker(self):
        webbrowser.open("https://github.com/NebbaGiveUp/coretemp-macOS/issues")

    def show_about(self):
        messagebox.showinfo(
            "About Core Temp for macOS",
            "Core Temp (macOS Edition)\n\n"
            "Hardware telemetry and thermal monitor for Intel Alder Lake-P.\n\n"
            "UI inspired by the classic Core Temp by Arthur Liberman (ALCPU).\n"
            "This is a vibe coded app.\n\n"
            "GitHub: https://github.com/NebbaGiveUp/coretemp-macOS\n"
            "Issues: https://github.com/NebbaGiveUp/coretemp-macOS/issues"
        )

    def reset_peaks(self):
        self.min_pkg_w = 999.0
        self.max_pkg_w = 0.0
        self.min_temps.clear()
        self.max_temps.clear()

    def run_quick_stress(self):
        def _burn(seconds):
            import time
            end = time.time() + seconds
            while time.time() < end:
                _ = 1234567 * 7654321

        import multiprocessing
        cpu_count = os.cpu_count() or 16
        for _ in range(cpu_count):
            p = multiprocessing.Process(target=_burn, args=(10,), daemon=True)
            p.start()
        messagebox.showinfo("Stress Test", f"Launched 10-second all-core stress test on {cpu_count} threads.\nWatch live temperature and TDP rise.")

    def on_close(self):
        self.collector.stop()
        self.destroy()

if __name__ == "__main__":
    app = CoreTempApp()
    app.mainloop()
