# server_dashboard.py — the Tk "control room": theme, custom widgets and
# the ServerApp class (live view of clients, chats, groups, activity, logs).
from server_core import *
import server_core



# ============================================================
#  SERVER DASHBOARD  -  modern 3-panel UI (client jaisa)
# ============================================================
PALETTES = {
    'dark': {
        'bg': '#0b141a', 'nav': '#111b21', 'mid': '#111b21', 'right': '#0b141a',
        'card': '#182229', 'card2': '#202c33',
        'text': '#e9edef', 'sub': '#8696a0', 'dim': '#5c6b73',
        'accent': '#00a884', 'accent_d': '#005c4b',
        'border': '#222d34', 'input': '#202c33', 'hover': '#1f2c34',
        'bubble_in': '#202c33', 'bubble_out': '#005c4b',
        'ok': '#00a884', 'warn': '#f0b232', 'bad': '#f15c6d', 'chip': '#202c33',
    },
    'light': {
        'bg': '#e9eef2', 'nav': '#ffffff', 'mid': '#ffffff', 'right': '#f0f2f5',
        'card': '#ffffff', 'card2': '#f0f2f5',
        'text': '#111b21', 'sub': '#54656f', 'dim': '#7a8a93',
        'accent': '#00a884', 'accent_d': '#d9fdd3',
        'border': '#dde3e8', 'input': '#f0f2f5', 'hover': '#eef2f5',
        'bubble_in': '#ffffff', 'bubble_out': '#d9fdd3',
        'ok': '#00a884', 'warn': '#b7791f', 'bad': '#d32f2f', 'chip': '#eef2f5',
    },
}

# the log terminal stays dark in BOTH themes -> "hacking" feel
TERM = {
    'bg': '#04120b', 'bar': '#071c11', 'fg': '#00ff88', 'dim': '#2f8f63',
    'actor': '#c8ffe0', 'border': '#0f3d28', 'err': '#ff5c5c',
}

VIEWS = [
    ('clients',  'clients',  'Clients',  'who is online right now'),
    ('chats',    'chat',     'Chats',    'every 1-to-1 conversation'),
    ('groups',   'group',    'Groups',   'group chats and their members'),
    ('activity', 'activity', 'Activity', 'who changed what, live'),
    ('log',      'log',      'Log',      'live terminal feed'),
    ('settings', 'settings', 'Settings', 'server configuration'),
]
VIEW_META = {v[0]: {'title': v[2], 'sub': v[3]} for v in VIEWS}


