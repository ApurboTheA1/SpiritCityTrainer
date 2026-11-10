"""
Spirit City: Lofi Sessions — All-in-One Desktop Trainer
Cozy Dark-Mode UI built on top of ue_engine.SpiritCityEngine.
"""

from __future__ import annotations

import os
import shutil
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from tkinter import ttk
from typing import Callable, Optional, Sequence, Tuple

from ue_engine import GameSnapshot, SpiritCityEngine


# --- Cozy Lofi Color Palette ---
BG = "#13131f"
CARD = "#1c1c2e"
SURFACE = "#26263d"
ACCENT = "#a78bfa"
ACCENT_HOVER = "#c4b5fd"
GOLD = "#f6c177"
MINT = "#73daca"
ROSE = "#eb6f92"
TEXT = "#e0def4"
MUTED = "#908caa"
BORDER = "#313244"


@dataclass
class _MultiplierChannel:
    """Binds a multiplier toggle, slider, presets, custom input, and engine setter."""

    var_on: tk.BooleanVar
    var_slider: tk.DoubleVar
    var_custom: tk.StringVar
    lbl_big: tk.Label
    push: Callable[[Optional[float]], None]


class SpiritCityTrainerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Spirit City: Lofi Sessions — Trainer")
        self.root.geometry("860x740")
        self.root.minsize(780, 660)
        self.root.configure(bg=BG)

        self.engine = SpiritCityEngine()

        # Header & progression variables
        self.var_status = tk.StringVar(value="Waiting to attach...")
        self.var_lvl_badge = tk.StringVar(value="LVL --")
        self.var_xp_text = tk.StringVar(value="XP: -- / --")
        self.var_credits_text = tk.StringVar(value="Spirit Credits: --")
        self.var_spirits_text = tk.StringVar(value="Spirits: -- / --")
        self.var_playtime_text = tk.StringVar(value="Playtime Today: --")
        self.var_xp_telemetry = tk.StringVar(value="Intercepted XP Calls: 0  |  Last Gain: --")

        self.var_free_shop = tk.BooleanVar(value=False)
        self.var_unlim_daily = tk.BooleanVar(value=False)

        self.var_grant_xp = tk.StringVar(value="500")
        self.var_grant_xp_use_mult = tk.BooleanVar(value=False)
        self.var_grant_cr = tk.StringVar(value="5000")
        self.var_set_xp = tk.StringVar(value="")
        self.var_set_lvl = tk.StringVar(value="")
        self.var_sync_xp_on_lvl = tk.BooleanVar(value=True)
        self.var_set_cr = tk.StringVar(value="")

        # World / Speed / Pomodoro variables
        self.var_game_speed = tk.DoubleVar(value=1.0)
        self.var_speed_label = tk.StringVar(value="1.00x")
        self.var_sync_clock = tk.BooleanVar(value=True)
        self.var_tod_label = tk.StringVar(value="Current: --")
        self.var_train_speed = tk.DoubleVar(value=1000.0)
        self.var_train_shake = tk.DoubleVar(value=1.0)
        self.var_pomo_status = tk.StringVar(value="Timer / Pomodoro: --")
        self.var_stopwatch_sec = tk.StringVar(value="3600")
        self.var_muted = tk.BooleanVar(value=False)
        self.var_hide_ui = tk.BooleanVar(value=False)
        self.var_parallax = tk.DoubleVar(value=20.0)
        self.var_playtime_min = tk.StringVar(value="60")

        # Spirits variables
        self.var_fast_lure_on = tk.BooleanVar(value=False)
        self.var_fast_lure_sec = tk.DoubleVar(value=0.05)
        self.var_max_friend_val = tk.StringVar(value="999")
        self.var_edit_friend_val = tk.StringVar(value="500")

        # Tools & status variables
        self.var_pkgs_label = tk.StringVar(value="Owned Content Packages: --")
        self.var_toast = tk.StringVar(value="Ready.")

        self._setup_styles()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.after(200, self.attach_game)
        self.root.after(700, self._poll_loop)

    # --- Styling & Reusable Widget Helpers ---
    def _setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=SURFACE,
            foreground=MUTED,
            padding=(14, 8),
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACCENT_HOVER)])
        style.configure("TProgressbar", troughcolor=SURFACE, background=MINT, thickness=10, borderwidth=0)
        style.configure(
            "Treeview", background=SURFACE, foreground=TEXT, fieldbackground=SURFACE, rowheight=24, borderwidth=0
        )
        style.configure(
            "Treeview.Heading", background=CARD, foreground=ACCENT_HOVER, font=("Segoe UI", 9, "bold"), borderwidth=0
        )
        style.map("Treeview", background=[("selected", "#3b3b5c")])

    def _card(self, parent: tk.Widget, title: str, accent: str = ACCENT) -> tk.Frame:
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="x", padx=12, pady=6)
        inner = tk.Frame(outer, bg=CARD, padx=14, pady=10)
        inner.pack(fill="x")
        tk.Label(inner, text=title, bg=CARD, fg=accent, font=("Segoe UI", 10, "bold"), anchor="w").pack(
            fill="x", pady=(0, 6)
        )
        return inner

    def _btn(
        self,
        parent: tk.Widget,
        text: str,
        cmd: Callable[[], None],
        bg: str = SURFACE,
        fg: str = TEXT,
        padx: int = 10,
        pady: int = 4,
    ) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=bg,
            fg=fg,
            activebackground=ACCENT,
            activeforeground="#11111b",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=padx,
            pady=pady,
        )

    def _check(
        self,
        parent: tk.Widget,
        text: str,
        var: tk.BooleanVar,
        cmd: Callable[[], None],
        bold: bool = False,
        fg: str = TEXT,
    ) -> tk.Checkbutton:
        font = ("Segoe UI", 9, "bold") if bold else ("Segoe UI", 9)
        return tk.Checkbutton(
            parent,
            text=text,
            variable=var,
            command=cmd,
            bg=CARD,
            fg=fg,
            selectcolor=SURFACE,
            activebackground=CARD,
            activeforeground=TEXT,
            font=font,
        )

    def _entry(
        self,
        parent: tk.Widget,
        var: tk.StringVar,
        width: int = 8,
        on_enter: Optional[Callable[[], None]] = None,
    ) -> tk.Entry:
        ent = tk.Entry(parent, textvariable=var, width=width, bg=SURFACE, fg=TEXT, insertbackground=TEXT, relief="flat")
        if on_enter:
            ent.bind("<Return>", lambda _: on_enter())
        return ent

    def _scale(
        self,
        parent: tk.Widget,
        var: tk.DoubleVar,
        frm: float,
        to: float,
        res: float,
        cmd: Optional[Callable[[str], None]] = None,
        accent: str = ACCENT,
        length: Optional[int] = None,
        showvalue: bool = False,
    ) -> tk.Scale:
        kwargs = dict(
            from_=frm,
            to=to,
            resolution=res,
            orient="horizontal",
            variable=var,
            bg=CARD,
            fg=TEXT,
            troughcolor=SURFACE,
            highlightthickness=0,
            activebackground=accent,
            showvalue=showvalue,
        )
        if cmd is not None:
            kwargs["command"] = cmd
        if length is not None:
            kwargs["length"] = length
        return tk.Scale(parent, **kwargs)

    def _scrollable_tab(self, notebook: ttk.Notebook, title: str) -> tk.Frame:
        container = tk.Frame(notebook, bg=BG)
        notebook.add(container, text=title)
        canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        def _on_wheel(ev: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_wheel))
        canvas.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))
        return inner

    def _build_multiplier_card(
        self,
        parent: tk.Frame,
        title: str,
        toggle_label: str,
        accent: str,
        default_enabled: bool,
        presets: Sequence[Tuple[float, str]],
        engine_setter: Callable[[bool, float], None],
        telemetry_var: Optional[tk.StringVar] = None,
    ) -> _MultiplierChannel:
        card = self._card(parent, title, accent)
        var_on = tk.BooleanVar(value=default_enabled)
        var_slider = tk.DoubleVar(value=1.0)
        var_custom = tk.StringVar(value="1.0")

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", pady=(0, 6))
        lbl_big = tk.Label(top, text="1.00x", bg=CARD, fg=accent, font=("Segoe UI", 15, "bold"))

        def push(override: Optional[float] = None) -> None:
            try:
                val = override if override is not None else float(var_custom.get() or var_slider.get())
            except ValueError:
                val = float(var_slider.get())
            if self.engine.is_alive():
                engine_setter(var_on.get(), max(0.0, val))

        def on_slider(_: str = "") -> None:
            val = round(float(var_slider.get()), 2)
            lbl_big.configure(text=f"{val:.2f}x")
            var_custom.set(f"{val:.2f}")
            push(val)

        def set_val(val: float) -> None:
            val = max(0.0, float(val))
            if val <= 50.0:
                var_slider.set(val)
            var_custom.set(f"{val:g}")
            lbl_big.configure(text=f"{val:.2f}x")
            var_on.set(True)
            push(val)

        def apply_custom() -> None:
            try:
                set_val(float(var_custom.get()))
            except ValueError:
                self._toast(f"Invalid {title.split()[0]} multiplier number.")

        chk = self._check(top, toggle_label, var_on, lambda: push(), bold=True)
        chk.configure(font=("Segoe UI", 10, "bold"))
        chk.pack(side="left")
        lbl_big.pack(side="right")

        self._scale(card, var_slider, 0.0, 50.0, 0.25, cmd=on_slider, accent=accent).pack(fill="x", pady=(0, 6))

        prow = tk.Frame(card, bg=CARD)
        prow.pack(fill="x", pady=(0, 4 if telemetry_var else 0))
        for val, lbl in presets:
            self._btn(prow, lbl, lambda v=val: set_val(v), padx=8, pady=3).pack(side="left", padx=(0, 4))

        tk.Label(prow, text="Custom:", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(10, 4))
        self._entry(prow, var_custom, width=7, on_enter=apply_custom).pack(side="left", padx=(0, 4))
        self._btn(prow, "Apply", apply_custom, bg=accent, fg="#11111b", padx=8, pady=3).pack(side="left")

        if telemetry_var is not None:
            tk.Label(card, textvariable=telemetry_var, bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(
                fill="x", pady=(4, 0)
            )

        return _MultiplierChannel(
            var_on=var_on, var_slider=var_slider, var_custom=var_custom, lbl_big=lbl_big, push=push
        )

    # --- Build Full UI ---
    def _build_ui(self) -> None:
        hdr = tk.Frame(self.root, bg=CARD, padx=16, pady=12)
        hdr.pack(fill="x")

        top_row = tk.Frame(hdr, bg=CARD)
        top_row.pack(fill="x")
        tk.Label(
            top_row, text="Spirit City: Lofi Sessions  —  Trainer", bg=CARD, fg=ACCENT_HOVER, font=("Segoe UI", 14, "bold")
        ).pack(side="left")

        btn_box = tk.Frame(top_row, bg=CARD)
        btn_box.pack(side="right")
        self._btn(btn_box, "Save Game", self._act_save, bg="#2d3b55", fg=MINT).pack(side="right", padx=(6, 0))
        self._btn(btn_box, "Re-Attach", self.attach_game, bg=ACCENT, fg="#11111b").pack(side="right")

        self.lbl_status = tk.Label(hdr, textvariable=self.var_status, bg=CARD, fg=GOLD, font=("Segoe UI", 9), anchor="w")
        self.lbl_status.pack(fill="x", pady=(4, 8))

        stats_row = tk.Frame(hdr, bg=SURFACE, padx=10, pady=8)
        stats_row.pack(fill="x")
        tk.Label(
            stats_row, textvariable=self.var_lvl_badge, bg=ACCENT, fg="#11111b", font=("Segoe UI", 10, "bold"), padx=8, pady=2
        ).pack(side="left", padx=(0, 10))
        tk.Label(stats_row, textvariable=self.var_xp_text, bg=SURFACE, fg=MINT, font=("Segoe UI", 10, "bold")).pack(
            side="left", padx=(0, 14)
        )
        tk.Label(stats_row, textvariable=self.var_credits_text, bg=SURFACE, fg=GOLD, font=("Segoe UI", 10, "bold")).pack(
            side="left", padx=(0, 14)
        )
        tk.Label(stats_row, textvariable=self.var_spirits_text, bg=SURFACE, fg=TEXT, font=("Segoe UI", 9)).pack(
            side="left", padx=(0, 14)
        )
        tk.Label(stats_row, textvariable=self.var_playtime_text, bg=SURFACE, fg=MUTED, font=("Segoe UI", 9)).pack(
            side="right"
        )

        self.pb_xp = ttk.Progressbar(hdr, mode="determinate", maximum=100)
        self.pb_xp.pack(fill="x", pady=(6, 0))

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        self._build_progression_tab(self._scrollable_tab(nb, "EXP & Progression"))
        self._build_world_tab(self._scrollable_tab(nb, "World, Speed & Timer"))
        self._build_spirits_tab(self._scrollable_tab(nb, "Spirits & Friendship"))
        self._build_tools_tab(self._scrollable_tab(nb, "Unlocks & Dev Tools"))

        foot = tk.Frame(self.root, bg=CARD, padx=14, pady=6)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot, textvariable=self.var_toast, bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(fill="x")

    # --- Tab 1: Progression & Multipliers ---
    def _build_progression_tab(self, parent: tk.Frame) -> None:
        self.xp_mult = self._build_multiplier_card(
            parent,
            title="EXP Earned Multiplier (All Sources: Minute Ticks, Pomodoro, Todo, Login, Spirits)",
            toggle_label="Enable EXP Multiplier",
            accent=MINT,
            default_enabled=True,
            presets=[(0.0, "0x"), (0.5, "0.5x"), (1.0, "1x"), (2.0, "2x"), (5.0, "5x"), (10.0, "10x"), (25.0, "25x"), (50.0, "50x"), (100.0, "100x")],
            engine_setter=self.engine.set_xp_multiplier,
            telemetry_var=self.var_xp_telemetry,
        )

        self.cr_mult = self._build_multiplier_card(
            parent,
            title="Spirit Credits Earned Multiplier",
            toggle_label="Enable Credits Multiplier",
            accent=GOLD,
            default_enabled=False,
            presets=[(1.0, "1x"), (2.0, "2x"), (5.0, "5x"), (10.0, "10x"), (25.0, "25x"), (50.0, "50x")],
            engine_setter=self.engine.set_credits_multiplier,
        )

        c_tog = self._card(parent, "Economy & Daily Bonuses")
        self._check(
            c_tog,
            "Free Shop / Zero Cost Purchases  (Wardrobe, Room, Garden, Train, Library & Skins cost 0 Credits)",
            self.var_free_shop,
            self._push_free_shop,
            bold=True,
        ).pack(anchor="w", pady=2)
        self._check(
            c_tog,
            "Unlimited Daily EXP & Credits Bonus  (Keeps +100 EXP & +100 Credits active for every Todo/Pomo)",
            self.var_unlim_daily,
            self._toggle_unlim_daily,
            bold=True,
        ).pack(anchor="w", pady=2)

        c_ed = self._card(parent, "Instant Grant & Direct Stat Editors")
        row_gxp = tk.Frame(c_ed, bg=CARD)
        row_gxp.pack(fill="x", pady=3)
        tk.Label(row_gxp, text="Grant XP (Native + Level-Up):", bg=CARD, fg=TEXT, width=24, anchor="w").pack(side="left")
        self._entry(row_gxp, self.var_grant_xp, width=10, on_enter=self._act_grant_xp).pack(side="left", padx=(0, 6))
        self._btn(row_gxp, "Grant XP", self._act_grant_xp, bg=MINT, fg="#11111b").pack(side="left", padx=(0, 4))
        for amt in (100, 500, 1000, 5000):
            self._btn(row_gxp, f"+{amt}", lambda a=amt: self._act_grant_xp_amt(a), padx=6, pady=3).pack(
                side="left", padx=(0, 3)
            )
        self._check(row_gxp, "Use Mult", self.var_grant_xp_use_mult, lambda: None, fg=MUTED).pack(side="left", padx=(4, 0))

        row_gcr = tk.Frame(c_ed, bg=CARD)
        row_gcr.pack(fill="x", pady=3)
        tk.Label(row_gcr, text="Grant Spirit Credits (Native):", bg=CARD, fg=TEXT, width=24, anchor="w").pack(side="left")
        self._entry(row_gcr, self.var_grant_cr, width=10, on_enter=self._act_grant_credits).pack(side="left", padx=(0, 6))
        self._btn(row_gcr, "Grant Credits", self._act_grant_credits, bg=GOLD, fg="#11111b").pack(side="left", padx=(0, 4))
        for amt in (500, 5000, 50000, 500000):
            self._btn(row_gcr, f"+{amt:,}", lambda a=amt: self._act_grant_credits_amt(a), padx=6, pady=3).pack(
                side="left", padx=(0, 3)
            )

        tk.Frame(c_ed, bg=BORDER, height=1).pack(fill="x", pady=8)

        row_set = tk.Frame(c_ed, bg=CARD)
        row_set.pack(fill="x", pady=2)
        tk.Label(row_set, text="Set Exact Total XP:", bg=CARD, fg=MUTED).pack(side="left")
        self._entry(row_set, self.var_set_xp, width=9, on_enter=self._act_set_xp).pack(side="left", padx=4)
        self._btn(row_set, "Set XP", self._act_set_xp).pack(side="left", padx=(0, 12))

        tk.Label(row_set, text="Set Level:", bg=CARD, fg=MUTED).pack(side="left")
        self._entry(row_set, self.var_set_lvl, width=6, on_enter=self._act_set_lvl).pack(side="left", padx=4)
        self._btn(row_set, "Set Lvl", self._act_set_lvl).pack(side="left", padx=(0, 6))
        self._check(row_set, "Sync XP", self.var_sync_xp_on_lvl, lambda: None, fg=MUTED).pack(side="left")

        row_set2 = tk.Frame(c_ed, bg=CARD)
        row_set2.pack(fill="x", pady=(6, 0))
        tk.Label(row_set2, text="Set Exact Credits:", bg=CARD, fg=MUTED).pack(side="left")
        self._entry(row_set2, self.var_set_cr, width=10, on_enter=self._act_set_credits).pack(side="left", padx=4)
        self._btn(row_set2, "Set Credits", self._act_set_credits).pack(side="left", padx=(0, 14))
        self._btn(row_set2, "Trigger Level Up (+500 Credits)", self._act_level_up, bg=ACCENT, fg="#11111b").pack(
            side="right"
        )

    # --- Tab 2: World, Speed & Timer ---
    def _build_world_tab(self, parent: tk.Frame) -> None:
        c_spd = self._card(parent, "Game Speed (WorldSettings TimeDilation)", ACCENT)
        r_spd = tk.Frame(c_spd, bg=CARD)
        r_spd.pack(fill="x")
        tk.Label(r_spd, text="Speed Multiplier (affects animations, luring & world):", bg=CARD, fg=TEXT).pack(side="left")
        tk.Label(r_spd, textvariable=self.var_speed_label, bg=CARD, fg=ACCENT_HOVER, font=("Segoe UI", 13, "bold")).pack(
            side="right"
        )
        self._scale(c_spd, self.var_game_speed, 0.1, 20.0, 0.1, cmd=self._on_speed_slider, accent=ACCENT).pack(
            fill="x", pady=4
        )
        p_spd = tk.Frame(c_spd, bg=CARD)
        p_spd.pack(fill="x")
        for v, lbl in ((0.5, "0.5x Slow"), (1.0, "1.0x Normal"), (2.0, "2x"), (5.0, "5x"), (10.0, "10x"), (20.0, "20x")):
            self._btn(p_spd, lbl, lambda val=v: self._set_speed(val), padx=10, pady=3).pack(side="left", padx=(0, 5))

        c_tod = self._card(parent, "Time of Day & Lighting Override", GOLD)
        r_tod = tk.Frame(c_tod, bg=CARD)
        r_tod.pack(fill="x", pady=(0, 6))
        self._check(
            r_tod,
            "Sync with Real-Life Clock (uncheck to lock custom lighting)",
            self.var_sync_clock,
            self._act_toggle_clock,
        ).pack(side="left")
        tk.Label(r_tod, textvariable=self.var_tod_label, bg=CARD, fg=GOLD, font=("Segoe UI", 9, "bold")).pack(side="right")
        b_tod = tk.Frame(c_tod, bg=CARD)
        b_tod.pack(fill="x")
        for idx, lbl in ((0, "Morning (0)"), (1, "Day (1)"), (2, "Sunset (2)"), (3, "Night (3)")):
            self._btn(b_tod, lbl, lambda s=idx: self._act_set_tod(s), padx=12, pady=4).pack(side="left", padx=(0, 6))

        c_pom = self._card(parent, "Pomodoro, Focus Timer & Stopwatch", MINT)
        tk.Label(c_pom, textvariable=self.var_pomo_status, bg=CARD, fg=TEXT, font=("Segoe UI", 9, "bold"), anchor="w").pack(
            fill="x", pady=(0, 6)
        )
        r_pom = tk.Frame(c_pom, bg=CARD)
        r_pom.pack(fill="x")
        self._btn(
            r_pom, "Complete Active Timer / Pomodoro Segment (1s)", self._act_complete_timer, bg=MINT, fg="#11111b"
        ).pack(side="left", padx=(0, 12))
        tk.Label(r_pom, text="Set Stopwatch (sec):", bg=CARD, fg=MUTED).pack(side="left")
        self._entry(r_pom, self.var_stopwatch_sec, width=8, on_enter=self._act_set_stopwatch).pack(side="left", padx=4)
        self._btn(r_pom, "Set", self._act_set_stopwatch).pack(side="left")

        c_tr = self._card(parent, "Train Controls (All Aboard! DLC)")
        r_tr1 = tk.Frame(c_tr, bg=CARD)
        r_tr1.pack(fill="x", pady=2)
        tk.Label(r_tr1, text="Train Speed:", bg=CARD, fg=TEXT, width=18, anchor="w").pack(side="left")
        self._scale(r_tr1, self.var_train_speed, 0, 5000, 50, length=340, showvalue=True).pack(side="left", padx=6)
        self._btn(r_tr1, "Apply Speed", self._act_train_speed).pack(side="left")

        r_tr2 = tk.Frame(c_tr, bg=CARD)
        r_tr2.pack(fill="x", pady=2)
        tk.Label(r_tr2, text="Train Shake Mult:", bg=CARD, fg=TEXT, width=18, anchor="w").pack(side="left")
        self._scale(r_tr2, self.var_train_shake, 0.0, 5.0, 0.1, length=340, showvalue=True).pack(side="left", padx=6)
        self._btn(r_tr2, "Apply Shake", self._act_train_shake).pack(side="left")

        c_misc = self._card(parent, "Audio, Camera & Playtime")
        r_m1 = tk.Frame(c_misc, bg=CARD)
        r_m1.pack(fill="x", pady=2)
        self._check(r_m1, "Mute All Audio", self.var_muted, self._act_mute).pack(side="left", padx=(0, 16))
        self._check(r_m1, "Hide In-Game UI", self.var_hide_ui, self._act_hide_ui).pack(side="left", padx=(0, 16))

        tk.Label(r_m1, text="Playtime Today (min):", bg=CARD, fg=MUTED).pack(side="left", padx=(10, 4))
        self._entry(r_m1, self.var_playtime_min, width=6, on_enter=self._act_playtime).pack(side="left", padx=(0, 4))
        self._btn(r_m1, "Set", self._act_playtime).pack(side="left")

        r_m2 = tk.Frame(c_misc, bg=CARD)
        r_m2.pack(fill="x", pady=(6, 0))
        tk.Label(r_m2, text="Camera Parallax Strength:", bg=CARD, fg=TEXT).pack(side="left")
        self._scale(r_m2, self.var_parallax, 0, 100, 1, cmd=self._on_parallax_slider, length=320, showvalue=True).pack(
            side="left", padx=8
        )

    # --- Tab 3: Spirits & Friendship ---
    def _build_spirits_tab(self, parent: tk.Frame) -> None:
        c_lure = self._card(parent, "Spirit Luring & Friendship", ACCENT)
        r_l1 = tk.Frame(c_lure, bg=CARD)
        r_l1.pack(fill="x", pady=(0, 6))
        self._check(
            r_l1,
            "Fast Spirit Luring (Intercepts StartSpiritLuringTimer)",
            self.var_fast_lure_on,
            self._push_fast_lure,
            bold=True,
        ).pack(side="left")
        self._btn(r_l1, "Apply Lure Timer Now", self._act_apply_lure_now, bg=MINT, fg="#11111b").pack(side="right")

        r_l2 = tk.Frame(c_lure, bg=CARD)
        r_l2.pack(fill="x", pady=(0, 6))
        tk.Label(r_l2, text="Lure Tick Interval (seconds, normal = 60s):", bg=CARD, fg=MUTED).pack(side="left")
        self._scale(
            r_l2, self.var_fast_lure_sec, 0.05, 5.0, 0.05, cmd=lambda _: self._push_fast_lure(), length=280, showvalue=True
        ).pack(side="left", padx=8)

        r_fr = tk.Frame(c_lure, bg=CARD)
        r_fr.pack(fill="x", pady=(4, 0))
        tk.Label(r_fr, text="Friendship Score:", bg=CARD, fg=TEXT).pack(side="left")
        self._entry(r_fr, self.var_max_friend_val, width=7, on_enter=self._act_max_friendships).pack(side="left", padx=6)
        self._btn(r_fr, "Max All Discovered Friendships", self._act_max_friendships, bg=ACCENT, fg="#11111b").pack(
            side="left", padx=(0, 12)
        )
        self._btn(r_fr, "Refresh List", self._refresh_spirits_tree).pack(side="right")

        c_tbl = self._card(parent, "Spiritdex Live Inspector (Select a Spirit to edit Friendship)")
        cols = ("id", "name", "status", "friendship")
        self.tree_spirits = ttk.Treeview(c_tbl, columns=cols, show="headings", height=13)
        for col, heading, width, anchor in (
            ("id", "ID", 60, "center"),
            ("name", "Spirit Name", 260, "w"),
            ("status", "Status", 140, "center"),
            ("friendship", "Friendship Score", 130, "center"),
        ):
            self.tree_spirits.heading(col, text=heading)
            self.tree_spirits.column(col, width=width, anchor=anchor)
        sb = ttk.Scrollbar(c_tbl, orient="vertical", command=self.tree_spirits.yview)
        self.tree_spirits.configure(yscrollcommand=sb.set)
        self.tree_spirits.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        r_ed = tk.Frame(parent, bg=BG, padx=14, pady=4)
        r_ed.pack(fill="x")
        tk.Label(r_ed, text="Set Selected Spirit Friendship:", bg=BG, fg=MUTED).pack(side="left")
        self._entry(r_ed, self.var_edit_friend_val, width=8, on_enter=self._act_set_selected_friendship).pack(
            side="left", padx=6
        )
        self._btn(r_ed, "Apply to Selected", self._act_set_selected_friendship, bg=GOLD, fg="#11111b").pack(side="left")

    # --- Tab 4: Unlocks, Steam & Dev Tools ---
    def _build_tools_tab(self, parent: tk.Frame) -> None:
        c_dlc = self._card(parent, "Content Packages (DLC Slots)", GOLD)
        tk.Label(c_dlc, textvariable=self.var_pkgs_label, bg=CARD, fg=TEXT, anchor="w").pack(fill="x", pady=(0, 6))
        self._btn(c_dlc, "Unlock All Content Packages in Memory (IDs 0..12)", self._act_unlock_pkgs, bg=GOLD, fg="#11111b").pack(
            anchor="w"
        )

        c_stm = self._card(parent, "Steam Achievements Sync", MINT)
        tk.Label(
            c_stm,
            text="Triggers Spirit City's built-in retroactive Steam achievement checks for your current Level & Spirits.",
            bg=CARD,
            fg=MUTED,
            anchor="w",
        ).pack(fill="x", pady=(0, 6))
        self._btn(c_stm, "Sync Level & Spirit Steam Achievements", self._act_sync_steam, bg=MINT, fg="#11111b").pack(
            anchor="w"
        )

        c_dev = self._card(parent, "Built-in Developer Widgets", ACCENT)
        r_dev = tk.Frame(c_dev, bg=CARD)
        r_dev.pack(fill="x")
        self._btn(r_dev, "Show WBP_CheatMenu", lambda: self._act_dev_menu("cheat", True), bg=ACCENT, fg="#11111b").pack(
            side="left", padx=(0, 6)
        )
        self._btn(r_dev, "Hide WBP_CheatMenu", lambda: self._act_dev_menu("cheat", False)).pack(side="left", padx=(0, 14))
        self._btn(r_dev, "Show WBP_DebugMenu", lambda: self._act_dev_menu("debug", True), bg=SURFACE).pack(
            side="left", padx=(0, 6)
        )
        self._btn(r_dev, "Hide WBP_DebugMenu", lambda: self._act_dev_menu("debug", False)).pack(side="left")

        c_bak = self._card(parent, "Save File Backup Utility")
        tk.Label(
            c_bak,
            text=r"Creates a timestamped copy of %LOCALAPPDATA%\SpiritCity\Saved\SaveGames before experimenting.",
            bg=CARD,
            fg=MUTED,
            anchor="w",
        ).pack(fill="x", pady=(0, 6))
        self._btn(c_bak, "Backup SaveGames Folder Now", self._act_backup_saves, bg="#2d3b55", fg=MINT).pack(anchor="w")

    # --- Connection & Polling ---
    def attach_game(self) -> None:
        try:
            self.engine.attach()
            self.var_status.set(f"● CONNECTED  |  PID {self.engine.pid}  |  Base 0x{self.engine.base:X}  |  x64 Hook Active")
            self.lbl_status.configure(fg=MINT)
            self.xp_mult.push(None)
            self.cr_mult.push(None)
            self._push_free_shop()
            self._push_fast_lure()
            self._refresh_spirits_tree()
            self._toast("Attached & x64 hook installed cleanly!")
        except Exception as exc:
            self.var_status.set(f"○ NOT ATTACHED  |  {exc}")
            self.lbl_status.configure(fg=ROSE)
            self._toast(str(exc))

    def _poll_loop(self) -> None:
        try:
            if self.engine.is_alive():
                snap = self.engine.get_snapshot()
                if snap.attached:
                    self._update_ui_from_snapshot(snap)
                    if self.var_unlim_daily.get() and (
                        not snap.daily_login_avail or not snap.daily_todo_avail or not snap.daily_pomo_avail
                    ):
                        self.engine.set_daily_bonuses_available(True, True, True)
            elif self.engine.pid != 0:
                self.engine.detach()
                self.var_status.set("○ GAME CLOSED  |  Click Re-Attach after launching Spirit City")
                self.lbl_status.configure(fg=ROSE)
        except Exception:
            pass
        self.root.after(600, self._poll_loop)

    def _update_ui_from_snapshot(self, s: GameSnapshot) -> None:
        self.var_lvl_badge.set(f"LVL {s.level}")
        self.var_xp_text.set(f"XP: {s.xp:,}  ({s.xp_left_next:,} to LVL {s.level + 1})")
        self.var_credits_text.set(f"Credits: {s.credits:,}")
        self.var_spirits_text.set(f"Spirits: {s.discovered_count} / {s.total_spirits}")

        mins, secs = divmod(s.playtime_today_sec, 60)
        hrs, mins = divmod(mins, 60)
        self.var_playtime_text.set(f"Today: {hrs}h {mins:02d}m {secs:02d}s")
        self.pb_xp["value"] = round(s.xp_progress_norm * 100.0, 1)

        if s.xp_calls > 0:
            self.var_xp_telemetry.set(f"Intercepted XP Calls: {s.xp_calls}  |  Last Gain: {s.last_raw_xp} → {s.last_mult_xp} XP")

        tod_names = {0: "Morning (0)", 1: "Day (1)", 2: "Sunset (2)", 3: "Night (3)"}
        self.var_tod_label.set(f"Current: {tod_names.get(s.time_of_day, s.time_of_day)}")
        self.var_sync_clock.set(s.sync_real_clock)
        self.var_muted.set(s.is_muted)
        self.var_hide_ui.set(s.is_ui_hidden)
        self.var_speed_label.set(f"{s.time_dilation:.2f}x")
        self.var_pkgs_label.set(f"Owned Content Packages ({len(s.owned_packages)}): {s.owned_packages}")

        st_map = {0: "Stopped", 1: "Running", 2: "Paused"}
        pomo_str = f"Pomodoro: {st_map.get(s.pomo_state, s.pomo_state)} (Seg {s.pomo_segment + 1}, Loops {s.pomo_loops})"
        tmr_str = f"Timer: {st_map.get(s.timer_state, s.timer_state)} ({int(s.timer_passed)}/{int(s.timer_length)}s)"
        sw_str = f"Stopwatch: {st_map.get(s.stopwatch_state, s.stopwatch_state)} ({s.stopwatch_passed}s)"
        self.var_pomo_status.set(f"{pomo_str}   |   {tmr_str}   |   {sw_str}")

    def _toast(self, msg: str) -> None:
        self.var_toast.set(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _guard(self, fn: Callable[[], None]) -> None:
        if not self.engine.is_alive():
            self._toast("Not attached to Spirit City!")
            return
        try:
            fn()
        except Exception as exc:
            self._toast(f"Error: {exc}")

    # --- Handlers: Economy & Direct Stats ---
    def _push_free_shop(self) -> None:
        if self.engine.is_alive():
            enabled = self.var_free_shop.get()
            self.engine.set_free_shop(enabled)
            self._toast(f"Free Shop {'ENABLED (0 Credits)' if enabled else 'disabled'}.")

    def _toggle_unlim_daily(self) -> None:
        enabled = self.var_unlim_daily.get()
        if enabled and self.engine.is_alive():
            self.engine.set_daily_bonuses_available(True, True, True)
        self._toast(f"Unlimited Daily Bonuses {'ENABLED' if enabled else 'disabled'}.")

    def _act_grant_xp(self) -> None:
        self._guard(lambda: self._grant_xp_impl(int(self.var_grant_xp.get())))

    def _act_grant_xp_amt(self, amt: int) -> None:
        self._guard(lambda: self._grant_xp_impl(amt))

    def _grant_xp_impl(self, amt: int) -> None:
        self.engine.add_xp(amt, notify=True, bypass_multiplier=not self.var_grant_xp_use_mult.get())
        self._toast(f"Granted +{amt:,} XP natively!")

    def _act_grant_credits(self) -> None:
        self._guard(lambda: self._grant_credits_impl(int(self.var_grant_cr.get())))

    def _act_grant_credits_amt(self, amt: int) -> None:
        self._guard(lambda: self._grant_credits_impl(amt))

    def _grant_credits_impl(self, amt: int) -> None:
        self.engine.add_credits(amt, bypass_multiplier=True)
        self._toast(f"Granted +{amt:,} Spirit Credits natively!")

    def _act_set_xp(self) -> None:
        self._guard(lambda: (self.engine.set_xp(int(self.var_set_xp.get())), self._toast("Updated Total XP!")))

    def _act_set_lvl(self) -> None:
        self._guard(
            lambda: (
                self.engine.set_level(int(self.var_set_lvl.get()), sync_xp=self.var_sync_xp_on_lvl.get()),
                self._toast("Updated Level!"),
            )
        )

    def _act_set_credits(self) -> None:
        self._guard(lambda: (self.engine.set_credits(int(self.var_set_cr.get())), self._toast("Updated Spirit Credits!")))

    def _act_level_up(self) -> None:
        self._guard(lambda: (self.engine.trigger_level_up(), self._toast("Triggered Level Up (+500 Credits)!")))

    def _act_save(self) -> None:
        self._guard(lambda: (self.engine.trigger_save(), self._toast("Saved progression cleanly to disk!")))

    # --- Handlers: World, Speed, Pomodoro ---
    def _on_speed_slider(self, _: str = "") -> None:
        val = float(self.var_game_speed.get())
        self.var_speed_label.set(f"{val:.2f}x")
        if self.engine.is_alive():
            self.engine.set_game_speed(val)

    def _set_speed(self, val: float) -> None:
        self.var_game_speed.set(val)
        self._on_speed_slider()
        self._toast(f"Game Speed set to {val:.2f}x")

    def _act_toggle_clock(self) -> None:
        self._guard(
            lambda: (
                self.engine.set_time_of_day(self.engine.get_snapshot().time_of_day, self.var_sync_clock.get()),
                self._toast(f"Real-Life Clock Sync: {self.var_sync_clock.get()}"),
            )
        )

    def _act_set_tod(self, scenario: int) -> None:
        self.var_sync_clock.set(False)
        self._guard(lambda: (self.engine.set_time_of_day(scenario, False), self._toast(f"Changed Time of Day to mode {scenario}!")))

    def _act_complete_timer(self) -> None:
        self._guard(lambda: self._toast(self.engine.complete_active_timer()))

    def _act_set_stopwatch(self) -> None:
        self._guard(
            lambda: (self.engine.set_stopwatch_seconds(int(self.var_stopwatch_sec.get())), self._toast("Updated Stopwatch TimePassed!"))
        )

    def _act_train_speed(self) -> None:
        self._guard(lambda: (self.engine.set_train_params(speed=float(self.var_train_speed.get())), self._toast("Updated Train Speed!")))

    def _act_train_shake(self) -> None:
        self._guard(
            lambda: (self.engine.set_train_params(shake=float(self.var_train_shake.get())), self._toast("Updated Train Shake Multiplier!"))
        )

    def _act_mute(self) -> None:
        self._guard(lambda: (self.engine.set_mute(self.var_muted.get()), self._toast("Updated Mute state.")))

    def _act_hide_ui(self) -> None:
        self._guard(lambda: (self.engine.set_ui_hidden(self.var_hide_ui.get()), self._toast("Updated UI visibility.")))

    def _act_playtime(self) -> None:
        self._guard(
            lambda: (self.engine.set_playtime_today(int(float(self.var_playtime_min.get()) * 60)), self._toast("Updated Playtime Today!"))
        )

    def _on_parallax_slider(self, _: str = "") -> None:
        if self.engine.is_alive():
            self.engine.set_parallax_strength(float(self.var_parallax.get()))

    # --- Handlers: Spirits ---
    def _push_fast_lure(self) -> None:
        if self.engine.is_alive():
            self.engine.set_fast_lure(self.var_fast_lure_on.get(), float(self.var_fast_lure_sec.get()))

    def _act_apply_lure_now(self) -> None:
        self.var_fast_lure_on.set(True)
        self._push_fast_lure()
        self._guard(
            lambda: (
                self.engine.apply_lure_timer_now(float(self.var_fast_lure_sec.get())),
                self._toast(f"Applied fast lure interval ({self.var_fast_lure_sec.get():.2f}s)!"),
            )
        )

    def _refresh_spirits_tree(self) -> None:
        if not self.engine.is_alive():
            return
        self.tree_spirits.delete(*self.tree_spirits.get_children())
        for s in self.engine.get_spirits():
            status = "Discovered" if s.discovered else ("Luring..." if s.luring else "Undiscovered")
            fstr = str(s.friendship) if s.friendship is not None else "-"
            self.tree_spirits.insert("", "end", iid=str(s.spirit_id), values=(s.spirit_id, s.display_name, status, fstr))

    def _act_max_friendships(self) -> None:
        def _do() -> None:
            val = int(self.var_max_friend_val.get())
            cnt = self.engine.max_all_friendships(val)
            self._refresh_spirits_tree()
            self._toast(f"Updated Friendship score to {val} on {cnt} Spirit entries!")

        self._guard(_do)

    def _act_set_selected_friendship(self) -> None:
        sel = self.tree_spirits.selection()
        if not sel:
            self._toast("Select a Spirit in the table first (must have an existing Friendship entry).")
            return
        sid = int(sel[0])

        def _do() -> None:
            val = int(self.var_edit_friend_val.get())
            if self.engine.set_spirit_friendship(sid, val):
                self._refresh_spirits_tree()
                self._toast(f"Set Spirit ID {sid} Friendship to {val}!")
            else:
                self._toast(f"Spirit ID {sid} has no Friendship map entry yet (lure/discover it first).")

        self._guard(_do)

    # --- Handlers: Unlocks, Steam, Dev, Backups ---
    def _act_unlock_pkgs(self) -> None:
        self._guard(
            lambda: (self.engine.unlock_all_content_packages(), self._toast("Unlocked all Content Packages (0..12) in memory!"))
        )

    def _act_sync_steam(self) -> None:
        self._guard(lambda: (self.engine.sync_steam_achievements(), self._toast("Triggered Steam Level & Spirit achievements check!")))

    def _act_dev_menu(self, which: str, visible: bool) -> None:
        self._guard(
            lambda: (self.engine.toggle_dev_menu(which, visible), self._toast(f"{which} menu -> {'Visible' if visible else 'Collapsed'}"))
        )

    def _act_backup_saves(self) -> None:
        src = os.path.join(os.environ.get("LOCALAPPDATA", ""), "SpiritCity", "Saved", "SaveGames")
        if not os.path.isdir(src):
            self._toast("SaveGames directory not found!")
            return
        stamp = datetime.now().strftime("TrainerBackup_%Y-%m-%d_%H-%M-%S")
        dst = os.path.join(os.environ.get("LOCALAPPDATA", ""), "SpiritCity", "Saved", "SaveGamesBackup", stamp)
        shutil.copytree(src, dst)
        self._toast(f"Backed up SaveGames to {dst}")

    def _on_close(self) -> None:
        try:
            self.engine.detach()
        finally:
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    SpiritCityTrainerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
