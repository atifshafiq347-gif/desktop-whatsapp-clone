# client_menus.py — Context menus, add-client dialog, blocked view, diagnostics.
from client_core import *


class MenuMixin:

    def block_user(self, name):
        if not name:
            return
        self.blocked.add(name)
        self.blocked_meta = [b for b in self.blocked_meta
                             if b.get('peer') != name]
        self.blocked_meta.append({
            'peer': name,
            'blocked_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        try:
            sio.emit('block_user', {'me': self.my_username, 'peer': name})
        except Exception:
            pass
        self.refresh_middle_list()
        # blocking the person whose chat is open must leave an empty pane
        # behind, not their conversation still sitting in the right panel
        if getattr(self, 'current_chat_name', '') == name:
            try:
                self._close_open_chat()
                self._cancel_reply()
                self._discard_file_preview()
            except Exception:
                pass
        self._save_ui_state()
        self.show_toast("Blocked %s" % name)
        if getattr(self, 'current_view', 'chats') == 'blocked':
            self.show_blocked_inline()

    def unblock_user(self, name):
        self.blocked.discard(name)
        self.blocked_meta = [b for b in self.blocked_meta
                             if b.get('peer') != name]
        try:
            sio.emit('unblock_user', {'me': self.my_username, 'peer': name})
        except Exception:
            pass
        if getattr(self, 'current_view', 'chats') == 'chats':
            self.refresh_middle_list()
        else:
            self.show_blocked_inline()
        self._save_ui_state()
        self.show_toast("Unblocked %s" % name)

    def toggle_block(self, u):
        name = u.get('name')
        if not name:
            return
        if name in getattr(self, 'blocked', set()):
            self.unblock_user(name)
        else:
            self.block_user(name)

    def show_blocked(self):
        """The dedicated 'Blocked clients' view (list + detail)."""
        self.current_view = 'blocked'
        for b, v in getattr(self, 'nav_btns', []):
            b.set_active(False)
        try:
            self.block_btn.set_active(True)
        except Exception:
            pass
        try:
            self.mid_title.configure(text="Blocked")
        except Exception:
            pass
        # make sure the filter row (which holds the button) is visible
        try:
            self.filter_frame.pack(fill=tk.X, padx=12, pady=(0, 6),
                                   before=self.chat_list_frame)
            self.search_f.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True,
                               padx=(10, 0), pady=6)
        except Exception:
            pass
        self.show_blocked_inline()

    def show_blocked_inline(self):
        for w in self.cii.winfo_children():
            w.destroy()
        blocked = list(getattr(self, 'blocked_meta', []) or [])
        if not blocked:
            tk.Label(self.cii, text="\u26d4", bg='#1e1e1e', fg='#2c2c2c',
                     font=(self.icon_family, 46)).pack(pady=(70, 10))
            tk.Label(self.cii, text="No blocked clients", bg='#1e1e1e',
                     fg='#e9edef', font=("Segoe UI", 14, "bold")).pack()
            tk.Label(self.cii, text="Right-click any chat \u2192 Block client",
                     bg='#1e1e1e', fg='#8696a0',
                     font=("Segoe UI", 11)).pack(pady=(4, 0))
        else:
            tk.Label(self.cii, text="Blocked clients (%d)" % len(blocked),
                     bg='#1e1e1e', fg='#8696a0',
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(
                fill=tk.X, padx=14, pady=(10, 4))
            for b in blocked:
                self.blocked_item(b)
        self._bind_mousewheel_recursive(self.cii, self.ccv)
        self._theme_subtree(self.cii)
        self._queue_scrollregion(self.ccv)

    def blocked_item(self, b):
        """One row in the Blocked view: avatar + name + when + Unblock."""
        name = b.get('peer') or ''
        fr = tk.Frame(self.cii, bg='#1e1e1e')
        fr.pack(fill=tk.X, padx=4, pady=1)
        av = tk.Canvas(fr, width=44, height=44, bg='#1e1e1e',
                       highlightthickness=0, bd=0, cursor="hand2")
        av.pack(side=tk.LEFT, padx=(8, 10), pady=6)
        self._draw_avatar(av, 44, 14, name, '#2c2c2c', self._peer_pic(name))

        inf = tk.Frame(fr, bg='#1e1e1e', cursor="hand2")
        inf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        tk.Label(inf, text=name, bg='#1e1e1e', fg='#e9edef',
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(fill=tk.X)
        when = (b.get('blocked_at') or '')[:16]
        tk.Label(inf, text=("Blocked  " + when) if when else "Blocked",
                 bg='#1e1e1e', fg='#8696a0', font=("Segoe UI", 10),
                 anchor="w").pack(fill=tk.X)

        btn = RoundedButton(fr, text="Unblock",
                            command=lambda n=name: self.unblock_user(n),
                            font=("Segoe UI", 10, "bold"),
                            parent_bg='#1e1e1e', width=78, height=30,
                            radius=9, active_bg='#e53935',
                            active_fg='white', inactive_bg='#2c2c2c',
                            inactive_fg='#e9edef')
        btn.set_active(True)
        btn.pack(side=tk.RIGHT, padx=10)

        # clicking the row (not the button) opens the detail view
        detail = lambda e, n=name: self.show_blocked_detail(n)
        av.bind("<Button-1>", detail)
        self._bind_click_recursive(inf, detail)

    def show_blocked_detail(self, name):
        ip = ''
        for c in getattr(self, 'clients', []) or []:
            if c.get('username') == name:
                ip = c.get('ip') or ''
                break
        when = ''
        for b in getattr(self, 'blocked_meta', []):
            if b.get('peer') == name:
                when = b.get('blocked_at') or ''
                break
        self._simple_window("Blocked client \u2022 %s" % name, [
            "Client      : %s" % name,
            "Status      : Blocked",
            "IP address  : %s" % (ip or 'unknown / offline'),
            "Blocked on  : %s" % (when or '-'),
            "",
            "A blocked client cannot send you messages,",
            "call you or see your online status.",
            "",
            "Use the red 'Unblock' button in the list to allow them again.",
        ])

    def diagnostics(self):
        lines = [
            "UI running                 : PASS",
            "Server URL                 : %s" % self.server_url,
            "Socket connected           : %s" % ("YES" if getattr(sio, 'connected', False)
                                                 else "NO"),
            "Microphone (pyaudio)       : %s" % ("AVAILABLE" if PYAUDIO_OK
                                                 else "NOT INSTALLED"),
            "Camera (opencv+numpy)      : %s" % ("AVAILABLE" if CV2_OK
                                                 else "NOT INSTALLED - pip install opencv-python numpy"),
            "Pillow                     : %s" % ("AVAILABLE" if PIL_OK
                                                 else "NOT INSTALLED"),
            "winsound (inline audio)    : %s" % ("AVAILABLE" if winsound
                                                 else "NOT INSTALLED"),
            "Clients online             : %d" % len(getattr(self, 'clients', [])),
            "Open chat                  : %s" % (self.current_chat_name or "-"),
            "Messages in open chat      : %d" % len(getattr(self, '_current_msgs', [])),
        ]
        self._simple_window("Diagnostics", lines)

    def add_client(self):
        """Popup: add ANOTHER CLIENT by IP, using the profile name that client set.

        If the IPv4 is valid and matches a connected client it is added to the
        middle chat list; otherwise an 'unavailable' error is shown IN the window.
        """
        cur = ""
        try:
            cur = self.server_url.replace("http://", "").split(":")[0]
        except Exception:
            cur = ""

        dlg = tk.Toplevel(self.root)
        dlg.title("Add Client")
        dlg.configure(bg="#121212")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        w, h = 440, 455
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - w) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dlg, text="Add Client", bg="#121212", fg="#e9edef",
                 font=("Segoe UI", 15, "bold")).pack(pady=(16, 2))

        tk.Label(dlg, text="This client (your IPv4)", bg="#121212", fg="#8696a0",
                 font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=26, pady=(8, 2))
        tk.Label(dlg, text=self._local_ipv4(), bg="#1e1e1e", fg="#25d366",
                 font=("Consolas", 12), anchor="w").pack(fill=tk.X, padx=26, ipady=5)

        # currently connected clients, so you know which IP to type
        tk.Label(dlg, text="Connected clients (IP  \u2192  profile name)", bg="#121212",
                 fg="#8696a0", font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=26, pady=(10, 2))
        avail = tk.Text(dlg, height=3, bg="#1e1e1e", fg="#e9edef", bd=0,
                        relief=tk.FLAT, highlightthickness=0,
                        font=("Consolas", 10), wrap=tk.NONE)
        avail.pack(fill=tk.X, padx=26)
        lines = []
        for c in sorted(self._peer_candidates(),
                        key=lambda x: (x.get('ip') or '', x.get('username') or '')):
            lines.append(f"{c.get('ip', '?')}  \u2192  {c.get('username', '?')}")
        avail.insert("1.0", "\n".join(lines) if lines else "no other clients connected yet")
        avail.configure(state='disabled')

        tk.Label(dlg, text="Client IPv4 address", bg="#121212", fg="#8696a0",
                 font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=26, pady=(10, 2))
        entry = tk.Entry(dlg, bg="#1e1e1e", fg="white", insertbackground="#25d366",
                         relief=tk.FLAT, bd=0, font=("Consolas", 12), justify="center")
        entry.pack(fill=tk.X, padx=26, ipady=6)
        entry.insert(0, cur)
        entry.focus_set()

        err = tk.Label(dlg, text="", bg="#121212", fg="#ff5c5c",
                       font=("Segoe UI", 10, "bold"), wraplength=380)
        err.pack(pady=(8, 0))

        def cancel():
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        def finish(ip):
            if not dlg.winfo_exists():
                return
            info = self._resolve_ip(ip)
            if info is None:
                err.configure(text=f"Client unavailable at {ip}", fg="#ff5c5c")
                return
            self._add_peer(ip, info)
            cancel()

        def submit(_=None):
            ip = entry.get().strip()
            if not valid_ipv4(ip):
                err.configure(text="Invalid IPv4 address", fg="#ff5c5c")
                return
            info = self._resolve_ip(ip)
            if info is not None:
                self._add_peer(ip, info)
                cancel()
                return
            err.configure(text="Checking client...", fg="#e9edef")
            if sio.connected:
                sio.emit('get_connected_clients')
            dlg.after(900, lambda: finish(ip))

        bf = tk.Frame(dlg, bg="#121212")
        bf.pack(pady=14)
        tk.Button(bf, text="Add", command=submit, bg="#25d366", fg="#0b1a0e",
                  font=("Segoe UI", 11, "bold"), bd=0, relief=tk.FLAT,
                  cursor="hand2", width=10).pack(side=tk.LEFT, padx=8)
        tk.Button(bf, text="Cancel", command=cancel, bg="#2c2c2c", fg="white",
                  font=("Segoe UI", 11, "bold"), bd=0, relief=tk.FLAT,
                  cursor="hand2", width=10).pack(side=tk.LEFT, padx=8)
        dlg.bind("<Return>", submit)
        dlg.bind("<Escape>", lambda e: cancel())
        self._theme_subtree(dlg)

    def _add_peer(self, ip, info, silent=False):
        """Add the client at `ip` to the middle list using its own profile name."""
        name = info.get('username') or ip
        sid = info.get('sid')
        peers = getattr(self, '_peers', [])
        for u in peers:
            if (sid and u.get('sid') == sid) or u.get('name') == name:
                u['sid'] = sid or u.get('sid')
                u['status'] = 'active'
                self.refresh_middle_list()
                if not silent:
                    self.show_toast(f"{name} is already in your list")
                return
        nid = max([u.get('id', 0) for u in peers] + [0]) + 1
        palette = ['#0b6e4f', '#1f6feb', '#8957e5', '#bf4b8a',
                   '#e3b341', '#2da44e', '#cf222e', '#0e7490']
        u = {
            'id': nid, 'name': name, 'sid': sid, 'avatar': self._initials(name),
            'pic': info.get('avatar', '') or '',
            'color': palette[nid % len(palette)], 'status': 'active',
            'lastMsg': 'Tap to start chatting',
            'time': datetime.now().strftime("%H:%M"),
            'unread': 0, 'type': 'single',
            'pinned': False, 'pin_ts': 0, '_act': datetime.now().timestamp(),
        }
        peers.append(u)
        self._peers = peers
        if self.current_view != 'chats':
            self.switch_view('chats')
        else:
            self.refresh_middle_list()
        if not silent:
            self.show_toast(f"Added {name} ({ip})")
            self.notify("Client added", f"{name}  ({ip})", kind='client')
        self._save_ui_state()

    def add_menu(self):
        """Small chooser: private chat with a client OR create a group."""
        dlg = tk.Toplevel(self.root)
        dlg.title("New")
        dlg.configure(bg="#121212")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        w, h = 380, 230
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - w) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dlg, text="Start something new", bg="#121212", fg="#e9edef",
                 font=("Segoe UI", 14, "bold")).pack(pady=(18, 12))

        def close(cmd):
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()
            cmd()

        def opt(icon, title, subtitle, cmd):
            fr = tk.Frame(dlg, bg="#1e1e1e", cursor="hand2")
            fr.pack(fill=tk.X, padx=20, pady=6)
            cv = tk.Canvas(fr, width=40, height=40, bg="#1e1e1e",
                           highlightthickness=0, bd=0)
            cv.pack(side=tk.LEFT, padx=10, pady=8)
            self._round_rect(cv, 0, 0, 40, 40, 12, "#25d366")
            cv.create_text(20, 20, text=icon, fill="white", font=(self.icon_family, 16))
            info = tk.Frame(fr, bg="#1e1e1e")
            info.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=8)
            tk.Label(info, text=title, bg="#1e1e1e", fg="#e9edef",
                     font=("Segoe UI", 12, "bold"), anchor="w").pack(fill=tk.X)
            tk.Label(info, text=subtitle, bg="#1e1e1e", fg="#8696a0",
                     font=("Segoe UI", 9), anchor="w").pack(fill=tk.X)
            self._bind_click_recursive(fr, lambda e: close(cmd))
            self._bind_hover_recursive(fr, fr, "#1e1e1e", "#2c2c2c")

        opt(ICON.get("person", "\u25cf"), "Private chat with a client",
            "Add by IPv4 and chat one-to-one", self.add_client)
        opt(ICON.get("group", "\u25a6"), "Create a group",
            "Name it and pick clients to add", self.create_group)
        dlg.bind("<Escape>", lambda e: close(lambda: None))
        self._theme_subtree(dlg)

    def haction(self, a):
        if a == "Search":
            self.toggle_chat_search()
        elif a in ("Video Call", "Voice Call"):
            if self._is_server_chat():
                self.show_toast("Server ko call nahi kar sakte")
                return
            self.start_call('video' if a == "Video Call" else 'voice')
        elif a == "More":
            self._more_menu()
        else:
            self.show_toast(f"{a} feature (demo)")

    def _more_menu(self):
        """The chat header 'More' (⋮) menu."""
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Group info", command=self._group_info)
        m.add_command(label="Shared media", command=self.group_media)
        m.add_command(label="Search in chat", command=self.toggle_chat_search)
        m.add_separator()
        m.add_command(label="History filter", command=self.history_filter_menu)
        m.add_command(label="Export chat", command=self.export_chat)
        muted = self.current_chat_id in self.muted_chats
        m.add_command(label="Unmute notifications" if muted else "Mute notifications",
                      command=self.toggle_mute_chat)
        m.add_separator()
        m.add_command(label="Clear chat",
                      command=lambda: self._menu_do(self.clear_current_chat))
        m.add_command(label="Diagnostics", command=self.diagnostics)
        m.add_command(label="Settings", command=self.show_settings_inline)
        m.add_separator()
        m.add_command(label="Delete all chats",
                      command=lambda: self._menu_do(self.clear_all_chats))
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            try:
                m.grab_release()
            except Exception:
                pass

    # ---- delete every chat (More menu) ----
    def clear_all_chats(self):
        """Ask once, then wipe the whole chat list + every history."""
        if not getattr(self, '_peers', []):
            self.show_toast("No chats to delete")
            return
        n = len([p for p in self._peers if not (p.get('gid'))])
        ok = messagebox.askyesno(
            "Delete all chats",
            "Delete ALL chats and their messages?\n\n"
            "%d chat(s) will be removed from this device.\n"
            "This cannot be undone.\n\n"
            "(Group chats stay because they are shared.)" % max(1, n),
            icon='warning', parent=self.root)
        if not ok:
            return
        try:
            if sio.connected:
                sio.emit('clear_all_chats', {'me': self.my_username})
        except Exception:
            pass
        self._clear_pending = True
        self._wipe_chats()
        self.notify("Chats deleted", "All chats were removed", kind='info')
        try:
            self.root.after(2500, lambda: setattr(self, '_clear_pending', False))
        except Exception:
            self._clear_pending = False

    def _wipe_chats(self):
        """Drop the whole local chat list and any open conversation."""
        self._peers = []
        self._peer_seq = 0
        self._bubble_labels = {}
        self._bubble_widgets = {}
        self._bubble_rects = {}
        self.pinned = {}
        self.muted_chats = set()
        self._close_open_chat()
        self._cancel_reply()
        self._discard_file_preview()
        for w in self.mi.winfo_children():
            w.destroy()
        try:
            self.refresh_middle_list()
        except Exception:
            pass

    def clear_current_chat(self):
        """'Delete chat' from inside the open conversation (history only)."""
        if self.current_chat_id is None:
            self.show_toast("Open a chat first")
            return
        try:
            ok = messagebox.askyesno(
                "Clear chat",
                "Delete all messages in this chat?\n\n"
                "Only your copy is cleared - the other side keeps theirs.",
                icon='warning', parent=self.root)
        except Exception:
            ok = True
        if not ok:
            return
        peer = self.current_chat_name or ''
        gid = self.current_chat_gid if self.current_chat_type == 'group' else ''
        try:
            if sio.connected:
                sio.emit('clear_chat', {'me': self.my_username,
                                        'peer': peer, 'group': gid})
        except Exception:
            pass
        # clear immediately in the UI
        self._current_msgs = []
        for u in getattr(self, '_peers', []):
            if u.get('id') == self.current_chat_id:
                u['lastMsg'] = ''
                u['unread'] = 0
                break
        try:
            self.render_msgs({'messages': []})
        except Exception:
            pass
        self.show_toast("Chat cleared")

    def attach_file(self):
        """Pick any file and open its preview page INSIDE the right panel.

        The file is not sent yet: the preview shows the file's software logo,
        its name and size, and Enter (or the Send button) sends it.
        """
        path = filedialog.askopenfilename(title="Choose a file to send")
        if path:
            self._queue_file(path)

    def take_camera(self):
        self._attach_pick("Choose a photo / image",
                          [("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                           ("All files", "*.*")])

    def send_voice(self):
        self.start_recording()