def _rr(cv, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle drawn as one smooth polygon."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


class ThemeManager:
    def __init__(self, name='dark'):
        self.name = 'dark'
        self.current = dict(PALETTES['dark'])
        self.set_theme(name)

    def set_theme(self, name):
        self.name = 'dark' if str(name).lower().startswith('d') else 'light'
        self.current = dict(PALETTES[self.name])
        return self.current

    def get(self, key):
        return self.current.get(key, '#000000')


class GlyphButton(tk.Canvas):
    """Flat icon button with a caption + hover / active states (crisp glyphs)."""

    def __init__(self, parent, icon="", text="", icon_font=("Segoe UI Symbol", 16),
                 font=("Segoe UI", 7, "bold"), bg="#111b21", fg="#8696a0",
                 hover_bg="#1f2c34", active_bg="#202c33", active_fg="#00a884",
                 command=None, width=74, height=58, radius=12, **kw):
        super().__init__(parent, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2", **kw)
        self.icon, self.text = icon, text
        self.icon_font, self.font = icon_font, font
        self.bg, self.fg = bg, fg
        self.hover_bg, self.active_bg, self.active_fg = hover_bg, active_bg, active_fg
        self.command = command
        self.w, self.h, self.radius = width, height, radius
        self.active = False
        self.hovered = False
        self.bind('<Enter>', self._enter)
        self.bind('<Leave>', self._leave)
        self.bind('<Button-1>', self._click)
        self.draw()

    def _enter(self, _=None):
        self.hovered = True
        self.draw()

    def _leave(self, _=None):
        self.hovered = False
        self.draw()

    def _click(self, _=None):
        if self.command:
            self.command()

    def set_active(self, on):
        self.active = bool(on)
        self.draw()

    def draw(self):
        self.delete('all')
        fg = self.fg
        if self.active:
            _rr(self, 4, 4, self.w - 4, self.h - 4, self.radius,
                fill=self.active_bg, outline='')
            fg = self.active_fg
        elif self.hovered:
            _rr(self, 4, 4, self.w - 4, self.h - 4, self.radius,
                fill=self.hover_bg, outline='')
        self.create_text(self.w / 2, self.h / 2 - 6, text=self.icon,
                         fill=fg, font=self.icon_font)
        if self.text:
            self.create_text(self.w / 2, self.h / 2 + 15, text=self.text,
                             fill=fg, font=self.font)


class RoundButton(tk.Canvas):
    """A flat, rounded, hover-aware button drawn on a canvas."""

    def __init__(self, parent, text="", command=None, bg="#202c33", fg="#e9edef",
                 hover_bg=None, parent_bg="#111b21", font=("Segoe UI", 9, 'bold'),
                 width=160, height=30, radius=9, anchor='w', pad_x=12, **kw):
        super().__init__(parent, width=width, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor='hand2', **kw)
        self._text = text
        self._command = command
        self._bg = bg
        self._fg = fg
        self._hover = hover_bg or self._shade(bg)
        self._parent_bg = parent_bg
        self._font = font
        self._cw, self._ch, self._r = width, height, radius
        self._anchor = anchor
        self._pad = pad_x
        self._hovered = False
        self.bind('<Enter>', self._enter)
        self.bind('<Leave>', self._leave)
        self.bind('<Button-1>', self._click)
        self._draw()

    @staticmethod
    def _shade(color):
        try:
            r = int(color[1:3], 16); g = int(color[3:5], 16); b = int(color[5:7], 16)
            r = min(255, r + 14); g = min(255, g + 14); b = min(255, b + 14)
            return '#%02x%02x%02x' % (r, g, b)
        except Exception:
            return color

    def _enter(self, _=None):
        self._hovered = True
        self._draw()

    def _leave(self, _=None):
        self._hovered = False
        self._draw()

    def _click(self, _=None):
        if self._command:
            self._command()

    def set_text(self, text):
        self._text = text
        self._draw()

    def set_colors(self, bg=None, fg=None):
        if bg:
            self._bg = bg
            self._hover = self._shade(bg)
        if fg:
            self._fg = fg
        self._draw()

    def _draw(self):
        self.delete('all')
        _rr(self, 0, 0, self._cw, self._ch, self._r,
            fill=(self._hover if self._hovered else self._bg), outline='')
        x = self._pad if self._anchor == 'w' else self._cw / 2
        self.create_text(x, self._ch / 2, text=self._text, anchor=self._anchor,
                         fill=self._fg, font=self._font)


class RoundPanel(tk.Frame):
    """A card with rounded corners: a rounded shape is painted behind the
    children, so anything packed inside sits on a soft rounded surface."""

    def __init__(self, parent, radius=12, bg='#202c33', parent_bg='#111b21', **kw):
        super().__init__(parent, bg=parent_bg, **kw)
        self._bg = bg
        self._radius = radius
        self._canvas = tk.Canvas(self, bg=parent_bg, highlightthickness=0, bd=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bind('<Configure>', self._redraw)

    def _redraw(self, _=None):
        w = self.winfo_width()
        h = self.winfo_height()
        self._canvas.delete('bg')
        _rr(self._canvas, 0, 0, max(2, w), max(2, h), self._radius,
            fill=self._bg, outline='', tags='bg')


class RoundedEntry(tk.Frame):
    """A flat, rounded text field with a placeholder + focus highlight.

    It proxies the few tk.Entry methods the dashboard uses (get / delete /
    insert / bind / focus_set), so it drops straight into their place.
    """

    def __init__(self, parent, placeholder='', icon='', icon_font=("Segoe UI Symbol", 11),
                 font=("Segoe UI", 10), bg='#202c33', fg='#e9edef',
                 ph_fg='#8696a0', parent_bg='#111b21', radius=10, height=34,
                 border='#202c33', focus_border='#00a884', on_change=None,
                 on_submit=None, **kw):
        super().__init__(parent, bg=parent_bg, height=height, **kw)
        self.pack_propagate(False)
        self._bg, self._parent_bg = bg, parent_bg
        self._border, self._focus_border = border, focus_border
        self._radius, self._height = radius, height
        self._ph_fg, self._fg = ph_fg, fg
        self._placeholder = placeholder
        self._icon = icon
        self._on_change, self._on_submit = on_change, on_submit
        self._is_ph = False

        self.cv = tk.Canvas(self, bg=parent_bg, highlightthickness=0, bd=0,
                            height=height)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self._icon_id = self.cv.create_text(13, height / 2, text=icon,
                                            fill=ph_fg, font=icon_font, anchor='w')
        left = 30 if icon else 12
        self.entry = tk.Entry(self.cv, bg=bg, fg=fg, bd=0, relief=tk.FLAT,
                              font=font, insertbackground=fg,
                              highlightthickness=0)
        self._win = self.cv.create_window(left, height / 2, window=self.entry,
                                          anchor='w', height=height - 8)
        self.cv.bind('<Configure>', lambda e: self._redraw())
        self.cv.bind('<Button-1>', lambda e: self.focus_set())
        self.entry.bind('<FocusIn>', self._focus_in)
        self.entry.bind('<FocusOut>', self._focus_out)
        self.entry.bind('<KeyRelease>', self._key_release)
        self.entry.bind('<Return>', self._submit)
        self._show_placeholder()

    # ---- placeholder handling ----
    def _show_placeholder(self):
        if not self.entry.get():
            self._is_ph = True
            self.entry.delete(0, 'end')
            self.entry.insert(0, self._placeholder)
            self.entry.configure(fg=self._ph_fg)

    def _hide_placeholder(self):
        if self._is_ph:
            self._is_ph = False
            self.entry.delete(0, 'end')
            self.entry.configure(fg=self._fg)

    def set_placeholder(self, text):
        self._placeholder = text
        # replace whatever we are showing when it is a placeholder (or empty),
        # but never stomp on text the user actually typed
        if self._is_ph or not self.entry.get():
            self._is_ph = True
            self.entry.delete(0, 'end')
            self.entry.insert(0, text)
            self.entry.configure(fg=self._ph_fg)
        self._redraw()

    def _key_release(self, _=None):
        if self._on_change:
            self._on_change()

    def _submit(self, _=None):
        if self._on_submit:
            self._on_submit()
        return 'break'

    def _focus_in(self, _=None):
        self._hide_placeholder()
        self._redraw()

    def _focus_out(self, _=None):
        self._show_placeholder()
        self._redraw()

    def _focused(self):
        try:
            return self.entry.focus_get() is self.entry
        except Exception:
            return False

    def _redraw(self):
        w = self.cv.winfo_width()
        h = self.cv.winfo_height()
        if w <= 1:
            w = self.winfo_width()
        if h <= 1:
            h = self._height
        if w <= 1:
            return
        col = self._focus_border if self._focused() else self._border
        self.cv.delete('field')
        _rr(self.cv, 1, 1, max(2, w - 1), max(2, h - 1), self._radius,
            fill=self._bg, outline=col, width=1, tags='field')
        self.cv.tag_lower('field')
        left = 30 if self._icon else 12
        try:
            self.cv.coords(self._icon_id, 13, h / 2)
            self.cv.coords(self._win, left, h / 2)
            self.cv.itemconfigure(self._win, width=max(10, w - left - 12),
                                  height=max(10, h - 8))
        except Exception:
            pass

    # ---- tk.Entry proxy ----
    def get(self):
        return '' if self._is_ph else self.entry.get()

    def delete(self, *a):
        self._hide_placeholder()
        r = self.entry.delete(*a)
        if not self._focused():
            self._show_placeholder()
        return r

    def insert(self, *a):
        self._hide_placeholder()
        return self.entry.insert(*a)

    def bind(self, seq=None, fn=None, add=None):
        if seq is None:
            return super().bind(seq, fn, add)
        return self.entry.bind(seq, fn, add)

    def focus_set(self):
        try:
            self.entry.focus_set()
        except Exception:
            pass
        self._redraw()


class ServerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat Server  \u2022  Control Room")
        self.root.geometry("1460x880")
        self.root.minsize(1180, 720)
        self.theme = ThemeManager('dark')
        self.current_view = 'clients'
        self.sel_client = None
        self.sel_chat = None
        self.sel_group = None
        self.sel_act = None
        self.act_filter = 'all'
        self.compose_target = None
        self.term_lines = collections.deque(maxlen=600)
        self.term = None
        self._fonts = {}
        self._srv_imgs = []          # keep dashboard thumbnails alive (Tk GC)
        self._mid_sig = None
        self._right_sig = None
        self.server_thread = None
        self.is_running = False
        self.started_at = datetime.now()
        self.lan_ips = _detect_lan_ips()      # re-scanned every few seconds
        self._dots = []       # every animated dot currently on screen
        self._live = []       # (label, value_fn) refreshed by the tick loop
        self._tick_n = 0
        self._lan_age = 0
        self._ticking = False
        try:
            tkfont.Font(family="Consolas", size=9)
        except Exception:
            pass
        server_core.SERVER_UI = self
        self.setup_ui()
        # inputs are only "active" while clicked into: a click anywhere that is
        # not a text field drops focus, so everything returns to its idle look
        self.root.bind('<Button-1>', self._blur_inputs, add='+')
        self.start_server()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _blur_inputs(self, event=None):
        """Deactivate the text fields when the user clicks somewhere else."""
        node = getattr(event, 'widget', None)
        while node is not None:
            if isinstance(node, (tk.Entry, tk.Spinbox, tk.Text, RoundedEntry)):
                return
            node = getattr(node, 'master', None)
        try:
            self.root.focus_set()
        except Exception:
            pass

    # ---------- tiny helpers ----------
    def _t(self, key):
        return self.theme.get(key)

    def _font(self, spec):
        key = tuple(spec) if isinstance(spec, (tuple, list)) else str(spec)
        f = self._fonts.get(key)
        if f is None:
            f = tkfont.Font(font=spec)
            self._fonts[key] = f
        return f

    def _name_color(self, name):
        pal = ['#00a884', '#1f6feb', '#8957e5', '#bf4b8a',
               '#e3b341', '#2da44e', '#cf222e', '#0e7490']
        return pal[sum(ord(ch) for ch in str(name)) % len(pal)]

    def _avatar(self, parent, name, color, size=34, bg=None):
        cv = tk.Canvas(parent, width=size, height=size, bg=bg or self._t('mid'),
                       highlightthickness=0, bd=0)
        cv.create_oval(1, 1, size - 1, size - 1, fill=color, outline='')
        init = ''.join(w[0] for w in str(name).split()[:2]).upper() or '?'
        cv.create_text(size / 2, size / 2, text=init, fill='white',
                       font=("Segoe UI", max(8, int(size / 2.7)), 'bold'))
        return cv

    def _paint(self, w, color):
        try:
            w.configure(bg=color)
        except Exception:
            pass
        for c in w.winfo_children():
            self._paint(c, color)

    # ---------- live indicators (uptime, address, blinking dot) ----------
    def _make_live_dot(self, parent, color, bg, size=6):
        """A small dot that bobs up and down, with a ping ring around it.

        Every dot registers itself in `self._dots`; the tick loop moves them,
        so anything on screen that means "this is live" actually moves.
        Returns (canvas, entry) - keep the entry to recolour the dot later.
        """
        pad = 5                        # room for the bob + the ping ring
        w = size + 2 * pad
        bbox = (pad, pad, pad + size, pad + size)
        cv = tk.Canvas(parent, width=w, height=w, bg=bg, highlightthickness=0, bd=0)
        ring = cv.create_oval(*bbox, fill='', outline=color, width=1, state='hidden')
        item = cv.create_oval(*bbox, fill=color, outline='')
        entry = {'cv': cv, 'item': item, 'ring': ring, 'bbox': bbox,
                 'size': size, 'bg': bg, 'color': color}
        self._set_dot_color(entry, color)
        self._dots.append(entry)
        return cv, entry

    def _set_dot_color(self, entry, color):
        """Recolour a live dot; its ping ring fades from the colour to the bg."""
        try:
            entry['color'] = color
            entry['ring_cols'] = [_mix(color, entry.get('bg', '#111b21'), i / 2.0)
                                  for i in range(3)]
            entry['cv'].itemconfigure(entry['item'], fill=color)
        except Exception:
            pass

    def uptime_text(self):
        """How long the server has been up - keeps counting by itself."""
        s = int((datetime.now() - self.started_at).total_seconds())
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        if h:
            return "%dh %02dm %02ds" % (h, m, sec)
        return "%dm %02ds" % (m, sec)

    def _lan_line(self):
        """The address a client on the same Wi-Fi has to type."""
        ips = getattr(self, 'lan_ips', None) or []
        if not ips:
            return "not detected  \u00b7  localhost only"
        return "  \u00b7  ".join("%s:%d" % (ip, PORT) for ip in ips[:2])

    def _bind_line(self):
        return "0.0.0.0:%d  (all interfaces)" % PORT

    def _running_cell(self, parent):
        """The 'Running' value cell: a dot that animates + the word Running."""
        wrap = tk.Frame(parent, bg=self._t('card'))
        cv, _e = self._make_live_dot(wrap, self._t('ok'), self._t('card'), size=8)
        cv.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(wrap, text="Running", bg=self._t('card'), fg=self._t('text'),
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        return wrap

    def _tick(self):
        """Drive the animations + refresh every live value (1x per second)."""
        try:
            self._tick_n = n = getattr(self, '_tick_n', 0) + 1
            dy = BOB[n % len(BOB)]
            expand = RING[n % len(RING)]
            alive = []
            for d in getattr(self, '_dots', ()):
                try:
                    if not d['cv'].winfo_exists():
                        continue
                    x0, y0, x1, y1 = d['bbox']
                    d['cv'].coords(d['item'], x0, y0 + dy, x1, y1 + dy)
                    if expand:
                        e = min(expand, 3)
                        d['cv'].coords(d['ring'], x0 - e, y0 - e + dy,
                                       x1 + e, y1 + e + dy)
                        d['cv'].itemconfigure(d['ring'], state='normal',
                                              outline=d['ring_cols'][e - 1])
                    else:
                        d['cv'].itemconfigure(d['ring'], state='hidden')
                    alive.append(d)
                except Exception:
                    continue
            self._dots = alive
            if n % 10 == 0:
                self._refresh_live()
            self._lan_age = getattr(self, '_lan_age', 0) + 1
            if self._lan_age >= 50:               # re-scan the LAN address ~5 s
                self._lan_age = 0
                try:
                    self.lan_ips = _detect_lan_ips()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.root.after(100, self._tick)
        except Exception:
            pass

    def _refresh_live(self):
        """Re-read every live value: uptime, LAN address, counters."""
        keep = []
        for lbl, fn in getattr(self, '_live', ()):
            try:
                if not lbl.winfo_exists():
                    continue
                lbl.configure(text=str(fn()))
                keep.append((lbl, fn))
            except Exception:
                continue
        self._live = keep
        try:
            self.count_lbl.configure(text="%d/%d" % (len(connected_clients), MAX_CLIENTS))
            self.event_lbl.configure(text="%d events" % len(activity_log))
        except Exception:
            pass

    def _bind_wheel(self, canvas, inner):
        def on_wheel(e):
            try:
                if inner.winfo_reqheight() <= canvas.winfo_height():
                    return
                canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')
            except Exception:
                pass
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', on_wheel))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

    # ============================================================
    #  UI CONSTRUCTION
    # ============================================================
    def setup_ui(self):
        self.term = None
        self.icon_fam = pick_icon_font(self.root)
        self.if_big = (self.icon_fam, 20)
        self.if_md = (self.icon_fam, 15)
        self.if_sm = (self.icon_fam, 13)
        self.root.configure(bg=self._t('bg'))
        self.main = tk.Frame(self.root, bg=self._t('bg'))
        self.main.pack(fill=tk.BOTH, expand=True)
        self._build_rail()
        self._build_middle()
        self._build_right()
        if self.is_running:
            self._set_dot(self._t('ok'))
        self.switch_view(self.current_view)

    # ---------- left rail ----------
    def _build_rail(self):
        rail = tk.Frame(self.main, bg=self._t('nav'), width=88)
        rail.pack(side=tk.LEFT, fill=tk.Y)
        rail.pack_propagate(False)
        self.rail = rail

        logo = tk.Canvas(rail, width=56, height=56, bg=self._t('nav'),
                         highlightthickness=0)
        logo.pack(pady=(16, 4))
        logo.create_oval(3, 3, 53, 53, fill=self._t('accent'), outline='')
        logo.create_text(28, 28, text=ic('box'), fill='#06302a', font=(self.icon_fam, 24))
        tk.Label(rail, text="SERVER", bg=self._t('nav'), fg=self._t('sub'),
                 font=("Segoe UI", 7, 'bold')).pack(pady=(0, 12))

        self.rail_btns = {}
        for view, icon, label, _sub in VIEWS:
            b = GlyphButton(rail, icon=ic(icon), text=label,
                            icon_font=(self.icon_fam, 16),
                            font=("Segoe UI", 7, 'bold'),
                            bg=self._t('nav'), fg=self._t('sub'),
                            hover_bg=self._t('hover'), active_bg=self._t('card2'),
                            active_fg=self._t('accent'),
                            command=lambda v=view: self.switch_view(v))
            b.pack(pady=2)
            self.rail_btns[view] = b

        foot = tk.Frame(rail, bg=self._t('nav'))
        foot.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 14))
        # a live indicator: it bobs up and down while the server is running
        self.status_dot, self._dot_entry = self._make_live_dot(
            foot, self._t('warn'), self._t('nav'), size=10)
        self._dot = self._dot_entry['item']
        self.status_dot.pack()
        self.count_lbl = tk.Label(foot, text="0/%d" % MAX_CLIENTS, bg=self._t('nav'),
                                  fg=self._t('text'), font=("Segoe UI", 8, 'bold'))
        self.count_lbl.pack(pady=(4, 0))
        self.event_lbl = tk.Label(foot, text="0 events", bg=self._t('nav'),
                                  fg=self._t('dim'), font=("Segoe UI", 7))
        self.event_lbl.pack()

    # ---------- middle list ----------
    def _build_middle(self):
        mid = tk.Frame(self.main, bg=self._t('mid'), width=350)
        mid.pack(side=tk.LEFT, fill=tk.Y)
        mid.pack_propagate(False)
        self.mid = mid

        head = tk.Frame(mid, bg=self._t('mid'))
        head.pack(fill=tk.X, padx=16, pady=(16, 8))
        self.mid_title = tk.Label(head, text="Clients", bg=self._t('mid'),
                                  fg=self._t('text'), font=("Segoe UI", 15, 'bold'))
        self.mid_title.pack(anchor='w')
        self.mid_sub = tk.Label(head, text="", bg=self._t('mid'), fg=self._t('sub'),
                                font=("Segoe UI", 8))
        self.mid_sub.pack(anchor='w', pady=(2, 0))

        self.search_e = RoundedEntry(
            mid, placeholder="Search", icon=ic('search'), icon_font=self.if_sm,
            font=("Segoe UI", 10), bg=self._t('input'), fg=self._t('text'),
            ph_fg=self._t('sub'), parent_bg=self._t('mid'),
            border=self._t('input'), focus_border=self._t('accent'),
            on_change=lambda: self._render_middle(force=True))
        self.search_wrap = self.search_e

        body = tk.Frame(mid, bg=self._t('mid'))
        body.pack(fill=tk.BOTH, expand=True)
        self.mid_body = body
        self.mid_canvas = tk.Canvas(body, bg=self._t('mid'), highlightthickness=0, bd=0)
        self.mid_scroll = tk.Scrollbar(body, orient=tk.VERTICAL, command=self.mid_canvas.yview)
        self.mid_inner = tk.Frame(self.mid_canvas, bg=self._t('mid'))
        self.mid_inner.bind("<Configure>", lambda e: self.mid_canvas.configure(
            scrollregion=self.mid_canvas.bbox("all")))
        self.mid_win = self.mid_canvas.create_window((0, 0), window=self.mid_inner, anchor='nw')
        self.mid_canvas.configure(yscrollcommand=self.mid_scroll.set)
        self.mid_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.mid_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.mid_canvas.bind('<Configure>',
                             lambda e: self.mid_canvas.itemconfigure(self.mid_win, width=e.width))
        self._bind_wheel(self.mid_canvas, self.mid_inner)

    # ---------- right main-data panel ----------
    def _build_right(self):
        right = tk.Frame(self.main, bg=self._t('right'))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.right = right

        # compose bar first (bottom) so the scroll body can expand
        self.compose = tk.Frame(right, bg=self._t('mid'))
        tk.Frame(self.compose, height=1, bg=self._t('border')).pack(fill=tk.X)
        row = tk.Frame(self.compose, bg=self._t('mid'))
        row.pack(fill=tk.X, padx=16, pady=(10, 4))
        tk.Label(row, text=ic('bell'), bg=self._t('mid'), fg=self._t('accent'),
                 font=self.if_md).pack(side=tk.LEFT, padx=(0, 8))
        self.recipient_menu = tk.Menu(self.root, tearoff=0,
                                      bg=self._t('card2'), fg=self._t('text'),
                                      activebackground=self._t('accent'),
                                      activeforeground='white', bd=0,
                                      font=("Segoe UI", 9))
        self.recipient_btn = RoundButton(
            row, text="All clients (broadcast)  \u25be",
            command=self._open_recipient_menu,
            bg=self._t('input'), fg=self._t('text'), parent_bg=self._t('mid'),
            font=("Segoe UI", 9), width=210, height=32, radius=9, pad_x=12)
        self.recipient_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.compose_e = RoundedEntry(
            row, placeholder="Broadcast", font=("Segoe UI", 10),
            bg=self._t('input'), fg=self._t('text'), ph_fg=self._t('sub'),
            parent_bg=self._t('mid'), border=self._t('input'),
            focus_border=self._t('accent'), on_submit=self.send_compose)
        self.compose_e.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.send_btn = RoundButton(
            row, text=ic('send'), command=self.send_compose,
            bg=self._t('accent'), fg='white', parent_bg=self._t('mid'),
            font=self.if_md, width=44, height=32, radius=9, anchor='center')
        self.send_btn.pack(side=tk.LEFT)
        self.compose_hint = tk.Label(self.compose, text="", bg=self._t('mid'),
                                     fg=self._t('sub'), font=("Segoe UI", 8))
        self.compose_hint.pack(anchor='w', padx=20, pady=(0, 9))

        head = tk.Frame(right, bg=self._t('nav'))
        head.pack(side=tk.TOP, fill=tk.X)
        h = tk.Frame(head, bg=self._t('nav'))
        h.pack(fill=tk.X, padx=20, pady=12)
        self.r_title = tk.Label(h, text="Server overview", bg=self._t('nav'),
                                fg=self._t('text'), font=("Segoe UI", 13, 'bold'))
        self.r_title.pack(anchor='w')
        self.r_sub = tk.Label(h, text="", bg=self._t('nav'), fg=self._t('sub'),
                              font=("Segoe UI", 8))
        self.r_sub.pack(anchor='w', pady=(2, 0))
        tk.Frame(right, height=1, bg=self._t('border')).pack(side=tk.TOP, fill=tk.X)

        body = tk.Frame(right, bg=self._t('right'))
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.r_body = body
        self.r_canvas = tk.Canvas(body, bg=self._t('right'), highlightthickness=0, bd=0)
        self.r_scroll = tk.Scrollbar(body, orient=tk.VERTICAL, command=self.r_canvas.yview)
        self.r_inner = tk.Frame(self.r_canvas, bg=self._t('right'))
        self.r_inner.bind("<Configure>", lambda e: self.r_canvas.configure(
            scrollregion=self.r_canvas.bbox("all")))
        self.r_win = self.r_canvas.create_window((0, 0), window=self.r_inner, anchor='nw')
        self.r_canvas.configure(yscrollcommand=self.r_scroll.set)
        self.r_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.r_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.r_canvas.bind('<Configure>',
                           lambda e: self.r_canvas.itemconfigure(self.r_win, width=e.width))
        self._bind_wheel(self.r_canvas, self.r_inner)
        self._refresh_recipients()

    # ============================================================
    #  NAVIGATION
    # ============================================================
    def switch_view(self, view):
        self.current_view = view
        for v, b in self.rail_btns.items():
            b.set_active(v == view)
        if view in ('clients', 'chats', 'groups', 'activity'):
            self.search_wrap.pack(fill=tk.X, padx=16, pady=(0, 8), before=self.mid_body)
        else:
            self.search_wrap.pack_forget()
        if view in ('clients', 'chats', 'groups', 'activity'):
            self.compose.pack(side=tk.BOTTOM, fill=tk.X, before=self.r_body)
        else:
            self.compose.pack_forget()
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)

    # keep the old name working (the poll loop used it)
    def refresh_middle(self, force=False):
        self._render_middle(force=force)

    # ============================================================
    #  MIDDLE PANEL
    # ============================================================
    def _middle_sig(self):
        v = self.current_view
        q = self.search_e.get().lower()
        if v == 'clients':
            return (v, tuple(sorted(connected_clients.keys())), q, self.sel_client)
        if v == 'chats':
            return (v, len(conversations), sum(len(m) for m in conversations.values()),
                    q, self.sel_chat)
        if v == 'groups':
            return (v, tuple(sorted(groups.keys())), q, self.sel_group)
        if v == 'activity':
            return (v, len(activity_log), self.act_filter, q, self.sel_act)
        return (v, len(activity_log), self.act_filter)

    def _render_middle(self, force=False):
        view = self.current_view
        sig = self._middle_sig()
        if not force and sig == self._mid_sig:
            return
        self._mid_sig = sig
        for w in self.mid_inner.winfo_children():
            w.destroy()
        try:
            self.mid_canvas.yview_moveto(0)
        except Exception:
            pass
        meta = VIEW_META.get(view, {'title': view.title(), 'sub': ''})
        self.mid_title.configure(text=meta['title'])
        self.mid_sub.configure(text=meta['sub'])
        getattr(self, '_mid_' + view, self._mid_clients)()
        self.count_lbl.configure(text="%d/%d" % (len(connected_clients), MAX_CLIENTS))
        self.event_lbl.configure(text="%d events" % len(activity_log))

    # ---------- list row factory ----------
    def _list_row(self, parent, title, sub="", right="", badge=None, dot=None,
                  avatar=None, avatar_color=None, sel=False, on_click=None,
                  live=False, keep=None):
        """One list row.  `live=True` makes the dot animate; `keep` receives the
        widgets so the caller can refresh the text later on."""
        base = self._t('hover') if sel else self._t('mid')
        fr = tk.Frame(parent, bg=base, cursor='hand2')
        fr.pack(fill=tk.X)
        if sel:
            tk.Frame(fr, width=3, bg=self._t('accent')).pack(side=tk.LEFT, fill=tk.Y)
        if avatar:
            self._avatar(fr, avatar, avatar_color or self._name_color(avatar), 36,
                         bg=base).pack(side=tk.LEFT, padx=(11, 10), pady=9)
        pad = tk.Frame(fr, bg=base)
        pad.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                 padx=(0 if avatar else 14, 10), pady=9)
        top = tk.Frame(pad, bg=base)
        top.pack(fill=tk.X)
        tk.Label(top, text=title, bg=base, fg=self._t('text'),
                 font=("Segoe UI", 10, 'bold'), anchor='w').pack(side=tk.LEFT)
        right_lbl = None
        if right:
            right_lbl = tk.Label(top, text=right, bg=base, fg=self._t('sub'),
                                 font=("Segoe UI", 8), anchor='e')
            right_lbl.pack(side=tk.RIGHT)
        low = tk.Frame(pad, bg=base)
        low.pack(fill=tk.X, pady=(2, 0))
        dot_cv = dot_entry = None
        if dot:
            if live:
                dot_cv, dot_entry = self._make_live_dot(low, dot, base)
            else:
                dot_cv = tk.Canvas(low, width=8, height=8, bg=base,
                                   highlightthickness=0, bd=0)
                dot_cv.create_oval(0, 0, 8, 8, fill=dot, outline='')
            dot_cv.pack(side=tk.LEFT, padx=(0, 6))
        sub_lbl = tk.Label(low, text=sub, bg=base, fg=self._t('sub'),
                           font=("Segoe UI", 8), anchor='w')
        sub_lbl.pack(side=tk.LEFT)
        if badge:
            tk.Label(fr, text=str(badge), bg=self._t('accent'), fg='white',
                     font=("Segoe UI", 8, 'bold'), padx=7, pady=1).pack(side=tk.RIGHT,
                                                                        padx=(0, 10))
        self._hover_row(fr, base, self._t('hover'), on_click)
        if keep is not None:
            keep.update({'frame': fr, 'sub_lbl': sub_lbl, 'right_lbl': right_lbl,
                         'dot_cv': dot_cv, 'dot_entry': dot_entry})
        return fr

    def _hover_row(self, fr, base, hover, on_click):
        def enter(_=None):
            self._paint(fr, hover)

        def leave(e=None):
            try:
                under = fr.winfo_containing(e.x_root, e.y_root)
            except Exception:
                under = None
            if under is not None and str(under).startswith(str(fr)):
                return
            self._paint(fr, base)

        def bind_all(w):
            w.bind('<Enter>', enter, add='+')
            w.bind('<Leave>', leave, add='+')
            if on_click:
                w.bind('<Button-1>', lambda e: on_click(), add='+')
            for c in w.winfo_children():
                bind_all(c)
        bind_all(fr)

    def _empty(self, parent, icon, title, sub, bg=None):
        bg = bg or self._t('mid')
        box = tk.Frame(parent, bg=bg)
        box.pack(fill=tk.BOTH, expand=True, pady=70)
        cv = tk.Canvas(box, width=70, height=70, bg=bg, highlightthickness=0)
        cv.pack()
        cv.create_oval(3, 3, 67, 67, fill=self._t('card2'), outline='')
        cv.create_text(35, 35, text=icon, fill=self._t('sub'), font=(self.icon_fam, 26))
        tk.Label(box, text=title, bg=bg, fg=self._t('text'),
                 font=("Segoe UI", 11, 'bold')).pack(pady=(14, 4))
        tk.Label(box, text=sub, bg=bg, fg=self._t('sub'), font=("Segoe UI", 9),
                 wraplength=240, justify='center').pack()

    # ---------- per-view middle ----------
    def _mid_clients(self):
        q = self.search_e.get().lower()
        clients = sorted(connected_clients.values(), key=lambda c: c.get('connected_at', ''))
        if q:
            clients = [c for c in clients
                       if q in c['username'].lower() or q in c.get('ip', '').lower()]
        if not clients:
            self._empty(self.mid_inner, ic('clients'), "No clients connected",
                        "Waiting for clients to join on port %d" % PORT)
            return
        for c in clients:
            sid = c['sid']
            self._list_row(
                self.mid_inner, title=c['username'],
                sub="%s  ·  joined %s" % (c.get('ip', '?'), c.get('connected_at', '')),
                right=sid[:6], avatar=c['username'],
                dot=self._t('ok'), sel=(self.sel_client == sid),
                on_click=lambda s=sid: self._pick_client(s))

    def _mid_chats(self):
        q = self.search_e.get().lower()
        items = []
        for key, msgs in conversations.items():
            if not msgs:
                continue
            a, b = key
            if q and q not in a.lower() and q not in b.lower():
                continue
            items.append((key, a, b, msgs[-1], len(msgs)))
        items.sort(key=lambda x: (str(x[3].get('time', '')), x[4]), reverse=True)
        if not items:
            self._empty(self.mid_inner, ic('chat'), "No conversations yet",
                        "Chats show up the moment two clients start talking")
            return
        for key, a, b, last, n in items:
            self._list_row(
                self.mid_inner, title="%s  \u2194  %s" % (a, b),
                sub="%s: %s" % (last.get('sender', ''), str(last.get('text', ''))[:32]),
                right=str(last.get('time', '')), badge=n, sel=(self.sel_chat == key),
                on_click=lambda k=key: self._pick_chat(k))

    def _mid_groups(self):
        q = self.search_e.get().lower()
        gs = sorted(groups.values(), key=lambda g: str(g['name']).lower())
        if q:
            gs = [g for g in gs if q in str(g['name']).lower()]
        if not gs:
            self._empty(self.mid_inner, ic('group'), "No groups yet",
                        "Groups created by clients appear here")
            return
        for g in gs:
            n = len(group_messages.get(g['id'], []))
            self._list_row(
                self.mid_inner, title=g['name'],
                sub="%d members  ·  by %s" % (len(g['members']), g['creator']),
                right="%d msgs" % n, avatar=g['name'],
                avatar_color='#2da44e', sel=(self.sel_group == g['id']),
                on_click=lambda gid=g['id']: self._pick_group(gid))

    def _mid_activity(self):
        q = self.search_e.get().lower()
        rows = list(enumerate(activity_log))[::-1]
        if self.act_filter != 'all':
            rows = [(i, r) for i, r in rows if r['kind'] == self.act_filter]
        if q:
            rows = [(i, r) for i, r in rows
                    if q in (r['summary'] + ' ' + r['actor']).lower()]
        if not rows:
            self._empty(self.mid_inner, ic('activity'), "Nothing here yet",
                        "Client-side changes will stream in live")
            return
        for i, r in rows[:300]:
            self._list_row(
                self.mid_inner, title=str(r['summary'])[:42],
                sub="%s  ·  %s" % (r['actor'], str(r['detail'])[:36]),
                right=r['ts'], dot=ACT_COLOR.get(r['kind'], '#94a3b8'),
                sel=(self.sel_act == i),
                on_click=lambda k=i: self._pick_activity(k))

    def _mid_log(self):
        counts = collections.Counter(r['kind'] for r in activity_log)
        chips = [
            ('all', 'All events', len(activity_log), '#94a3b8'),
            ('join', 'Connections', counts.get('join', 0) + counts.get('leave', 0), '#00ff88'),
            ('message', 'Messages', counts.get('message', 0), '#7dd3fc'),
            ('group', 'Groups', counts.get('group', 0), '#38bdf8'),
            ('settings', 'Settings', counts.get('settings', 0) + counts.get('profile', 0),
             '#fbbf24'),
            ('view', 'Screens', counts.get('view', 0), '#64748b'),
            ('error', 'Errors', counts.get('error', 0), '#ff5c5c'),
        ]
        for key, label, n, col in chips:
            self._list_row(self.mid_inner, title=label,
                           sub="filter the terminal", right=str(n), dot=col,
                           sel=(self.act_filter == key),
                           on_click=lambda k=key: self._set_filter(k))
        raw = tk.Frame(self.mid_inner, bg=self._t('mid'))
        raw.pack(fill=tk.X, padx=14, pady=16)
        b = self._pill(raw, "Clear activity log", on_click=self.clear_log)
        b.pack(anchor='w')

    def _mid_settings(self):
        """Server settings rows - the dynamic ones re-read themselves every
        second, and the dot next to 'Running' bobs up and down."""
        rows = [
            ("Server", lambda: "Running on %s" % self._lan_line(),
             self._t('ok'), ":%d" % PORT, True),
            ("Bind", self._bind_line, self._t('dim'), "", False),
            ("Clients", lambda: "%d connected  /  %d max"
             % (len(connected_clients), MAX_CLIENTS), self._t('accent'), "", False),
            ("Database", self._db_info, "#1f6feb", "SQLite", False),
            ("Chats", lambda: "%d conversations  \u00b7  %d groups"
             % (len(conversations), len(groups)), '#8957e5', "", False),
            ("Messages", lambda: "%d stored" % sum(len(m) for m in conversations.values()),
             '#0e7490', "", False),
            ("Uptime", self.uptime_text, '#e3b341', "live", False),
            ("Theme", lambda: self.theme.name.title(), '#bf4b8a', "", False),
        ]
        for name, val, col, right, animated in rows:
            keep = {}
            text = val() if callable(val) else val
            self._list_row(self.mid_inner, title=name, sub=text, dot=col,
                           right=right, live=animated, keep=keep)
            if callable(val) and keep.get('sub_lbl') is not None:
                self._live.append((keep['sub_lbl'], val))

    # ============================================================
    #  RIGHT PANEL (main data)
    # ============================================================
    def _right_state(self):
        v = self.current_view
        if v == 'clients':
            c = connected_clients.get(self.sel_client)
            return (v, self.sel_client, c.get('username') if c else None,
                    len(conversations), len(groups))
        if v == 'chats':
            msgs = conversations.get(self.sel_chat) if self.sel_chat else None
            return (v, self.sel_chat, len(msgs) if msgs else 0)
        if v == 'groups':
            g = groups.get(self.sel_group) if self.sel_group else None
            return (v, self.sel_group, len(group_messages.get(self.sel_group or '', [])),
                    len(g['members']) if g else 0)
        if v == 'activity':
            return (v, self.sel_act, len(activity_log))
        if v == 'settings':
            return (v, self.theme.name, MAX_CLIENTS, len(connected_clients))
        return (v,)

    def _render_right(self, force=False):
        if self.current_view == 'log' and not force and self.term is not None:
            self._update_term_count()
            return
        sig = self._right_state()
        if not force and sig == self._right_sig:
            return
        self._right_sig = sig
        for w in self.r_inner.winfo_children():
            w.destroy()
        self.term = None
        try:
            self.r_canvas.yview_moveto(0)
        except Exception:
            pass
        getattr(self, '_right_' + self.current_view, self._overview)()

    def _card(self, title, rows, icon=None):
        """A titled card.  Each row is `(key, value)` or `(key, value, cell)`.

        A callable `value` is re-read every second (so uptime keeps counting),
        and `cell` - when given - is a factory `f(parent) -> widget` that draws
        the value itself (used for the animated 'Running' dot).
        """
        card = RoundPanel(self.r_inner, radius=12, bg=self._t('card'),
                          parent_bg=self._t('right'))
        card.pack(fill=tk.X, padx=18, pady=(0, 10))
        hdr = tk.Frame(card, bg=self._t('card'))
        hdr.pack(fill=tk.X, padx=14, pady=(12, 6))
        if icon:
            tk.Label(hdr, text=icon, bg=self._t('card'), fg=self._t('accent'),
                     font=self.if_md).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(hdr, text=title, bg=self._t('card'), fg=self._t('text'),
                 font=("Segoe UI", 11, 'bold')).pack(side=tk.LEFT)
        for row in rows:
            key = row[0]
            val = row[1] if len(row) > 1 else ''
            cell = row[2] if len(row) > 2 else None
            r = tk.Frame(card, bg=self._t('card'))
            r.pack(fill=tk.X, padx=14, pady=3)
            tk.Label(r, text=str(key), bg=self._t('card'), fg=self._t('sub'),
                     font=("Segoe UI", 9), width=15, anchor='w').pack(side=tk.LEFT)
            if cell is not None:
                w = cell(r)
                if w is not None:
                    w.pack(side=tk.LEFT, fill=tk.X, expand=True)
                continue
            lbl = tk.Label(r, text=str(val() if callable(val) else val),
                           bg=self._t('card'), fg=self._t('text'),
                           font=("Segoe UI", 9), anchor='w', justify='left',
                           wraplength=620)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            if callable(val):
                self._live.append((lbl, val))
        tk.Frame(card, height=10, bg=self._t('card')).pack()
        return card

    def _pill(self, parent, text, active=False, on_click=None, bg=None, fg=None,
              radius=9):
        col = bg or (self._t('accent') if active else self._t('input'))
        f = fg or ('white' if active else self._t('text'))
        try:
            pbg = parent.cget('bg')
        except Exception:
            pbg = self._t('mid')
        return RoundButton(parent, text=text, command=on_click, bg=col, fg=f,
                           parent_bg=pbg, font=("Segoe UI", 9, 'bold'),
                           width=max(64, len(str(text)) * 7 + 28), height=30,
                           radius=radius, pad_x=14)

    def _overview(self):
        self.r_title.configure(text="Server overview")
        self.r_sub.configure(text="%s  \u00b7  live" % self._lan_line())
        self._card("Status", [
            ('Server', 'Running', self._running_cell),
            ('LAN address', self._lan_line),
            ('Bind address', self._bind_line),
            ('Uptime', self.uptime_text),
            ('Max clients', MAX_CLIENTS),
        ], icon=ic('power'))
        self._card("Traffic", [
            ('Online now', lambda: len(connected_clients)),
            ('Conversations', lambda: len(conversations)),
            ('Messages', lambda: sum(len(m) for m in conversations.values())),
            ('Groups', lambda: len(groups)),
            ('Events', lambda: len(activity_log)),
        ], icon=ic('activity'))
        self._card("Data", [
            ('Database', self._db_info),
            ('Contacts', lambda: sum(1 for _ in db_query("SELECT 1 FROM contacts"))),
        ], icon=ic('box'))
        clients = sorted(connected_clients.values(), key=lambda c: c.get('connected_at', ''))
        pad = tk.Frame(self.r_inner, bg=self._t('right'))
        pad.pack(fill=tk.X, padx=18, pady=(4, 20))
        tk.Label(pad, text="Online clients", bg=self._t('right'), fg=self._t('sub'),
                 font=("Segoe UI", 9, 'bold')).pack(anchor='w', pady=(0, 8))
        if not clients:
            tk.Label(pad, text="Nobody is connected yet.", bg=self._t('right'),
                     fg=self._t('dim'), font=("Segoe UI", 9)).pack(anchor='w')
        for c in clients:
            b = self._pill(pad, "%s   %s" % (c['username'], c.get('ip', '')),
                           on_click=lambda s=c['sid']: self._pick_client(s))
            b.pack(anchor='w', pady=3)
        self._refresh_recipients()

    def _right_clients(self):
        c = connected_clients.get(self.sel_client)
        if not c:
            self.sel_client = None
            self._overview()
            return
        self.r_title.configure(text=c['username'])
        self.r_sub.configure(text="%s  ·  sid %s" % (c.get('ip', '?'), c['sid'][:8]))
        head = tk.Frame(self.r_inner, bg=self._t('right'))
        head.pack(fill=tk.X, padx=18, pady=(18, 10))
        self._avatar(head, c['username'], self._name_color(c['username']), 62,
                     bg=self._t('right')).pack(side=tk.LEFT, padx=(0, 16))
        col = tk.Frame(head, bg=self._t('right'))
        col.pack(side=tk.LEFT, anchor='n')
        tk.Label(col, text=c['username'], bg=self._t('right'), fg=self._t('text'),
                 font=("Segoe UI", 16, 'bold')).pack(anchor='w')
        tk.Label(col, text="\u25CF online  ·  joined %s" % c.get('connected_at', ''),
                 bg=self._t('right'), fg=self._t('ok'),
                 font=("Segoe UI", 9)).pack(anchor='w', pady=(2, 0))
        msg_btn = self._pill(self.r_inner, "\u2709  Message %s" % c['username'], active=True,
                             on_click=lambda s=c['sid']: self._focus_compose(s))
        msg_btn.pack(anchor='w', padx=18, pady=(0, 12))

        self._card("Connection", [
            ('IP address', c.get('ip', '-') or '-'),
            ('Socket id', c['sid']),
            ('Connected at', c.get('connected_at', '-')),
        ], icon=ic('key'))

        mine = []
        for key, msgs in conversations.items():
            if c['username'] in key:
                other = key[0] if key[1] == c['username'] else key[1]
                mine.append((other, "%d messages" % len(msgs)))
        self._card("Chats", mine or [('-', 'no conversations yet')], icon=ic('chat'))

        gs = [(g['name'], "%d members" % len(g['members']))
              for g in groups.values() if c['username'] in g['members']]
        self._card("Groups", gs or [('-', 'not in any group')], icon=ic('group'))

        st = user_settings.get(c['username'], {})
        self._card("Preferences", [
            ('Theme', st.get('theme', '-')),
            ('Ringtone', st.get('ringtone', '-')),
            ('Call ringtone', st.get('call_ringtone', '-')),
            ('Notify volume', st.get('notification_volume', '-')),
            ('Call volume', st.get('call_volume', '-')),
        ], icon=ic('settings'))

        recent = [r for r in list(activity_log)[::-1] if r['actor'] == c['username']][:8]
        self._card("Recent changes by %s" % c['username'],
                   [(r['ts'], r['summary']) for r in recent] or [('-', 'nothing yet')],
                   icon=ic('activity'))
        tk.Frame(self.r_inner, height=16, bg=self._t('right')).pack()
        self._refresh_recipients()

    def _ticks(self, m):
        st = m.get('status', 'sent')
        if st == 'read':
            return '\u2713\u2713 read'
        if st == 'delivered':
            return '\u2713\u2713 delivered'
        return '\u2713 sent'

    def _bubble(self, parent, text, header, status, outgoing, msg=None):
        msg = msg or {}
        is_file = (msg.get('kind') or 'text') != 'text'
        if (not is_file) and (text is None or text == ''):
            return
        bg = self._t('bubble_out' if outgoing else 'bubble_in')
        fg = self._t('text')
        sub = self._t('sub')
        body_font = self._font(("Segoe UI", 10))
        head_font = self._font(("Segoe UI", 8, 'bold'))
        stat_font = self._font(("Segoe UI", 8))
        pad, wrap = 11, 470
        cont = tk.Frame(parent, bg=self._t('right'))
        cont.pack(fill=tk.X, padx=16, pady=3)
        cv = tk.Canvas(cont, bg=self._t('right'), highlightthickness=0, bd=0)
        cv.pack(side=tk.RIGHT if outgoing else tk.LEFT,
                anchor='e' if outgoing else 'w')
        y, max_x = pad, pad
        if header:
            hid = cv.create_text(pad, y, text=header, anchor='nw', font=head_font, fill=sub)
            bb = cv.bbox(hid)
            max_x, y = max(max_x, bb[2]), bb[3] + 3
        # ---- file payload (image thumbnail, else a name + size line) ----
        if is_file:
            fk = msg.get('file_kind') or 'file'
            fname = os.path.basename(str(msg.get('file_name') or 'file'))
            fsz = human_size(msg.get('file_size') or 0)
            photo = None
            if fk == 'image' and SRV_PIL_OK and msg.get('file_data'):
                try:
                    raw = base64.b64decode(msg['file_data'])
                    im = Image.open(io.BytesIO(raw)).convert('RGB')
                    im.thumbnail((300, 300))
                    photo = ImageTk.PhotoImage(im)
                    self._srv_imgs.append(photo)
                except Exception:
                    photo = None
            if photo is not None:
                iid = cv.create_image(pad, y, anchor='nw', image=photo)
                bb = cv.bbox(iid)
                max_x, y = max(max_x, bb[2]), bb[3] + 4
            else:
                iid = cv.create_text(pad, y, anchor='nw', font=body_font, fill=fg,
                                     text="%s  \u00b7  %s" % (fname, fsz))
                bb = cv.bbox(iid)
                max_x, y = max(max_x, bb[2]), bb[3] + 2
        if text:
            tid = cv.create_text(pad, y, text=text, anchor='nw', font=body_font, fill=fg,
                                 justify='left', width=wrap)
            bb = cv.bbox(tid)
            max_x, y = max(max_x, bb[2]), bb[3]
        if status:
            sid = cv.create_text(pad, y + 3, text=status, anchor='nw',
                                 font=stat_font, fill=sub)
            bb = cv.bbox(sid)
            max_x, y = max(max_x, bb[2]), bb[3]
        total_w = int(min(wrap + 2 * pad, max_x + pad))
        total_h = int(y + pad)
        cv.configure(width=total_w, height=total_h)
        rect = _rr(cv, 1, 1, total_w - 1, total_h - 1, 12, fill=bg, outline='')
        cv.tag_lower(rect)
        return cont

    def _right_chats(self):
        key = self.sel_chat
        msgs = conversations.get(key) if key else None
        if not msgs:
            self.sel_chat = None
            self.r_title.configure(text="Chat log")
            self.r_sub.configure(text="pick a conversation from the list")
            self._empty(self.r_inner, ic('chat'), "Select a conversation",
                        "The full message history will be shown here", bg=self._t('right'))
            return
        a, b = key
        self.r_title.configure(text="%s  \u2194  %s" % (a, b))
        self.r_sub.configure(text="%d messages  ·  stored in the database" % len(msgs))
        for m in msgs:
            outgoing = (m.get('sender') == b)
            status = "%s  %s" % (m.get('time', ''), self._ticks(m)) if outgoing \
                else m.get('time', '')
            self._bubble(self.r_inner, m.get('text', ''), m.get('sender', ''),
                         status, outgoing, msg=m)
        tk.Frame(self.r_inner, height=18, bg=self._t('right')).pack()
        self._refresh_recipients()

    def _right_groups(self):
        gid = self.sel_group
        g = groups.get(gid) if gid else None
        if not g:
            self.sel_group = None
            self.r_title.configure(text="Group log")
            self.r_sub.configure(text="pick a group from the list")
            self._empty(self.r_inner, ic('group'), "Select a group",
                        "Members and the full group history will appear here",
                        bg=self._t('right'))
            return
        self.r_title.configure(text=g['name'])
        self.r_sub.configure(text="created by %s  ·  %d members"
                                  % (g['creator'], len(g['members'])))
        mem = tk.Frame(self.r_inner, bg=self._t('right'))
        mem.pack(fill=tk.X, padx=18, pady=(16, 8))
        for m in g['members']:
            self._pill(mem, m).pack(side=tk.LEFT, padx=(0, 6), pady=3)
        msgs = group_messages.get(gid, [])
        if not msgs:
            tk.Label(self.r_inner, text="No messages in this group yet.",
                     bg=self._t('right'), fg=self._t('dim'),
                     font=("Segoe UI", 9)).pack(anchor='w', padx=18, pady=12)
        for m in msgs:
            self._bubble(self.r_inner, m.get('text', ''), m.get('sender', ''),
                         m.get('time', ''), False, msg=m)
        tk.Frame(self.r_inner, height=18, bg=self._t('right')).pack()
        self._refresh_recipients()

    def _right_activity(self):
        rows = list(activity_log)
        idx = self.sel_act
        if idx is None or not (0 <= idx < len(rows)):
            self.r_title.configure(text="Activity")
            self.r_sub.configure(text="every client-side change, live")
            counts = collections.Counter(r['kind'] for r in activity_log)
            self._card("By type", [(k, v) for k, v in counts.most_common()]
                       or [('-', 'nothing yet')], icon=ic('activity'))
            actors = collections.Counter(r['actor'] for r in activity_log)
            self._card("By client", [(k, "%d changes" % v) for k, v in actors.most_common(12)]
                       or [('-', 'nothing yet')], icon=ic('clients'))
            self._card("Latest", [(r['ts'], r['summary'])
                                  for r in rows[::-1][:12]] or [('-', 'nothing yet')],
                       icon=ic('log'))
            return
        it = rows[idx]
        self.r_title.configure(text="Change detail")
        self.r_sub.configure(text="%s  ·  %s" % (it['ts'], it['kind']))
        self._card("Event", [
            ('Time', it['ts']),
            ('Type', it['kind']),
            ('Client', it['actor']),
            ('What happened', it['summary']),
            ('Detail', it['detail'] or '-'),
        ], icon=ic('activity'))
        prev = [(r['ts'], r['summary']) for r in rows[:idx][::-1]
                if r['actor'] == it['actor']][:8]
        self._card("Earlier by %s" % it['actor'], prev or [('-', 'nothing before this')],
                   icon=ic('log'))
        tk.Frame(self.r_inner, height=16, bg=self._t('right')).pack()

    # ---------- hacker terminal ----------
    def _right_log(self):
        self.r_title.configure(text="Chat Log")
        self.r_sub.configure(text="live tail  ·  filter on the left")
        wrap = tk.Frame(self.r_inner, bg=TERM['bg'])
        wrap.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        bar = tk.Frame(wrap, bg=TERM['bar'])
        bar.pack(fill=tk.X)
        for i, col in enumerate(('#ff5f56', '#ffbd2e', '#27c93f')):
            d = tk.Canvas(bar, width=12, height=12, bg=TERM['bar'], highlightthickness=0)
            d.create_oval(2, 2, 11, 11, fill=col, outline='')
            d.pack(side=tk.LEFT, padx=(9 if i == 0 else 3, 0), pady=9)
        tk.Label(bar, text="   root@chat-server:~# tail -f activity.log",
                 bg=TERM['bar'], fg=TERM['dim'],
                 font=("Consolas", 9)).pack(side=tk.LEFT)
        self.term_count = tk.Label(bar, text="", bg=TERM['bar'], fg=TERM['fg'],
                                   font=("Consolas", 9, 'bold'))
        self.term_count.pack(side=tk.RIGHT, padx=12)
        body = tk.Frame(wrap, bg=TERM['bg'])
        body.pack(fill=tk.BOTH, expand=True)
        self.term = tk.Text(body, bg=TERM['bg'], fg=TERM['fg'], bd=0, relief=tk.FLAT,
                            font=("Consolas", 9), wrap='word', padx=12, pady=10,
                            insertbackground=TERM['fg'], height=26)
        self.term.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tsb = tk.Scrollbar(body, orient=tk.VERTICAL, command=self.term.yview)
        self.term.configure(yscrollcommand=tsb.set)
        tsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._term_tags()
        prompt = tk.Frame(wrap, bg=TERM['bg'])
        prompt.pack(fill=tk.X)
        self.prompt_lbl = tk.Label(prompt, text="root@chat-server:~# \u2588",
                                   bg=TERM['bg'], fg=TERM['fg'],
                                   font=("Consolas", 9))
        self.prompt_lbl.pack(anchor='w', padx=12, pady=(0, 9))
        self._term_redraw()
        self._blink()

    def _term_tags(self):
        for k, col in ACT_COLOR.items():
            self.term.tag_config(k, foreground=col)
        self.term.tag_config('ts', foreground=TERM['dim'])
        self.term.tag_config('actor', foreground=TERM['actor'])
        self.term.tag_config('msg', foreground=TERM['fg'])
        self.term.tag_config('detail', foreground=TERM['dim'])
        self.term.tag_config('arrow', foreground='#00a86b')

    def _passes_filter(self, item):
        return self.act_filter == 'all' or item.get('kind') == self.act_filter

    def _term_write(self, item):
        if self.term is None:
            return
        try:
            if not self.term.winfo_exists():
                return
            self.term.configure(state='normal')
            kind = str(item.get('kind', 'info'))
            self.term.insert(tk.END, "%s " % item.get('ts', ''), 'ts')
            self.term.insert(tk.END, "[%-8s]" % kind[:8], kind if kind in ACT_COLOR else 'msg')
            self.term.insert(tk.END, " %s" % item.get('actor', ''), 'actor')
            self.term.insert(tk.END, "  %s" % item.get('summary', ''), 'msg')
            if item.get('detail'):
                self.term.insert(tk.END, "\n          \u2514\u2500 ", 'arrow')
                self.term.insert(tk.END, str(item['detail']), 'detail')
            self.term.insert(tk.END, "\n")
            self.term.see(tk.END)
            self.term.configure(state='disabled')
        except Exception:
            pass

    def _term_redraw(self):
        if self.term is None:
            return
        try:
            self.term.configure(state='normal')
            self.term.delete('1.0', tk.END)
            self.term.configure(state='disabled')
        except Exception:
            return
        n = 0
        for item in self.term_lines:
            if self._passes_filter(item):
                self._term_write(item)
                n += 1
        self._update_term_count(n)

    def _update_term_count(self, n=None):
        if getattr(self, 'term_count', None) is None:
            return
        try:
            if n is None:
                n = sum(1 for i in self.term_lines if self._passes_filter(i))
            self.term_count.configure(text="%d lines" % n)
        except Exception:
            pass

    def _blink(self):
        lbl = getattr(self, 'prompt_lbl', None)
        if lbl is None:
            return
        try:
            if not lbl.winfo_exists():
                return
        except Exception:
            return
        try:
            cur = lbl.cget('text')
            lbl.configure(text="root@chat-server:~#" if cur.endswith('\u2588')
                          else "root@chat-server:~# \u2588")
        except Exception:
            return
        self.root.after(620, self._blink)

    # ---------- settings ----------
    def _right_settings(self):
        self.r_title.configure(text="Server Settings")
        self.r_sub.configure(text="theme, limits & data")

        card = RoundPanel(self.r_inner, radius=12, bg=self._t('card'),
                          parent_bg=self._t('right'))
        card.pack(fill=tk.X, padx=18, pady=(18, 10))
        tk.Label(card, text="Appearance", bg=self._t('card'), fg=self._t('text'),
                 font=("Segoe UI", 11, 'bold')).pack(anchor='w', padx=14, pady=(12, 8))
        seg = tk.Frame(card, bg=self._t('card'))
        seg.pack(anchor='w', padx=14, pady=(0, 14))
        for name, label in (('dark', 'Dark'), ('light', 'Light')):
            self._pill(seg, label, active=(self.theme.name == name),
                       on_click=lambda n=name: self.apply_theme(n)).pack(side=tk.LEFT,
                                                                        padx=(0, 8))

        card2 = RoundPanel(self.r_inner, radius=12, bg=self._t('card'),
                           parent_bg=self._t('right'))
        card2.pack(fill=tk.X, padx=18, pady=(0, 10))
        tk.Label(card2, text="Limits", bg=self._t('card'), fg=self._t('text'),
                 font=("Segoe UI", 11, 'bold')).pack(anchor='w', padx=14, pady=(12, 8))
        lrow = tk.Frame(card2, bg=self._t('card'))
        lrow.pack(anchor='w', padx=14, pady=(0, 14))
        tk.Label(lrow, text="Max clients", bg=self._t('card'), fg=self._t('sub'),
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 10))
        self.max_spin = tk.Spinbox(lrow, from_=1, to=200, width=6,
                                   font=("Segoe UI", 10), bg=self._t('input'),
                                   fg=self._t('text'), bd=0, relief=tk.FLAT,
                                   buttonbackground=self._t('input'),
                                   insertbackground=self._t('text'))
        self.max_spin.delete(0, 'end')
        self.max_spin.insert(0, str(MAX_CLIENTS))
        self.max_spin.pack(side=tk.LEFT, padx=(0, 12))
        self._pill(lrow, "Save", active=True, on_click=self.save_server_settings).pack(
            side=tk.LEFT)

        card3 = RoundPanel(self.r_inner, radius=12, bg=self._t('card'),
                           parent_bg=self._t('right'))
        card3.pack(fill=tk.X, padx=18, pady=(0, 10))
        tk.Label(card3, text="Data", bg=self._t('card'), fg=self._t('text'),
                 font=("Segoe UI", 11, 'bold')).pack(anchor='w', padx=14, pady=(12, 6))
        for k, v in (('Database', self._db_info()),
                     ('Messages', "%d stored" % sum(len(m) for m in conversations.values())),
                     ('Activity rows', len(activity_log))):
            r = tk.Frame(card3, bg=self._t('card'))
            r.pack(fill=tk.X, padx=14, pady=3)
            tk.Label(r, text=k, bg=self._t('card'), fg=self._t('sub'),
                     font=("Segoe UI", 9), width=15, anchor='w').pack(side=tk.LEFT)
            tk.Label(r, text=str(v), bg=self._t('card'), fg=self._t('text'),
                     font=("Segoe UI", 9), anchor='w').pack(side=tk.LEFT)
        arow = tk.Frame(card3, bg=self._t('card'))
        arow.pack(anchor='w', padx=14, pady=(12, 8))
        self._pill(arow, "Clear activity log", on_click=self.clear_log).pack(side=tk.LEFT,
                                                                            padx=(0, 8))
        self._pill(arow, "Reload from DB", on_click=self.reload_db).pack(side=tk.LEFT)
        drow = tk.Frame(card3, bg=self._t('card'))
        drow.pack(anchor='w', padx=14, pady=(0, 14))
        self._pill(drow, "Clear database", on_click=self.delete_database,
                   bg=self._t('bad'), fg='white').pack(side=tk.LEFT)
        tk.Frame(self.r_inner, height=16, bg=self._t('right')).pack()

    def _db_info(self):
        try:
            sz = os.path.getsize(DB_PATH)
            return "%s  (%.0f KB)" % (os.path.basename(DB_PATH), sz / 1024.0)
        except Exception:
            return os.path.basename(DB_PATH)

    def apply_theme(self, name):
        self.theme.set_theme(name)
        for w in list(self.root.winfo_children()):
            w.destroy()
        self._fonts.clear()
        self.setup_ui()
        self.log("Server theme set to %s" % self.theme.name, kind='server')

    def save_server_settings(self):
        global MAX_CLIENTS
        try:
            val = int(self.max_spin.get())
            MAX_CLIENTS = set_max_clients(val)
        except Exception:
            self.show_toast("Max clients must be a number", 'warn')
            return
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)
        # push the new limit to every connected client right away
        socketio.emit('server_config', {'max_clients': MAX_CLIENTS, 'port': PORT,
                                        'server_name': 'Server'})
        record_activity('server', 'Server',
                        "Server limit changed to %d clients" % MAX_CLIENTS,
                        "broadcast to all clients")
        self.log("Max clients set to %d (pushed to clients)" % MAX_CLIENTS, kind='server')
        self.show_toast("Settings saved")

    def reload_db(self):
        conversations.clear()
        groups.clear()
        group_messages.clear()
        user_settings.clear()
        try:
            servers.clear()
        except Exception:
            pass
        activity_log.clear()
        db_load()
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)
        self.show_toast("Reloaded from database")
        self.log("Reloaded caches from %s" % os.path.basename(DB_PATH), kind='server')

    def clear_log(self):
        """Wipe the audit trail: in-memory feed, the terminal and the DB table."""
        try:
            activity_log.clear()
        except Exception:
            pass
        try:
            self.term_lines.clear()
        except Exception:
            pass
        try:
            db_exec("DELETE FROM activity")
        except Exception:
            pass
        self.sel_act = None
        self.act_filter = 'all'
        self._mid_sig = None
        self._right_sig = None
        try:
            self._term_sig = None
        except Exception:
            pass
        self._render_middle(force=True)
        self._render_right(force=True)
        self.show_toast("Activity log cleared")

    def delete_database(self):
        """Danger zone: wipe the ENTIRE database (users, chats, groups, ...)."""
        try:
            ok = messagebox.askyesno(
                "Clear database",
                "Clear the ENTIRE database?\n\n"
                "Every user, contact, chat, group, message, call log and the "
                "activity trail will be permanently erased.\n\n"
                "This cannot be undone. Continue?",
                icon='warning', default='no')
        except Exception:
            ok = True
        if not ok:
            return
        warnings = 0
        # 1) wipe every table
        for t in ('users', 'contacts', 'blocked', 'messages', 'groups',
                  'group_members', 'activity', 'call_log'):
            try:
                db_exec("DELETE FROM %s" % t)
            except Exception:
                warnings += 1
        try:
            db_exec("DELETE FROM sqlite_sequence")
        except Exception:
            pass
        # 2) drop the file itself and rebuild an empty schema
        try:
            for suffix in ('', '-wal', '-shm'):
                p = DB_PATH + suffix
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            db_init()
        except Exception:
            warnings += 1
        # 3) forget everything cached in memory
        conversations.clear()
        groups.clear()
        group_messages.clear()
        user_settings.clear()
        try:
            servers.clear()
        except Exception:
            pass
        for store in (call_history, activity_log, self.term_lines):
            try:
                store.clear()
            except Exception:
                pass
        self.sel_client = self.sel_chat = self.sel_group = self.sel_act = None
        self.act_filter = 'all'
        self.compose_target = None
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)
        try:
            self._refresh_recipients()
        except Exception:
            pass
        self.show_toast("Database deleted" if not warnings
                        else "Database deleted (%d warning)" % warnings,
                        'bad' if not warnings else 'warn')
        self.log("ENTIRE database deleted", kind='warn')

    # ============================================================
    #  SELECTION
    # ============================================================
    def _pick_client(self, sid):
        self.sel_client = sid
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)
        if sid in connected_clients:
            self.compose_target = sid
            self._refresh_recipients()
            self._set_recipient(
                ("%s (direct)" % connected_clients[sid]['username'])[:26])
            self._update_compose_placeholder()

    def _pick_chat(self, key):
        self.sel_chat = key
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)
        if key:
            a, b = key
            for name in (b, a):
                for sid, c in connected_clients.items():
                    if c['username'] == name:
                        self.compose_target = sid
                        self._refresh_recipients()
                        self._set_recipient(("%s (direct)" % name)[:26])
                        self._update_compose_placeholder()
                        return

    def _pick_group(self, gid):
        self.sel_group = gid
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)

    def _pick_activity(self, idx):
        self.sel_act = idx
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)

    def _set_filter(self, key):
        self.act_filter = key
        self._mid_sig = None
        self._right_sig = None
        self._render_middle(force=True)
        self._render_right(force=True)

    # ============================================================
    #  COMPOSE  (broadcast to all  OR  message one client)
    # ============================================================
    def _refresh_recipients(self):
        if not hasattr(self, 'recipient_menu'):
            return
        m = self.recipient_menu
        m.delete(0, 'end')
        m.add_command(label="All clients (broadcast)",
                      command=lambda: self._set_target(None, "All clients (broadcast)"))
        m.add_separator()
        if not connected_clients:
            m.add_command(label="(no clients online)", state='disabled')
        for sid, c in sorted(connected_clients.items(), key=lambda x: x[1]['username']):
            label = "%s   %s" % (c['username'], c.get('ip', ''))
            m.add_command(label=label, command=lambda s=sid, n=c['username']:
                          self._set_target(s, ("%s (direct)" % n)[:26]))
        if self.compose_target not in connected_clients:
            self.compose_target = None
            self._set_recipient("All clients (broadcast)")
        self._update_compose_placeholder()

    def _set_recipient(self, label):
        try:
            self.recipient_btn.set_text("%s  \u25be" % label)
        except Exception:
            pass

    def _update_compose_placeholder(self):
        """'Broadcast' when messaging everyone, 'Send Message' for one client."""
        try:
            if self.compose_target:
                name = connected_clients.get(self.compose_target, {}).get(
                    'username', 'client')
                self.compose_e.set_placeholder("Send Message")
                self.compose_hint.configure(
                    text="Type a message for %s and press Enter" % name)
            else:
                self.compose_e.set_placeholder("Broadcast")
                self.compose_hint.configure(
                    text="Broadcast to all connected clients")
        except Exception:
            pass

    def _open_recipient_menu(self):
        """Open the recipient picker just below the (rounded) selector."""
        self._refresh_recipients()
        try:
            x = self.recipient_btn.winfo_rootx()
            y = self.recipient_btn.winfo_rooty() + self.recipient_btn.winfo_height() + 2
            self.recipient_menu.tk_popup(x, y)
        except Exception:
            pass
        finally:
            try:
                self.recipient_menu.grab_release()
            except Exception:
                pass

    def _set_target(self, sid, label):
        self.compose_target = sid
        self._set_recipient(label)
        self._update_compose_placeholder()
        self.compose_e.focus_set()

    def _focus_compose(self, sid):
        name = connected_clients.get(sid, {}).get('username', 'client')
        self._set_target(sid, ("%s (direct)" % name)[:26])

    def _server_chat_send(self, sid, text):
        """Deliver a dashboard message as a REAL chat message from 'Server'.

        The client sees it in Chats under the contact "Server" (with unread
        badge, notification + ringtone), exactly like a client-to-client ping.
        """
        c = connected_clients.get(sid)
        if not c:
            return None
        name = c['username']
        now = datetime.now().strftime("%H:%M")
        mid = uuid.uuid4().hex[:12]
        # stored shape: sender=Server, peer=<client>  ->  conv_key('Server', name)
        msg = {'mid': mid, 'text': text, 'sender': 'Server', 'peer': name,
               'time': now, 'status': 'delivered'}
        conversations.setdefault(conv_key('Server', name), []).append(msg)
        db_add_message(msg)
        db_upsert_contact(name, 'Server', 'single', text, unread_inc=True,
                          color='#00806a')
        incoming = dict(msg)
        incoming['type'] = 'received'
        incoming['peer'] = 'Server'          # the client's view: it comes from the server
        incoming['from_sid'] = None
        incoming['from_ip'] = 'server'
        incoming['from_avatar'] = ''
        socketio.emit('new_message', incoming, to=sid)
        return msg

    def send_compose(self):
        msg = self.compose_e.get().strip()
        if not msg:
            self._hint("Type a message first")
            return
        if self.compose_target is None:
            sent = 0
            for sid in list(connected_clients.keys()):
                if self._server_chat_send(sid, msg):
                    sent += 1
            record_activity('server', 'Server',
                            "Server broadcast to all clients",
                            "[%d clients] %s" % (sent, msg[:110]))
            self.log("Broadcast to all (%d clients): %s" % (sent, msg), kind='server')
            self._hint("Broadcast delivered to %d client(s)" % sent)
            self.show_toast("Broadcast sent to %d" % sent)
        else:
            sid = self.compose_target
            c = connected_clients.get(sid)
            if not c:
                self._hint("That client went offline")
                self._refresh_recipients()
                return
            if self._server_chat_send(sid, msg) is None:
                self._hint("Could not reach that client")
                return
            record_activity('server', 'Server',
                            "Server \u2192 %s" % c['username'],
                            msg[:120])
            self.log("Direct message to %s: %s" % (c['username'], msg), kind='server')
            self._hint("Sent to %s" % c['username'])
            self.show_toast("Sent to %s" % c['username'])
        self.compose_e.delete(0, tk.END)
        self._mid_sig = None
        self._render_middle()

    # legacy hook kept for compatibility
    def broadcast(self):
        self.compose_target = None
        self._set_recipient("All clients (broadcast)")
        self._update_compose_placeholder()
        self.send_compose()

    def _hint(self, text):
        self.compose_hint.configure(text=text)

    # ============================================================
    #  ACTIVITY STREAM
    # ============================================================
    def push_activity(self, item):
        self.term_lines.append(item)
        try:
            if self.current_view == 'log' and self.term is not None and self.term.winfo_exists():
                if self._passes_filter(item):
                    self._term_write(item)
                self._update_term_count()
            elif self.current_view in ('activity', 'clients'):
                self._mid_sig = None
                self._right_sig = None
                self._render_middle()
                self._render_right()
        except Exception:
            pass
        try:
            self.count_lbl.configure(text="%d/%d" % (len(connected_clients), MAX_CLIENTS))
            self.event_lbl.configure(text="%d events" % len(activity_log))
        except Exception:
            pass

    def log(self, text, kind='info', detail=''):
        item = {'ts': datetime.now().strftime("%H:%M:%S"), 'kind': kind,
                'actor': 'server', 'summary': text, 'detail': detail}
        try:
            self.root.after(0, lambda it=item: self.push_activity(it))
        except Exception:
            pass

    # ============================================================
    #  SERVER BOOT / POLL
    # ============================================================
    def start_server(self):
        self.is_running = True
        self.server_thread = threading.Thread(target=self.run_flask, daemon=True)
        self.server_thread.start()
        self.log("Server listening on 0.0.0.0:%d" % PORT, kind='join')
        self.log("Database ready: %s" % self._db_info(), kind='info')
        self.log("Max clients: %d" % MAX_CLIENTS, kind='info')
        for ip in (getattr(self, 'lan_ips', None) or []):
            self.log("LAN address: %s:%d" % (ip, PORT), kind='info')
        self.root.after(1200, lambda: self._set_dot(self._t('ok')))
        self.poll_clients()
        self.start_ticker()

    def start_ticker(self):
        """Start the animation / live-value loop (exactly once)."""
        if getattr(self, '_ticking', False):
            return
        self._ticking = True
        self.root.after(100, self._tick)

    def _set_dot(self, color):
        """Colour the rail's live dot (green = serving, amber = booting)."""
        try:
            self._set_dot_color(self._dot_entry, color)
        except Exception:
            try:
                self.status_dot.itemconfigure(self._dot, fill=color)
            except Exception:
                pass

    def poll_clients(self):
        try:
            self._render_middle()
            self._render_right()
        except Exception:
            pass
        self.root.after(2000, self.poll_clients)

    def run_flask(self):
        # async_mode='threading' + Werkzeug: `threaded=True` is set by
        # Flask-SocketIO, so each client gets its own thread and 10+ clients
        # can sit on the server at once.  allow_unsafe_werkzeug silences the
        # refusal when the server is launched without a console (double-click).
        socketio.run(app, host='0.0.0.0', port=PORT, debug=False,
                     use_reloader=False, allow_unsafe_werkzeug=True,
                     log_output=False)

    def show_toast(self, text, kind='ok'):
        col = {'ok': self._t('accent'), 'warn': self._t('warn'),
               'bad': self._t('bad')}.get(kind, self._t('accent'))
        t = tk.Frame(self.root, bg=col)
        tk.Label(t, text=text, bg=col, fg='white', font=("Segoe UI", 9, 'bold'),
                 padx=18, pady=10).pack()
        t.place(relx=1.0, rely=0.0, x=-20, y=20, anchor='ne')
        self.root.after(2600, t.destroy)

    def on_closing(self):
        self.root.destroy()

__all__ = [
    "GlyphButton",
    "PALETTES",
    "RoundButton",
    "RoundPanel",
    "RoundedEntry",
    "ServerApp",
    "TERM",
    "ThemeManager",
    "VIEWS",
    "VIEW_META",
    "_rr",
]
