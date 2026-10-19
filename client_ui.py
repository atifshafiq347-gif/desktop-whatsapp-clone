# client_ui.py — UI shell: window layout, theme, chat-list rows, avatars, navigation.
from client_core import *


class UiMixin:

    def _media_dep_check(self):
        pkgs = []
        if not CV2_OK:
            pkgs += ["opencv-python", "numpy"]
        if not PYAUDIO_OK:
            pkgs.append("pyaudio")
        if not PIL_OK:
            pkgs.append("Pillow")
        if not pkgs:
            return
        self.notify("Media packages missing",
                    "This machine cannot run calls fully. Install with:   "
                    "pip install " + " ".join(pkgs),
                    kind='error', duration=12000)

    # ============================================================
    # UI SETUP
    # ============================================================
    def setup_ui(self):
        # Crisp monochrome icon font (Windows)
        self.icon_family = self._pick_icon_font()
        IF = self.icon_family

        # dark ttk theming (the ringtone dropdown is the only ttk widget)
        try:
            st = ttk.Style(self.root)
            try:
                st.theme_use('clam')
            except Exception:
                pass
            st.configure('Dark.TCombobox', fieldbackground='#1e1e1e',
                         background='#2c2c2c', foreground='#e9edef',
                         arrowcolor='#25d366', bordercolor='#3c3c3c',
                         lightcolor='#2c2c2c', darkcolor='#2c2c2c',
                         selectbackground='#1e1e1e', selectforeground='#e9edef',
                         padding=4)
            st.map('Dark.TCombobox',
                   fieldbackground=[('readonly', '#1e1e1e')],
                   foreground=[('readonly', '#e9edef')],
                   background=[('readonly', '#2c2c2c')])
            self.root.option_add('*TCombobox*Listbox.background', '#1e1e1e')
            self.root.option_add('*TCombobox*Listbox.foreground', '#e9edef')
            self.root.option_add('*TCombobox*Listbox.selectBackground', '#25d366')
            self.root.option_add('*TCombobox*Listbox.selectForeground', '#0b1a0e')
            self.root.option_add('*TCombobox*Listbox.font', '{Segoe UI} 11')
        except Exception:
            pass

        # ===== TOP BAR (full width): WhatsApp logo + bold title, panels below =====
        bar = tk.Frame(self.root, bg='#121212', height=52)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        self.logo_cv = tk.Canvas(bar, width=30, height=30, bg='#121212',
                                 highlightthickness=0, bd=0)
        self.logo_cv.pack(side=tk.LEFT, padx=(16, 9))
        self._draw_whatsapp_logo(self.logo_cv, 30)
        tk.Label(bar, text="WhatsApp", bg='#121212', fg='#e9edef',
                 font=("Segoe UI", 15, "bold")).pack(side=tk.LEFT)
        tk.Frame(self.root, bg='#2a2a2a', height=1).pack(fill=tk.X)

        # ===== MAIN CONTAINER - 3 panels below the top bar =====
        self.mc = tk.Frame(self.root, bg='#121212')
        self.mc.pack(fill=tk.BOTH, expand=True)

        # ===== PART 1: LEFT SIDEBAR =====
        self.ls = tk.Frame(self.mc, bg='#121212', width=120)
        self.ls.pack(side=tk.LEFT, fill=tk.Y)
        self.ls.pack_propagate(False)

        # Navigation (icon + label, neatly arranged at the top)
        sn = tk.Frame(self.ls, bg='#121212')
        sn.pack(fill=tk.BOTH, expand=True, padx=8, pady=(10, 4))

        nav_data = [
            (ICON["message"], "Chats", 'chats', True, IF),
            (ICON["phone"], "Calls", 'calls', False, IF),
            (ICON["settings"], "Settings", 'settings', False, IF),
        ]
        self.nav_btns = []
        for ic, txt, view, active, ifam in nav_data:
            b = RoundedButton(sn, text=txt, icon=ic, icon_font=(ifam, 14),
                              command=lambda v=view: self.switch_view(v),
                              font=("Segoe UI", 11, "bold" if active else "normal"),
                              parent_bg='#121212', width=100, height=36, radius=9,
                              align="left", pad_left=11, icon_gap=9,
                              active_bg='#25d366', active_fg='white',
                              inactive_bg='#121212', inactive_fg='#aebac1')
            b.set_active(active)
            b.pack(pady=2)
            self.nav_btns.append((b, view))

        # Footer - my profile photo + online users + add server
        sf = tk.Frame(self.ls, bg='#121212')
        sf.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 10))

        mef = tk.Frame(sf, bg='#121212')
        mef.pack(fill=tk.X, pady=(0, 6))
        self.me_av = tk.Canvas(mef, width=46, height=46, bg='#121212',
                               highlightthickness=0, bd=0, cursor="hand2")
        self.me_av.pack()
        self.me_lbl = tk.Label(mef, text=self.my_username[:12], bg='#121212',
                               fg='#aebac1', font=("Segoe UI", 8, "bold"))
        self.me_lbl.pack(pady=(3, 0))
        self._bind_click_recursive(self.me_av, lambda e: self.switch_view('settings'))
        self._render_my_avatar()

        of = tk.Frame(sf, bg='#121212')
        of.pack(fill=tk.X, pady=(0, 4))
        tk.Label(of, text="●", bg='#121212', fg='#25d366', font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.onl = tk.Label(of, text="Online: 0", bg='#121212', fg='#aebac1', font=("Segoe UI", 8))
        self.onl.pack(side=tk.LEFT, padx=(5, 0))

        self.cc = tk.Label(sf, text=f"Clients: 0 / 20", bg='#121212', fg='#667781', font=("Segoe UI", 8))
        self.cc.pack(pady=(0, 6))

        add_srv = RoundedButton(sf, text="New", icon=ICON["add"], icon_font=(IF, 12),
                                command=self.add_menu, font=("Segoe UI", 9, "bold"),
                                parent_bg='#121212', width=104, height=32, radius=8,
                                active_bg='#2c2c2c', active_fg='white')
        add_srv.set_active(True)
        add_srv.pack()

        # ===== PART 2: MIDDLE PANEL (Chats list) =====
        self.mp = tk.Frame(self.mc, bg='#1e1e1e')
        self.mp.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        mh = tk.Frame(self.mp, bg='#1e1e1e', height=52)
        mh.pack(fill=tk.X, padx=12, pady=8)
        mh.pack_propagate(False)
        self.mid_title = tk.Label(mh, text="Chats", bg='#1e1e1e', fg='#e9edef', font=("Segoe UI", 16, "bold"))
        self.mid_title.pack(side=tk.LEFT)

        # Search bar (rounded, original search icon)
        self.search_f = RoundedBox(mh, radius=16, bg='#2c2c2c', parent_bg='#1e1e1e')
        self.search_f.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=6)
        tk.Label(self.search_f, text=ICON["search"], bg='#2c2c2c', fg='#8696a0',
                 font=(IF, 13)).pack(side=tk.LEFT, padx=(10, 2))
        self.se = PlaceholderEntry(self.search_f, placeholder="Search",
                                   bg='#2c2c2c', font=("Segoe UI", 11),
                                   fg='white', insertbackground='#25d366')
        self.se.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 10))
        self.se.bind('<KeyRelease>', lambda e: self.filter_chats())

        # Filter chips (rounded)
        ff = tk.Frame(self.mp, bg='#1e1e1e')
        ff.pack(fill=tk.X, padx=12, pady=(0, 6))
        self.filter_frame = ff
        self.fb = {}
        for txt, val in [("All", "all"), ("Groups", "groups"), ("Single", "single")]:
            act = val == "all"
            b = RoundedButton(ff, text=txt, command=lambda v=val: self.set_filter(v),
                              font=("Segoe UI", 10, "bold" if act else "normal"),
                              parent_bg='#1e1e1e', width=66, height=30, radius=9,
                              active_bg='#25d366', active_fg='white',
                              inactive_bg='#2c2c2c', inactive_fg='#aebac1')
            b.set_active(act)
            b.pack(side=tk.LEFT, padx=3)
            self.fb[val] = b

        # Separate "Blocked" button (just below the search bar): opens the
        # dedicated blocked-clients view with the list + detail + unblock.
        self.block_btn = RoundedButton(ff, text="Blocked",
                                       command=self.show_blocked,
                                       font=("Segoe UI", 10, "bold"),
                                       parent_bg='#1e1e1e', width=78, height=30,
                                       radius=9, active_bg='#e53935',
                                       active_fg='white',
                                       inactive_bg='#2c2c2c',
                                       inactive_fg='#aebac1')
        self.block_btn.set_active(False)
        self.block_btn.pack(side=tk.RIGHT, padx=3)

        # Chat list scrollable (items stretch to full middle width)
        clf = tk.Frame(self.mp, bg='#1e1e1e')
        clf.pack(fill=tk.BOTH, expand=True)
        self.chat_list_frame = clf
        self.ccv = tk.Canvas(clf, bg='#1e1e1e', bd=0, highlightthickness=0)
        # slim rounded scrollbar on the right of the middle panel; it hides
        # itself completely while every chat already fits on screen
        self.csc = ModernScrollbar(clf, command=self.ccv.yview, width=12,
                                   parent_bg='#1e1e1e',
                                   thumb='#4a4a4a', thumb_hover='#5f6d75')
        self.cii = tk.Frame(self.ccv, bg='#1e1e1e')
        self.ccv_window = self.ccv.create_window((0, 0), window=self.cii, anchor="nw")
        self._autohide_scrollbar(self.ccv, self.csc)
        self.ccv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # keep inner frame width == visible canvas width (no horizontal overflow)
        self.ccv.bind("<Configure>", self._on_chat_canvas_configure)
        self.cii.bind("<Configure>", lambda e: self._queue_scrollregion(self.ccv))
        # mouse-wheel scrolling for the chat list
        self._bind_mousewheel(self.ccv)

        # Floating add button (crisp drawn '+' so pixels stay sharp, no overflow)
        def _plus(cv, bg):
            cx, cy = cv.w / 2, cv.h / 2
            arm, thick = 9, 3
            cv.create_line(cx - arm, cy, cx + arm, cy, fill='white',
                           width=thick, capstyle=tk.ROUND)
            cv.create_line(cx, cy - arm, cx, cy + arm, fill='white',
                           width=thick, capstyle=tk.ROUND)
        self.fab = RoundedButton(self.mp, command=self.add_menu, parent_bg='#1e1e1e',
                                 width=52, height=52, radius=26,
                                 active_bg='#25d366', active_fg='white',
                                 draw_extra=_plus)
        self.fab.set_active(True)
        self.fab.place(relx=1.0, rely=1.0, anchor="se", x=-16, y=-16)

        # ===== PART 3: RIGHT PANEL (Chat window) =====
        self.rp = tk.Frame(self.mc, bg='#121212', width=650)
        self.rp.pack(side=tk.RIGHT, fill=tk.Y)
        self.rp.pack_propagate(False)

        # Empty state
        self.re = tk.Frame(self.rp, bg='#121212')
        self.re.pack(fill=tk.BOTH, expand=True)
        tk.Label(self.re, text=ICON["message"], bg='#121212', fg='#2c2c2c',
                 font=(IF, 64)).pack(pady=(120, 14))
        tk.Label(self.re, text="Select a Chat", bg='#121212', fg='#e9edef', font=("Segoe UI", 20, "bold")).pack()
        tk.Label(self.re, text="Click on any contact to start messaging",
                 bg='#121212', fg='#8696a0', font=("Segoe UI", 12)).pack(pady=(6, 0))

        # Active chat (hidden by default)
        self.ra = tk.Frame(self.rp, bg='#121212')

        # Chat header
        ch = tk.Frame(self.ra, bg='#121212', height=80)
        ch.pack(fill=tk.X)
        ch.pack_propagate(False)
        self._chat_header = ch
        # pack the action buttons FIRST so they always get their space (even when
        # a group's member list makes the left side very wide) -> the "More"
        # button no longer disappears for large groups.
        hr = tk.Frame(ch, bg='#121212')
        hr.pack(side=tk.RIGHT, padx=12, pady=13)
        self.hbtns = {}
        for ic, tt in [(ICON["search"], "Search"), (ICON["video"], "Video Call"),
                       (ICON["phone"], "Voice Call"), (ICON["more"], "More")]:
            hbtn = RoundedButton(hr, icon=ic, icon_font=(IF, 15),
                                 command=lambda t=tt: self.haction(t),
                                 parent_bg='#121212', width=34, height=34, radius=17,
                                 active_bg='#1e1e1e', active_fg='#aebac1')
            hbtn.set_active(True)
            hbtn.pack(side=tk.LEFT, padx=3)
            self.hbtns[tt] = hbtn

        hl = tk.Frame(ch, bg='#121212')
        hl.pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=10)
        self.ha = tk.Canvas(hl, width=40, height=40, bg='#121212', highlightthickness=0, bd=0)
        self.ha.pack(side=tk.LEFT, padx=(0, 10))
        self._round_rect(self.ha, 0, 0, 40, 40, 12, self.current_chat_color or '#2c2c2c')
        self.ha.create_text(20, 20, text="U", fill="white", font=("Segoe UI", 15, "bold"))
        hi = tk.Frame(hl, bg='#121212')
        hi.pack(side=tk.LEFT, fill=tk.Y)
        self.cn = tk.Label(hi, text="Contact Name", bg='#121212', fg="#e9edef", font=("Segoe UI", 15, "bold"), anchor="w")
        self.cn.pack(anchor="w")
        sf3 = tk.Frame(hi, bg='#121212')
        sf3.pack(anchor="w", pady=(1, 0))
        self.sd = tk.Label(sf3, text="●", bg='#121212', fg=self.theme.get('status_online'), font=("Segoe UI", 9))
        self.sd.pack(side=tk.LEFT)
        self.st = tk.Label(sf3, text="active", bg='#121212', fg=self.theme.get('status_online'),
                           font=("Segoe UI", 9, "bold"))
        self.st.pack(side=tk.LEFT, padx=(5, 0))

        # Messages area
        ma = tk.Frame(self.ra, bg='#121212')
        ma.pack(fill=tk.BOTH, expand=True)
        self.messages_area = ma
        self.mcv = tk.Canvas(ma, bg='#121212', bd=0, highlightthickness=0)
        self.msc = ModernScrollbar(ma, command=self.mcv.yview, width=12,
                                   parent_bg='#121212',
                                   thumb='#4a4a4a', thumb_hover='#5f6d75')
        self.mi = tk.Frame(self.mcv, bg='#121212')
        self.mcv_window = self.mcv.create_window((0, 0), window=self.mi, anchor="nw")
        self._autohide_scrollbar(self.mcv, self.msc)
        self.mcv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.mi.bind("<Configure>", lambda e: self._queue_scrollregion(self.mcv))
        # messages stretch to full width of the chat window (no overflow)
        self.mcv.bind("<Configure>", lambda e: self.mcv.itemconfigure(self.mcv_window, width=e.width))
        # mouse-wheel scrolling for the messages panel ONLY (never the chat list)
        self._bind_mousewheel(self.mcv, self.mcv)

        # Input area (rounded input field) — normal composer + voice-recorder row
        ia = tk.Frame(self.ra, bg='#1e1e1e', height=60)
        ia.pack(fill=tk.X, side=tk.BOTTOM)
        ia.pack_propagate(False)
        self.input_area = ia

        self.input_row = tk.Frame(ia, bg='#1e1e1e')
        self.input_row.pack(fill=tk.BOTH, expand=True)

        at = RoundedButton(self.input_row, icon=ICON["attach"], icon_font=(IF, 15),
                           command=self.attach_menu, parent_bg='#1e1e1e',
                           width=36, height=36, radius=18,
                           active_bg='#1e1e1e', active_fg='#8696a0')
        at.set_active(True)
        at.pack(side=tk.LEFT, padx=(8, 0), pady=12)
        em = RoundedButton(self.input_row, icon=ICON["emoji"], icon_font=(IF, 15),
                           command=self.emoji_menu, parent_bg='#1e1e1e',
                           width=36, height=36, radius=18,
                           active_bg='#1e1e1e', active_fg='#8696a0')
        em.set_active(True)
        em.pack(side=tk.LEFT, padx=2, pady=12)

        self.input_box = RoundedBox(self.input_row, radius=16, bg='#2c2c2c', parent_bg='#1e1e1e')
        self.input_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=10)
        # single-line rounded field, styled exactly like the search input
        self.mi_t = PlaceholderEntry(self.input_box, placeholder="Message",
                                     bg='#2c2c2c', font=("Segoe UI", 12),
                                     fg='white', insertbackground='#25d366')
        self.mi_t.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(14, 14))
        self.mi_t.bind('<KeyRelease>', self.on_tc)
        self.mi_t.bind('<Return>', self.on_ep)

        self.voice_btn = RoundedButton(self.input_row, icon=ICON["mic"], icon_font=(IF, 15),
                                       command=self.start_recording, parent_bg='#1e1e1e',
                                       width=36, height=36, radius=18,
                                       active_bg='#1e1e1e', active_fg='#25d366')
        self.voice_btn.set_active(True)
        self.voice_btn.pack(side=tk.LEFT, padx=2, pady=12)
        self.sb = RoundedButton(self.input_row, icon=ICON["send"], icon_font=(IF, 16),
                                command=self.send_msg, parent_bg='#1e1e1e',
                                width=38, height=36, radius=18,
                                active_bg='#25d366', active_fg='white')
        self.sb.set_enabled(False)
        self.sb.pack(side=tk.LEFT, padx=(2, 8), pady=12)

        # WhatsApp-style voice-recording row (shown in place of the composer)
        self.rec_row = self._build_recorder_row(ia)

        # File preview page: opens INSIDE the right panel (never a new window)
        # when a file is picked.  Enter or the Send button sends it.
        self.preview_panel = self._build_file_preview(self.ra)

        # Settings panel (inline, hidden by default)
        self.settings_panel = tk.Frame(self.mp, bg='#1e1e1e')

    # ============================================================
    # ICON / LOGO HELPERS
    # ============================================================
    def _pick_icon_font(self):
        """Pick an installed monochrome icon font (pixel-crisp on Windows)."""
        try:
            fams = set(tkfont.families(self.root))
        except Exception:
            fams = set()
        for fam in ("Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol"):
            if fam in fams:
                return fam
        return "Segoe UI Symbol"

    def _draw_whatsapp_logo(self, cv, size):
        """WhatsApp-style green bubble with a white phone handset (no emoji)."""
        cv.delete("all")
        cv.create_oval(0, 0, size, size, fill="#25d366", outline="#25d366")
        cv.create_text(size / 2, size / 2 + 1, text=ICON["phone"], fill="white",
                       font=(self.icon_family, int(size * 0.5), "bold"))

    # ============================================================
    # THEME (dark <-> light, applied to the whole app)
    # ============================================================
    def apply_theme(self, target, save=True):
        """Re-skin the entire app (Chrome Widgets + canvases) for `target`."""
        target = 'Light' if str(target).lower().startswith('light') else 'Dark'
        if getattr(self, 'theme_name', 'Dark') == target and getattr(self, '_theme_ready', False):
            return
        bgmap, fgmap = self.theme.maps_for(target)
        self.theme_name = target
        self.theme.set_theme(target)
        # live notifications are drawn with fixed colours -> drop them
        try:
            for it in list(self.notifier.items):
                self.notifier.dismiss(it)
        except Exception:
            pass
        self._retheme_tree(self.root, bgmap, fgmap)
        self._restyle_ttk(target)
        self._theme_ready = True
        if save:
            try:
                self.root.update_idletasks()
            except Exception:
                pass

    def _retheme_tree(self, widget, bgmap, fgmap):
        """Recursively translate every colour option / canvas item."""
        # special widgets keep their own colour bookkeeping
        if isinstance(widget, RoundedButton):
            widget.theme_remap(bgmap, fgmap)
        elif isinstance(widget, RoundedBox):
            widget.theme_remap(bgmap, fgmap)
        elif isinstance(widget, ModernScrollbar):
            widget.theme_remap(bgmap, fgmap)
        else:
            self._retheme_widget(widget, bgmap, fgmap)
            if isinstance(widget, tk.Canvas):
                self._retheme_canvas_items(widget, bgmap, fgmap)
        for child in widget.winfo_children():
            self._retheme_tree(child, bgmap, fgmap)

    def _retheme_widget(self, w, bgmap, fgmap):
        plan = {}
        for opt in _BG_OPTIONS:
            try:
                cur = w.cget(opt)
            except Exception:
                continue
            if isinstance(cur, str) and cur.lower() in bgmap:
                plan[opt] = bgmap[cur.lower()]
        for opt in _FG_OPTIONS:
            try:
                cur = w.cget(opt)
            except Exception:
                continue
            if isinstance(cur, str) and cur.lower() in fgmap:
                plan[opt] = fgmap[cur.lower()]
        if plan:
            try:
                w.configure(**plan)
            except Exception:
                for opt, val in plan.items():
                    try:
                        w.configure(**{opt: val})
                    except Exception:
                        pass
        # hard-coded "white" text would vanish on a light background
        self._fix_contrast(w)

    @staticmethod
    def _lum(w, color):
        """Perceived brightness (0..1) of any Tk colour spec, or None."""
        try:
            r, g, b = w.winfo_rgb(color)
        except Exception:
            return None
        return (0.299 * r + 0.587 * g + 0.114 * b) / 65535.0

    def _fix_contrast(self, w):
        """Flip (and restore) white foregrounds so text stays readable."""
        try:
            fg = w.cget('fg')
        except Exception:
            return
        if not isinstance(fg, str):
            return
        if getattr(self, 'theme_name', 'Dark') == 'Light':
            lf = self._lum(w, fg)
            if lf is None or lf < 0.8:
                return
            try:
                bg = w.cget('bg')
            except Exception:
                return
            lb = self._lum(w, bg)
            if lb is None or lb < 0.62:
                return
            if not hasattr(w, '_dark_fg'):
                w._dark_fg = fg
            try:
                w.configure(fg='#111b21')
            except Exception:
                pass
        else:
            prev = getattr(w, '_dark_fg', None)
            if prev is not None:
                try:
                    w.configure(fg=prev)
                    del w._dark_fg
                except Exception:
                    pass

    def _retheme_canvas_items(self, cv, bgmap, fgmap):
        for it in cv.find_all():
            try:
                fill = cv.itemcget(it, 'fill')
            except Exception:
                continue
            if not fill:
                continue
            key = fill.lower()
            m = fgmap if cv.type(it) == 'text' else bgmap
            if key in m:
                try:
                    cv.itemconfigure(it, fill=m[key])
                except Exception:
                    pass

    def _theme_subtree(self, widget):
        """Re-theme freshly created widgets (called right after building them)."""
        if getattr(self, 'theme_name', 'Dark') == 'Dark':
            return
        bgmap, fgmap = self.theme.maps_for('Light')
        self._retheme_tree(widget, bgmap, fgmap)

    def _tbg(self, color):
        """Translate a dark-mode fill literal to the active theme."""
        if getattr(self, 'theme_name', 'Dark') == 'Light':
            bgmap, _ = self.theme.maps_for('Light')
            return bgmap.get(color, color)
        return color

    def _restyle_ttk(self, target):
        light = (target == 'Light')
        try:
            st = ttk.Style(self.root)
            st.configure('Dark.TCombobox',
                         fieldbackground='#ffffff' if light else '#1e1e1e',
                         background='#f0f2f5' if light else '#2c2c2c',
                         foreground='#111b21' if light else '#e9edef',
                         arrowcolor='#00a884' if light else '#25d366',
                         bordercolor='#d1d7db' if light else '#3c3c3c',
                         lightcolor='#f0f2f5' if light else '#2c2c2c',
                         darkcolor='#f0f2f5' if light else '#2c2c2c',
                         selectbackground='#ffffff' if light else '#1e1e1e',
                         selectforeground='#111b21' if light else '#e9edef')
            st.map('Dark.TCombobox',
                   fieldbackground=[('readonly', '#ffffff' if light else '#1e1e1e')],
                   foreground=[('readonly', '#111b21' if light else '#e9edef')],
                   background=[('readonly', '#f0f2f5' if light else '#2c2c2c')])
            self.root.option_add('*TCombobox*Listbox.background',
                                 '#ffffff' if light else '#1e1e1e')
            self.root.option_add('*TCombobox*Listbox.foreground',
                                 '#111b21' if light else '#e9edef')
            self.root.option_add('*TCombobox*Listbox.selectBackground',
                                 '#00a884' if light else '#25d366')
            self.root.option_add('*TCombobox*Listbox.selectForeground',
                                 '#ffffff' if light else '#0b1a0e')
        except Exception:
            pass

    # ============================================================
    # VIEW SWITCHING (Single page - no new windows)
    # ============================================================
    def switch_view(self, view):
        self.current_view = view
        for b, v in self.nav_btns:
            b.set_active(v == view)
        try:
            # leaving the Blocked view also un-highlights its button
            self.block_btn.set_active(False)
        except Exception:
            pass

        # Hide settings panel if showing chats
        self.settings_panel.pack_forget()

        if view == 'settings':
            self.mid_title.configure(text="Settings")
            self.search_f.pack_forget()
            self.filter_frame.pack_forget()
            self.fab.place_forget()
            self.show_settings_inline()
        elif view == 'calls':
            self.mid_title.configure(text="Calls")
            self.search_f.pack_forget()
            self.filter_frame.pack_forget()
            self.fab.place_forget()
            self.show_calls_inline()
        else:
            self.mid_title.configure(text="Chats")
            self.search_f.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=6)
            self.filter_frame.pack(fill=tk.X, padx=12, pady=(0, 6), before=self.chat_list_frame)
            self.fab.place(relx=1.0, rely=1.0, anchor="se", x=-16, y=-16)
            self.render_chats_from_data()
        self._save_ui_state()

    # ============================================================
    # PROFILE PICTURES (dp)
    # ============================================================
    @staticmethod
    def _pic_hash(b64):
        if not b64:
            return ""
        try:
            return hashlib.md5(b64.encode("utf-8", "ignore")).hexdigest()[:12]
        except Exception:
            return ""

    def _avatar_photo(self, b64, size):
        """Return a circular PhotoImage for `b64` (cached), or None."""
        if not b64 or not PIL_OK:
            return None
        key = (self._pic_hash(b64), int(size))
        if key in self._img_cache:
            return self._img_cache[key]
        ph = None
        try:
            raw = base64.b64decode(b64)
            im = Image.open(io.BytesIO(raw)).convert("RGBA")
            im = im.resize((size, size), Image.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
            im.putalpha(mask)
            ph = ImageTk.PhotoImage(im)
        except Exception:
            ph = None
        self._img_cache[key] = ph
        return ph

    def _draw_avatar(self, cv, size, radius, name, color, pic=""):
        """Draw either the circular profile photo or coloured initials."""
        cv.delete("all")
        ph = self._avatar_photo(pic, size)
        if ph is not None:
            cv.create_image(size // 2, size // 2, image=ph)
            cv._ph = ph                       # keep a hard reference
            return
        self._round_rect(cv, 0, 0, size, size, radius, color or '#2c2c2c')
        txt = self._initials(name) if name else "U"
        cv.create_text(size // 2, size // 2, text=txt, fill="white",
                       font=("Segoe UI", max(9, int(size * 0.36)), "bold"))

    @staticmethod
    def _square_photo_bytes(path, size=192):
        """Read any image file and return a square PNG (bytes) for transport."""
        if not PIL_OK:
            return None
        im = Image.open(path).convert("RGB")
        w, h = im.size
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2,
                      (w - s) // 2 + s, (h - s) // 2 + s))
        im = im.resize((size, size), Image.LANCZOS)
        bio = io.BytesIO()
        im.save(bio, "PNG")
        return bio.getvalue()

    def _my_avatar_color(self):
        try:
            return self.pc.get() or self.my_color
        except Exception:
            return self.my_color

    def _render_my_avatar(self):
        cv = getattr(self, 'me_av', None)
        if cv is None:
            return
        # the sidebar always shows the *applied* colour + photo
        self._draw_avatar(cv, 46, 14, self.my_username,
                          self.my_color or '#25d366', self.my_pic)

    @staticmethod
    def _round_rect(cv, x1, y1, x2, y2, r, fill, outline="", tags=()):
        _rrect(cv, x1, y1, x2, y2, r, fill, outline, tags)

    def _autohide_scrollbar(self, canvas, scrollbar):
        """Attach an auto-hiding vertical scrollbar to a canvas.

        `ModernScrollbar` keeps track of its own visibility (and tolerates a
        fraction of a pixel, so a panel that already fits stays clean).  A
        plain `tk.Scrollbar` still gets the classic pack / unpack treatment,
        so any other canvas in the app keeps working.
        """
        if isinstance(scrollbar, ModernScrollbar):
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.set(0.0, 1.0)                  # start hidden
            return

        def _set(lo, hi):
            if float(lo) <= 0.0 and float(hi) >= 1.0:
                scrollbar.pack_forget()
            elif not scrollbar.winfo_ismapped():
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            scrollbar.set(lo, hi)
        canvas.configure(yscrollcommand=_set)

    def _on_chat_canvas_configure(self, e):
        # keep inner frame width equal to the visible canvas width (no overflow)
        try:
            self.ccv.itemconfigure(self.ccv_window, width=e.width)
        except Exception:
            pass
        self._queue_scrollregion(self.ccv)

    def _queue_scrollregion(self, canvas):
        """Refresh a canvas' scrollregion one idle cycle later.

        `bbox('all')` can lag behind a resize, so setting the region directly
        from a `<Configure>` handler leaves a stale (too tall) region - which
        is exactly what used to keep the scrollbar on screen after every chat
        had already been removed again.
        """
        jobs = getattr(self, '_sregion_jobs', None)
        if jobs is None:
            jobs = self._sregion_jobs = {}
        if jobs.get(canvas) is not None:
            return

        def _do():
            jobs[canvas] = None
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass
        try:
            jobs[canvas] = self.root.after_idle(_do)
        except Exception:
            _do()

    def _wheel_handler(self, canvas):
        """Return a wheel handler that scrolls ONLY the given canvas.

        If that canvas has nothing to scroll (content fits inside the view)
        the event is swallowed so no other panel scrolls either.
        """
        def _h(e):
            try:
                lo, hi = canvas.yview()
            except Exception:
                return "break"
            if (hi - lo) >= 1.0:          # everything visible -> not scrollable
                return "break"
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            return "break"
        return _h

    def _bind_mousewheel(self, widget, canvas=None):
        canvas = canvas if canvas is not None else self.ccv
        widget.bind("<MouseWheel>", self._wheel_handler(canvas), add="+")
        widget.bind("<Button-4>", lambda e, c=canvas: c.yview_scroll(-1, "units"), add="+")
        widget.bind("<Button-5>", lambda e, c=canvas: c.yview_scroll(1, "units"), add="+")

    def _bind_mousewheel_recursive(self, widget, canvas=None):
        self._bind_mousewheel(widget, canvas)
        for c in widget.winfo_children():
            self._bind_mousewheel_recursive(c, canvas)

    def _bind_click_recursive(self, widget, handler):
        """Bind a click handler to a widget AND all of its descendants.

        In Tkinter a click does not bubble up to the parent, so without this
        clicking on the contact's name/message text would do nothing.
        """
        widget.bind("<Button-1>", handler)
        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass
        for c in widget.winfo_children():
            self._bind_click_recursive(c, handler)

    def _paint_row(self, widget, color):
        """Recursively set the background colour of a row and its children."""
        try:
            widget.configure(bg=color)
        except Exception:
            pass
        for c in widget.winfo_children():
            self._paint_row(c, color)

    def _bind_hover_recursive(self, widget, row, base_color, hover_color):
        """Smooth hover highlight: any descendant that gets <Enter> lights the
        whole row up, and it only reverts when the pointer truly leaves it.

        Colours are translated through the active theme so a hovered row never
        flashes the dark-mode shade while Light mode is on.
        """
        def _enter(_e=None):
            self._paint_row(row, self._tbg(hover_color))

        def _leave(e=None):
            # keep it lit while the pointer is still inside the row
            try:
                under = row.winfo_containing(e.x_root, e.y_root)
            except Exception:
                under = None
            if under is not None and str(under).startswith(str(row)):
                return
            self._paint_row(row, self._tbg(base_color))

        widget.bind("<Enter>", _enter, add="+")
        widget.bind("<Leave>", _leave, add="+")
        for c in widget.winfo_children():
            self._bind_hover_recursive(c, row, base_color, hover_color)

    def render_chats_from_data(self):
        self.refresh_middle_list()

    def refresh_middle_list(self):
        """Rebuild the middle chat list from the added contacts + active filter."""
        if getattr(self, 'current_view', 'chats') != 'chats':
            return
        peers = list(getattr(self, '_peers', []))
        try:
            q = self.se.get().lower()
        except Exception:
            q = ''
        fv = 'all'
        for v, b in getattr(self, 'fb', {}).items():
            if getattr(b, 'is_active', False):
                fv = v
                break
        out = []
        for u in peers:
            if u.get('hidden'):
                continue
            # blocked clients are shown in their own "Blocked" view, not here
            if u.get('type') != 'group' and u.get('name') in self.blocked:
                continue
            if fv == 'groups' and u.get('type') != 'group':
                continue
            if fv == 'single' and u.get('type') != 'single':
                continue
            if q and q not in u.get('name', '').lower():
                continue
            out.append(u)
        # pinned chats float on top (most recently pinned first); the rest are
        # ordered by newest activity
        def _order(u):
            if u.get('pinned'):
                return (0, -float(u.get('pin_ts') or 0))
            return (1, -float(u.get('_act') or 0))
        out.sort(key=_order)
        self.render_chats(out)
        if not out:
            visible = [u for u in peers if not u.get('hidden')]
            if not visible:
                msg, sub = "No chats yet", "Tap the + button to add a client by IP or create a group"
            else:
                msg, sub = "Client not found", "No client matches your search"
            tk.Label(self.cii, text=msg, bg='#1e1e1e', fg='#8696a0',
                     font=("Segoe UI", 12, "bold")).pack(pady=(40, 4))
            tk.Label(self.cii, text=sub, bg='#1e1e1e', fg='#6b7780',
                     font=("Segoe UI", 10)).pack()
            self._theme_subtree(self.cii)
        self._queue_scrollregion(self.ccv)

    def render_chats(self, users):
        self._last_users = users
        # never overwrite the Settings / Calls panel with the chat list
        if getattr(self, 'current_view', 'chats') != 'chats':
            return
        self._chat_rows = {}
        self._chat_row_widgets = {}
        for w in self.cii.winfo_children():
            w.destroy()
        for u in users:
            self.chat_item(u)
        self._bind_mousewheel_recursive(self.cii, self.ccv)
        self._theme_subtree(self.cii)
        self._queue_scrollregion(self.ccv)

    def chat_item(self, u):
        fr = tk.Frame(self.cii, bg='#1e1e1e', cursor="hand2")
        fr.pack(fill=tk.X, padx=4, pady=1)

        def cl(e): self.open_chat(u)

        # Avatar (rounded / circular photo)
        av = tk.Canvas(fr, width=44, height=44, bg='#1e1e1e',
                       highlightthickness=0, bd=0, cursor="hand2")
        av.pack(side=tk.LEFT, padx=(8, 10), pady=6)
        self._draw_avatar(av, 44, 14, u.get('name'), u.get('color', '#2c2c2c'),
                          u.get('pic', ''))
        # online/offline dot, updated live (never needs a re-render)
        self._draw_presence_dot(av, u.get('status', 'active'),
                                u.get('type', 'single'))

        # Info
        inf = tk.Frame(fr, bg='#1e1e1e')
        inf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        tk.Label(inf, text=u['name'], bg='#1e1e1e', fg='#e9edef', font=("Segoe UI", 13, "bold"), anchor="w").pack(fill=tk.X)

        # Meta row
        meta = tk.Frame(inf, bg='#1e1e1e')
        meta.pack(fill=tk.X)
        last_lbl = tk.Label(meta, text=u.get('lastMsg', ''), bg='#1e1e1e', fg='#8696a0', font=("Segoe UI", 11), anchor="w")
        last_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        time_lbl = tk.Label(meta, text=self._fmt_time(u.get('time', '')), bg='#1e1e1e', fg='#8696a0', font=("Segoe UI", 9), anchor="e")
        time_lbl.pack(side=tk.RIGHT)
        # pinned chats show the original push-pin icon on the right, next to the time
        if u.get('pinned'):
            pin_lbl = tk.Label(meta, text=ICON['pin'], bg='#1e1e1e',
                               fg='#8696a0', font=(self.icon_family, 11))
            pin_lbl.pack(side=tk.RIGHT, padx=(0, 6))
        if not hasattr(self, '_chat_rows'):
            self._chat_rows = {}
        self._chat_rows[u['id']] = (last_lbl, time_lbl)
        # remember the row's widgets so live updates can touch just this row
        if not hasattr(self, '_chat_row_widgets'):
            self._chat_row_widgets = {}
        self._chat_row_widgets[u['id']] = {
            'frame': fr, 'avatar': av, 'name': u.get('name', ''),
            'color': u.get('color', '#2c2c2c'), 'pic': u.get('pic', ''),
            'type': u.get('type', 'single'), 'badge': None}

        # Unread badge (rounded) - created/updated in place
        self._set_row_unread(u['id'], u.get('unread', 0))

        # Make the WHOLE row clickable (avatar, name, message, time, badge)
        self._bind_click_recursive(fr, cl)
        # right-click -> Pin / Mute / Block / Delete context menu
        self._bind_right_recursive(fr, lambda e, u=u: self._chat_context_menu(u, e))

        # Active highlight + hover animation (shows which client the cursor is on)
        is_active = (self.current_chat_id == u['id'])
        base = '#2c2c2c' if is_active else '#1e1e1e'
        hover = '#2c2c2c'
        if is_active:
            self._paint_row(fr, base)
        self._bind_hover_recursive(fr, fr, base, hover)

    # ---------- right-click context menu on a chat row ----------
    def _bind_right_recursive(self, widget, handler):
        """Bind <Button-3> to a row and every child (Tk doesn't bubble it)."""
        widget.bind("<Button-3>", handler)
        for c in widget.winfo_children():
            self._bind_right_recursive(c, handler)

    def _chat_context_menu(self, u, event=None):
        """Pin / Mute / Block / Delete menu for one chat row."""
        menu = tk.Menu(self.root, tearoff=0)
        name = u.get('name') or ''
        is_group = (u.get('type') == 'group')
        pinned = bool(u.get('pinned'))
        muted = u.get('id') in getattr(self, 'muted_chats', set())
        blocked = name in getattr(self, 'blocked', set())

        menu.add_command(label="Unpin" if pinned else "Pin to top",
                         command=lambda: self.toggle_chat_pin(u))
        menu.add_command(label="Unmute notifications" if muted
                         else "Mute notifications",
                         command=lambda: self.toggle_mute_chat_by_id(u.get('id')))
        menu.add_separator()
        if is_group:
            menu.add_command(label="Group info",
                             command=lambda: self.open_group_info(u))
            menu.add_separator()
        else:
            menu.add_command(label="Unblock client" if blocked else "Block client",
                             command=lambda: self.toggle_block(u))
            menu.add_separator()
        menu.add_command(label="Mark as read",
                         command=lambda: self.mark_chat_read(u))
        menu.add_separator()
        # the middle panel removes the CLIENT (not the conversation): label it
        # clearly so it is never confused with "clear chat" inside a conversation
        menu.add_command(label="Delete client",
                         command=lambda: self._menu_do(
                             lambda: self.delete_client(u)))
        try:
            menu.tk_popup(event.x_root if event else self.root.winfo_pointerx(),
                          event.y_root if event else self.root.winfo_pointery())
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def toggle_chat_pin(self, u):
        will_pin = not bool(u.get('pinned'))
        if will_pin:
            # at most 3 chats may be pinned
            pinned_now = [p for p in getattr(self, '_peers', []) if p.get('pinned')]
            if len(pinned_now) >= 3:
                self.show_toast("Sirf 3 chats pin ho sakti hain")
                self.notify("Pin limit reached",
                            "Aap sirf 3 chats pin kar sakte hain \u2014 "
                            "pehle koi chat unpin karein.", kind='warn')
                return
            u['pin_ts'] = max(
                datetime.now().timestamp(),
                max([float(p.get('pin_ts') or 0) for p in self._peers] + [0.0]) + 0.001)
        else:
            u['pin_ts'] = 0
        u['pinned'] = will_pin
        try:
            sio.emit('pin_chat', {'me': self.my_username, 'peer': u.get('name'),
                                  'pinned': will_pin,
                                  'pin_ts': float(u.get('pin_ts') or 0)})
        except Exception:
            pass
        self.refresh_middle_list()
        self.show_toast(("Pinned " if will_pin else "Unpinned ") + (u.get('name') or ''))

    def mark_chat_read(self, u):
        u['unread'] = 0
        self._set_row_unread(u.get('id'), 0)
        if not u.get('type') == 'group':
            try:
                sio.emit('mark_read', {'me': self.my_username, 'peer': u.get('name')})
            except Exception:
                pass
        self._save_ui_state()

    def delete_chat(self, u):
        """Remove one chat (contact) from the middle list."""
        try:
            self._peers = [p for p in getattr(self, '_peers', [])
                           if p.get('id') != u.get('id')]
        except Exception:
            pass
        self.refresh_middle_list()
        self._save_ui_state()
        self.show_toast("Chat deleted")

    def delete_client(self, u):
        """Remove a CLIENT from the middle chat list (WhatsApp 'Delete chat')."""
        name = u.get('name') or 'this client'
        try:
            ok = messagebox.askyesno(
                "Delete client",
                "Remove \u201c%s\u201d from your chats?\n\n"
                "The client is removed from the middle list. "
                "The conversation can come back if they message you again."
                % name, parent=self.root)
        except Exception:
            ok = True
        if not ok:
            return
        # if this client was the open conversation, drop back to the empty pane
        try:
            if self.current_chat_id == u.get('id'):
                self._close_open_chat()
                self._cancel_reply()
                self._discard_file_preview()
        except Exception:
            pass
        self.delete_chat(u)
        self.show_toast("Client removed from chats")

    def toggle_mute_chat_by_id(self, chat_id):
        if chat_id in self.muted_chats:
            self.muted_chats.discard(chat_id)
            self.show_toast("Notifications unmuted")
        else:
            self.muted_chats.add(chat_id)
            self.show_toast("Notifications muted")

    def _peer_pic(self, name):
        for p in getattr(self, '_peers', []):
            if p.get('name') == name:
                return p.get('pic', '')
        return ''

    # ---------- live, in-place row updates (no full re-render) ----------
    def _draw_presence_dot(self, av, status, ctype='single'):
        """Small online/offline dot at the bottom-right of a list avatar."""
        try:
            av.delete('presence')
            if ctype == 'group':
                return
            online = (status or '').strip().lower() in ('active', 'online')
            col = '#25d366' if online else '#8696a0'
            av.create_oval(30, 30, 43, 43, fill=col,
                           outline=self._tbg('#1e1e1e'), width=2, tags='presence')
            av.tag_raise('presence')
        except Exception:
            pass

    def _set_row_presence(self, chat_id, status):
        w = (getattr(self, '_chat_row_widgets', {}) or {}).get(chat_id)
        if not w:
            return
        self._draw_presence_dot(w.get('avatar'), status, w.get('type', 'single'))

    def _set_row_unread(self, chat_id, n):
        w = (getattr(self, '_chat_row_widgets', {}) or {}).get(chat_id)
        if not w:
            return
        fr = w.get('frame')
        badge = w.get('badge')
        try:
            if n and int(n) > 0:
                if badge is None or not badge.winfo_exists():
                    badge = tk.Canvas(fr, width=22, height=22, bg='#1e1e1e',
                                      highlightthickness=0, bd=0)
                    badge.pack(side=tk.RIGHT, padx=10, pady=9)
                    w['badge'] = badge
                badge.delete('all')
                self._round_rect(badge, 1, 1, 21, 21, 11, '#25d366')
                badge.create_text(11, 11, text=str(int(n)), fill='white',
                                  font=("Segoe UI", 9, "bold"))
            elif badge is not None:
                try:
                    badge.destroy()
                except Exception:
                    pass
                w['badge'] = None
        except Exception:
            pass

    def _set_row_avatar(self, chat_id, name, color, pic, status='active'):
        w = (getattr(self, '_chat_row_widgets', {}) or {}).get(chat_id)
        if not w:
            return
        try:
            self._draw_avatar(w.get('avatar'), 44, 14, name, color, pic)
            w['pic'] = pic
            w['color'] = color
            self._draw_presence_dot(w.get('avatar'), status, w.get('type', 'single'))
        except Exception:
            pass

    def _set_active_row(self, chat_id):
        """Move the 'selected chat' highlight to another row, in place."""
        for cid, w in (getattr(self, '_chat_row_widgets', {}) or {}).items():
            try:
                self._paint_row(w.get('frame'),
                                self._tbg('#2c2c2c' if cid == chat_id else '#1e1e1e'))
            except Exception:
                pass

    def _update_row_inplace(self, u):
        """Refresh one chat row (preview, time, unread, presence) in place."""
        cid = u.get('id')
        rows = getattr(self, '_chat_rows', None)
        t = rows.get(cid) if rows else None
        if t:
            try:
                t[0].configure(text=u.get('lastMsg', ''))
                t[1].configure(text=self._fmt_time(u.get('time', '')))
            except Exception:
                pass
        self._set_row_presence(cid, u.get('status', 'active'))
        self._set_row_unread(cid, u.get('unread', 0))

    def _apply_header_status(self, status):
        """Update the open-chat header dot/text immediately (no re-render)."""
        try:
            if getattr(self, 'current_chat_type', 'single') == 'group':
                return
            if (status or 'active').strip().lower() in ('active', 'online'):
                self.sd.configure(fg='#25d366')
                self.st.configure(text='active', fg='#25d366')
            else:
                self.sd.configure(fg='#7f8c8d')
                self.st.configure(text='offline', fg='#7f8c8d')
        except Exception:
            pass

    def _mark_peer_status(self, name, status, sid=None):
        """Set a contact's presence and reflect it live (list row + header)."""
        if not name:
            return
        for u in getattr(self, '_peers', []):
            if u.get('name') == name and not u.get('is_server'):
                if sid:
                    u['sid'] = sid
                changed = (u.get('status') != status)
                u['status'] = status
                if changed:
                    self._update_row_inplace(u)
                if self.current_chat_name == name:
                    self.current_status = status
                    self._apply_header_status(status)
                break

    def toggle_mute_chat(self):
        if self.current_chat_id is None:
            return
        if self.current_chat_id in self.muted_chats:
            self.muted_chats.discard(self.current_chat_id)
            self.show_toast("Notifications unmuted for this chat")
        else:
            self.muted_chats.add(self.current_chat_id)
            self.show_toast("Notifications muted for this chat")

    def _update_chat_preview(self, chat_id, last_msg, time_str):
        rows = getattr(self, '_chat_rows', None)
        if not rows:
            return
        row = rows.get(chat_id)
        if row:
            try:
                row[0].configure(text=last_msg)
                row[1].configure(text=self._fmt_time(time_str))
            except Exception:
                pass

    def _touch_chat(self, chat_id):
        """Mark a chat as the most recent one and re-order the list.

        Pinned chats still float above everything (see refresh_middle_list).
        """
        for u in getattr(self, '_peers', []):
            if u.get('id') == chat_id:
                u['_act'] = datetime.now().timestamp()
                break
        try:
            self.refresh_middle_list()
        except Exception:
            pass

    # ============================================================
    # FILTER & SEARCH
    # ============================================================
    def filter_chats(self):
        self.refresh_middle_list()

    def set_filter(self, v):
        # picking a chat filter also leaves the Blocked view
        if getattr(self, 'current_view', 'chats') != 'chats':
            self.switch_view('chats')
        for val, b in self.fb.items():
            b.set_active(val == v)
        self.filter_chats()

    @staticmethod
    def _initials(name):
        parts = [p for p in (name or "").split() if p]
        if not parts:
            return "U"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    def _close_open_chat(self):
        self.current_chat_id = None
        self.current_chat_name = ''
        self.current_chat_gid = None
        self.current_chat_sid = None
        self._current_msgs = []
        try:
            self.ra.pack_forget()
            self.re.pack(fill=tk.BOTH, expand=True)
        except Exception:
            pass

    # ---- inputs are only "active" while they are actually focused ----
    @staticmethod
    def _widget_inside(parent, w):
        try:
            while w is not None:
                if w is parent:
                    return True
                w = w.master
        except Exception:
            pass
        return False

    def _install_click_outside(self):
        """Clicking anywhere outside Search / Message makes them inactive.

        Tk frames and canvases never take the keyboard focus, so without this
        the caret would stay inside the input (and the placeholder stay hidden)
        even after clicking somewhere completely different.
        """
        try:
            self.root.bind_all('<Button-1>', self._click_outside, add='+')
        except Exception:
            pass

    def _click_outside(self, event):
        try:
            w = getattr(event, 'widget', None)
            focused = self.root.focus_get()
        except Exception:
            return
        for ent, box in ((getattr(self, 'mi_t', None), getattr(self, 'input_box', None)),
                         (getattr(self, 'se', None), getattr(self, 'search_f', None))):
            if ent is None or box is None:
                continue
            if self._widget_inside(box, w):
                # clicking the field or its padding simply focuses it
                if focused is not ent:
                    try:
                        ent.focus_set()
                    except Exception:
                        pass
                continue
            if focused is ent:
                try:
                    self.root.focus_set()
                except Exception:
                    pass

    def show_toast(self, text):
        toast = tk.Label(self.root, text=text, bg='#25d366', fg='#0b1a0e',
                         font=("Segoe UI", 10, "bold"), padx=16, pady=6)
        toast.place(relx=0.5, rely=0.94, anchor=tk.CENTER)
        self.root.after(2000, toast.destroy)

    def notify(self, title, message='', kind='info', duration=5000):
        """Modern left-side notification with a countdown bar (see Notifier)."""
        try:
            self.notifier.notify(title, message, kind, duration)
        except Exception:
            self.show_toast(f"{title}: {message}" if message else title)

    # ============================================================
    # ONLINE COUNT
    # ============================================================
    def update_client_count(self, count):
        self.onl.configure(text=f"Online: {count}")
        self.cc.configure(text=f"Clients: {count} / {getattr(self, 'server_max', 20)}")
