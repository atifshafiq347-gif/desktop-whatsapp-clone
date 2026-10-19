# client_settings.py — Settings tab: draft/apply behaviour, profile, ringtones, volume.
from client_core import *


class SettingsMixin:

    def choose_theme(self):
        """Radio button handler: remember the choice (applied only on Save)."""
        self._settings_dirty()

    def set_time_format(self):
        """Settings: remember the clock choice (applied only on Save)."""
        self._settings_dirty()

    def show_settings_inline(self):
        """Settings inside the same page (middle panel), not a new window"""
        for w in self.cii.winfo_children():
            w.destroy()

        # Every control below edits a *draft*: nothing is applied to the app
        # until the user presses "Save Settings".
        self._draft_pic = None
        self._settings_unsaved = False
        self._settings_building = True

        card = tk.Frame(self.cii, bg='#2c2c2c', bd=0, highlightbackground='#3c3c3c', highlightthickness=1)
        card.pack(fill=tk.X, padx=22, pady=22)

        hd = tk.Frame(card, bg='#2c2c2c')
        hd.pack(anchor="w", padx=18, pady=(14, 10))
        tk.Label(hd, text=ICON["settings"], bg='#2c2c2c', fg='#25d366',
                 font=(self.icon_family, 16)).pack(side=tk.LEFT)
        tk.Label(hd, text="Settings", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT, padx=(8, 0))

        # Profile section
        tk.Label(card, text="Profile", bg='#2c2c2c', fg='#8696a0', font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(6, 0))

        # Profile picture (dp) picker
        pf = tk.Frame(card, bg='#2c2c2c')
        pf.pack(fill=tk.X, padx=18, pady=(8, 4))
        self.set_av_cv = tk.Canvas(pf, width=72, height=72, bg='#2c2c2c',
                                   highlightthickness=0, bd=0)
        self.set_av_cv.pack(side=tk.LEFT)
        pbt = tk.Frame(pf, bg='#2c2c2c')
        pbt.pack(side=tk.LEFT, padx=(14, 0), fill=tk.X, expand=True)
        tk.Label(pbt, text="Profile Photo", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(pbt, text="PNG / JPG — chat mein dp ban jayegi", bg='#2c2c2c',
                 fg='#8696a0', font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))
        pbrow = tk.Frame(pbt, bg='#2c2c2c')
        pbrow.pack(anchor="w")
        up_btn = RoundedButton(pbrow, text="Upload Photo", icon=ICON["photo"],
                               icon_font=(self.icon_family, 12), command=self.choose_profile_pic,
                               font=("Segoe UI", 10), parent_bg='#2c2c2c',
                               width=132, height=32, radius=10,
                               active_bg='#25d366', active_fg='white')
        up_btn.set_active(True)
        up_btn.pack(side=tk.LEFT)
        rm_btn = RoundedButton(pbrow, text="Remove", command=self.remove_profile_pic,
                               font=("Segoe UI", 10), parent_bg='#2c2c2c',
                               width=84, height=32, radius=10,
                               active_bg='#2c2c2c', active_fg='white')
        rm_btn.set_active(True)
        rm_btn.pack(side=tk.LEFT, padx=(8, 0))
        self._render_settings_avatar()

        nf = tk.Frame(card, bg='#2c2c2c')
        nf.pack(fill=tk.X, padx=18, pady=6)
        tk.Label(nf, text="Name:", bg='#2c2c2c', fg='#e9edef', font=("Segoe UI", 11)).pack(side=tk.LEFT)
        self.pn = tk.StringVar(value=self.my_username)
        tk.Entry(nf, textvariable=self.pn, bg='#1e1e1e', fg='white', font=("Segoe UI", 11),
                 insertbackground='#25d366', relief=tk.FLAT, bd=0).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0), ipady=5)

        cf = tk.Frame(card, bg='#2c2c2c')
        cf.pack(fill=tk.X, padx=18, pady=6)
        tk.Label(cf, text="Avatar Color:", bg='#2c2c2c', fg='#e9edef', font=("Segoe UI", 11)).pack(side=tk.LEFT)
        self.pc = tk.StringVar(value=getattr(self, 'my_color', '#25d366'))
        self.color_btn = RoundedButton(cf, text="Choose Color", command=self.choose_color,
                                       font=("Segoe UI", 10), parent_bg='#2c2c2c',
                                       width=116, height=32, radius=10,
                                       active_bg='#25d366', active_fg='white')
        self.color_btn.set_active(True)
        self.color_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # ---- Notifications ----
        tk.Label(card, text="Notifications", bg='#2c2c2c', fg='#8696a0',
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(16, 0))

        # Ringtone picker (built-in tones + add your own)
        rl = tk.Frame(card, bg='#2c2c2c')
        rl.pack(fill=tk.X, padx=18, pady=(6, 0))
        tk.Label(rl, text="Notification Ringtone", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 11)).pack(side=tk.LEFT)
        tk.Label(rl, text=f"{len(self.ringtone.labels())} built-in + apni file",
                 bg='#2c2c2c', fg='#8696a0', font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        rr = tk.Frame(card, bg='#2c2c2c')
        rr.pack(fill=tk.X, padx=18, pady=(2, 0))
        self.rt_custom_path = getattr(self, 'custom_ringtone_path', "")
        self.rt_var = tk.StringVar(value=self.ringtone_label)
        rt_values = list(self.ringtone.labels())
        if self.rt_custom_path:
            rt_values.append("Custom: " + os.path.basename(self.rt_custom_path))
        rt_values += ["Custom…", "None"]
        rt_box = ttk.Combobox(rr, textvariable=self.rt_var, style='Dark.TCombobox',
                              values=rt_values, state="readonly",
                              font=("Segoe UI", 11))
        self.rt_box = rt_box
        rt_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        rt_box.bind("<<ComboboxSelected>>", self.on_ringtone_pick)
        play_btn = RoundedButton(rr, text="Play", icon=ICON["play"],
                                 icon_font=(self.icon_family, 11), command=self.preview_ringtone,
                                 font=("Segoe UI", 10), parent_bg='#2c2c2c',
                                 width=84, height=32, radius=10,
                                 active_bg='#25d366', active_fg='white')
        play_btn.set_active(True)
        play_btn.pack(side=tk.LEFT, padx=(8, 0))

        add_rt = RoundedButton(card, text="Add your own ringtone…", icon=ICON["music"],
                               icon_font=(self.icon_family, 12), command=self.choose_ringtone_file,
                               font=("Segoe UI", 10), parent_bg='#2c2c2c',
                               width=200, height=32, radius=10,
                               active_bg='#2c2c2c', active_fg='white')
        add_rt.set_active(True)
        add_rt.pack(anchor="w", padx=18, pady=(8, 0))

        # Ringtone volume (app-level, 100% by default)
        tk.Label(card, text="Ringtone Volume", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 11)).pack(anchor="w", padx=18, pady=(12, 0))
        rvr = tk.Frame(card, bg='#2c2c2c')
        rvr.pack(fill=tk.X, padx=18, pady=4)
        self.rt_vol_lbl = tk.Label(rvr, text=f"{self.ringtone.volume}%", bg='#2c2c2c',
                                   fg='#e9edef', font=("Segoe UI", 11, "bold"),
                                   width=5, anchor="e")
        self.rt_vol_lbl.pack(side=tk.RIGHT)
        self.rt_vol_scale = ModernScale(rvr, from_=0, to=100, value=self.ringtone.volume,
                                        command=self.on_ringtone_volume,
                                        bg='#2c2c2c', track='#3a3a3a', fill='#25d366',
                                        height=22)
        self.rt_vol_scale.set(self.ringtone.volume)
        self.rt_vol_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        # System (device) volume
        tk.Label(card, text="System Volume (device)", bg='#2c2c2c', fg='#8696a0',
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(12, 0))
        vr = tk.Frame(card, bg='#2c2c2c')
        vr.pack(fill=tk.X, padx=18, pady=4)
        self.vol_lbl = tk.Label(vr, text="", bg='#2c2c2c', fg='#e9edef',
                                font=("Segoe UI", 11, "bold"), width=5, anchor="e")
        self.vol_lbl.pack(side=tk.RIGHT)
        cur_vol = self.volume.get()
        try:
            cur_vol = int(cur_vol)
        except Exception:
            cur_vol = 50
        self.vol_scale = ModernScale(vr, from_=0, to=100, value=cur_vol,
                                     command=self.on_volume_change,
                                     bg='#2c2c2c', track='#3a3a3a', fill='#25d366',
                                     height=22)
        self.vol_scale.set(cur_vol)
        self.vol_lbl.configure(text=f"{cur_vol}%")
        self.vol_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        # ---- Calls ----
        tk.Label(card, text="Calls", bg='#2c2c2c', fg='#8696a0',
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(16, 0))

        cl = tk.Frame(card, bg='#2c2c2c')
        cl.pack(fill=tk.X, padx=18, pady=(6, 0))
        tk.Label(cl, text="Call Ringtone", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 11)).pack(side=tk.LEFT)
        tk.Label(cl, text=f"{len(self.call_ringtone.labels())} built-in + apni file",
                 bg='#2c2c2c', fg='#8696a0', font=("Segoe UI", 9)).pack(side=tk.RIGHT)

        cr = tk.Frame(card, bg='#2c2c2c')
        cr.pack(fill=tk.X, padx=18, pady=(2, 0))
        self.ct_custom_path = getattr(self, 'custom_call_ringtone_path', "")
        self.ct_var = tk.StringVar(value=self.call_ringtone_label)
        ct_values = list(self.call_ringtone.labels())
        if self.ct_custom_path:
            ct_values.append("Custom: " + os.path.basename(self.ct_custom_path))
        ct_values += ["Custom…", "None"]
        self.ct_box = ttk.Combobox(cr, textvariable=self.ct_var, style='Dark.TCombobox',
                                   values=ct_values, state="readonly",
                                   font=("Segoe UI", 11))
        self.ct_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ct_box.bind("<<ComboboxSelected>>", self.on_call_ringtone_pick)
        ct_play = RoundedButton(cr, text="Play", icon=ICON["play"],
                                icon_font=(self.icon_family, 11), command=self.preview_call_ringtone,
                                font=("Segoe UI", 10), parent_bg='#2c2c2c',
                                width=84, height=32, radius=10,
                                active_bg='#25d366', active_fg='white')
        ct_play.set_active(True)
        ct_play.pack(side=tk.LEFT, padx=(8, 0))

        add_ct = RoundedButton(card, text="Add your own call ringtone…", icon=ICON["music"],
                               icon_font=(self.icon_family, 12), command=self.choose_call_ringtone_file,
                               font=("Segoe UI", 10), parent_bg='#2c2c2c',
                               width=224, height=32, radius=10,
                               active_bg='#2c2c2c', active_fg='white')
        add_ct.set_active(True)
        add_ct.pack(anchor="w", padx=18, pady=(8, 0))

        tk.Label(card, text="Call Volume", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 11)).pack(anchor="w", padx=18, pady=(12, 0))
        cvr = tk.Frame(card, bg='#2c2c2c')
        cvr.pack(fill=tk.X, padx=18, pady=4)
        self.ct_vol_lbl = tk.Label(cvr, text=f"{self.call_ringtone.volume}%", bg='#2c2c2c',
                                   fg='#e9edef', font=("Segoe UI", 11, "bold"),
                                   width=5, anchor="e")
        self.ct_vol_lbl.pack(side=tk.RIGHT)
        self.ct_vol_scale = ModernScale(cvr, from_=0, to=100, value=self.call_ringtone.volume,
                                        command=self.on_call_volume,
                                        bg='#2c2c2c', track='#3a3a3a', fill='#25d366',
                                        height=22)
        self.ct_vol_scale.set(self.call_ringtone.volume)
        self.ct_vol_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        # Theme
        tk.Label(card, text="Theme", bg='#2c2c2c', fg='#8696a0', font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(12, 0))
        self.tv = tk.StringVar(value=getattr(self, 'theme_name', 'Dark'))
        tf = tk.Frame(card, bg='#2c2c2c')
        tf.pack(anchor="w", padx=18, pady=4)
        tk.Radiobutton(tf, text="Dark Mode", variable=self.tv, value="Dark", command=self.choose_theme,
                       bg='#2c2c2c', fg='#e9edef',
                       selectcolor='#2c2c2c', activebackground='#2c2c2c', activeforeground='white',
                       font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=(0, 18))
        tk.Radiobutton(tf, text="Light Mode", variable=self.tv, value="Light", command=self.choose_theme,
                       bg='#2c2c2c', fg='#e9edef',
                       selectcolor='#2c2c2c', activebackground='#2c2c2c', activeforeground='white',
                       font=("Segoe UI", 11)).pack(side=tk.LEFT)

        # Time format (12-hour / 24-hour clock)
        tk.Label(card, text="Time Format", bg='#2c2c2c', fg='#8696a0',
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(12, 0))
        self.timef_var = tk.StringVar(value='24-hour' if self.time_24h else '12-hour')
        timef = tk.Frame(card, bg='#2c2c2c')
        timef.pack(anchor="w", padx=18, pady=4)
        for txt in ("12-hour", "24-hour"):
            tk.Radiobutton(timef, text=txt, variable=self.timef_var, value=txt,
                           command=self.set_time_format, bg='#2c2c2c', fg='#e9edef',
                           selectcolor='#2c2c2c', activebackground='#2c2c2c',
                           activeforeground='white',
                           font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=(0, 18))

        # ---- Server (info pushed by the server) ----
        tk.Label(card, text="Server", bg='#2c2c2c', fg='#8696a0',
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(16, 0))
        srv = tk.Frame(card, bg='#2c2c2c')
        srv.pack(fill=tk.X, padx=18, pady=(6, 0))
        tk.Label(srv, text="Connected to", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 11)).pack(side=tk.LEFT)
        tk.Label(srv, text=f"{self.server_url}",
                 bg='#2c2c2c', fg='#25d366',
                 font=("Segoe UI", 11, "bold")).pack(side=tk.RIGHT)
        srv2 = tk.Frame(card, bg='#2c2c2c')
        srv2.pack(fill=tk.X, padx=18, pady=4)
        tk.Label(srv2, text="Max Clients", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 11)).pack(side=tk.LEFT)
        self.srv_max_lbl = tk.Label(srv2, text=f"{getattr(self, 'server_max', 50)}",
                                    bg='#2c2c2c', fg='#25d366',
                                    font=("Segoe UI", 11, "bold"))
        self.srv_max_lbl.pack(side=tk.RIGHT)
        srv3 = tk.Frame(card, bg='#2c2c2c')
        srv3.pack(fill=tk.X, padx=18, pady=4)
        tk.Label(srv3, text="Online now", bg='#2c2c2c', fg='#e9edef',
                 font=("Segoe UI", 11)).pack(side=tk.LEFT)
        tk.Label(srv3, text=f"{max(0, getattr(self, '_client_total', 0))}",
                 bg='#2c2c2c', fg='#25d366',
                 font=("Segoe UI", 11, "bold")).pack(side=tk.RIGHT)
        tk.Label(card, text="Server change karega to yahan turant update ho jayega",
                 bg='#2c2c2c', fg='#8696a0', font=("Segoe UI", 8)).pack(anchor="w", padx=18)

        self.set_dirty_lbl = tk.Label(card, text="", bg='#2c2c2c', fg='#e3b341',
                                      font=("Segoe UI", 9, "bold"))
        self.set_dirty_lbl.pack(anchor="w", padx=18, pady=(14, 0))
        save_btn = RoundedButton(card, text="Save Settings", command=self.save_client_settings,
                                 font=("Segoe UI", 11, "bold"), parent_bg='#2c2c2c',
                                 width=140, height=38, radius=12,
                                 active_bg='#25d366', active_fg='white')
        save_btn.set_active(True)
        save_btn.pack(anchor="w", padx=18, pady=(6, 18))
        # allow mouse-wheel scrolling of the settings card inside the list canvas
        self._bind_mousewheel_recursive(self.cii)
        self._theme_subtree(self.cii)
        self._queue_scrollregion(self.ccv)
        self._settings_building = False

    def choose_color(self):
        """Pick an avatar colour (preview only; applied on Save)."""
        c = colorchooser.askcolor(title="Choose Profile Color", initialcolor=self.pc.get())
        if c[1]:
            self.pc.set(c[1])
            try:
                self.color_btn.set_bg(c[1])
            except Exception:
                pass
            self._render_settings_avatar()
            self._settings_dirty()

    def on_volume_change(self, value):
        """Slider moved -> update the label only (device volume set on Save)."""
        try:
            v = int(float(value))
        except Exception:
            return
        try:
            self.vol_lbl.configure(text=f"{v}%")
        except Exception:
            pass
        self._settings_dirty()

    def _settings_dirty(self):
        """Mark the Settings card as having unsaved changes."""
        if getattr(self, '_settings_building', False):
            return
        self._settings_unsaved = True
        try:
            self.set_dirty_lbl.configure(
                text="\u25CF Unsaved changes \u2014 click \u201cSave Settings\u201d to apply")
        except Exception:
            pass

    def _settings_clean(self):
        self._settings_unsaved = False
        try:
            self.set_dirty_lbl.configure(text="")
        except Exception:
            pass

    def _wget(self, name, fallback=''):
        """Read a widget/StringVar value that may already have been destroyed.

        The Settings card lives inside the middle panel, which is rebuilt
        whenever a client joins/leaves or a message arrives.  Reading a stale
        Scale/Entry after that would raise a TclError and dump a traceback on
        the terminal, so fall back to a safe default instead.
        """
        obj = getattr(self, name, None)
        try:
            return obj.get()
        except Exception:
            return fallback

    def _apply_ringtone_choice(self, player, label, path=''):
        """Point `player` at the tone named by `label` (built-in / custom / None)."""
        label = (label or '').strip()
        if not label or label == 'None':
            player.set_file('')
            return 'None'
        if label.startswith('Custom: '):
            if path and os.path.exists(path):
                player.set_file(path)
            return label
        if label in player.labels():
            player.set_file(player.builtin_path(label))
        return label

    def _preview_ringtone_choice(self, player, label, custom_path, volume=None):
        """Play the *selected* tone once without committing it to the player."""
        label = (label or '').strip()
        if not label or label in ('None', 'Custom…'):
            return
        if label.startswith('Custom: '):
            path = custom_path or ''
        elif label in player.labels():
            path = player.builtin_path(label)
        else:
            path = ''
        if not path or not os.path.exists(path):
            return
        try:
            saved_path, saved_vol = player.path, player.volume
        except Exception:
            saved_path, saved_vol = '', 15
        try:
            if volume is not None:
                player.set_volume(volume)
            player.set_file(path)
            player.play()
        except Exception:
            pass
        finally:
            try:
                player.set_file(saved_path)
                player.set_volume(saved_vol)
            except Exception:
                pass

    def _apply_settings_now(self, data, new_pic):
        """Apply the values taken from the Settings card to this running client.

        Called only when the user presses "Save Settings" so no control can
        change the app before then.
        """
        # ---- theme ----
        try:
            if data.get('theme'):
                self.apply_theme(data['theme'], save=False)
        except Exception:
            pass
        # ---- 12 / 24 hour clock ----
        try:
            self.time_24h = (data.get('time_format') != '12-hour')
            if self.current_chat_id is not None:
                self.render_msgs({'messages': getattr(self, '_current_msgs', [])})
            self.refresh_middle_list()
        except Exception:
            pass
        # ---- avatar colour + photo ----
        if data.get('profile_color'):
            self.my_color = data['profile_color']
        self.my_pic = new_pic or ''
        self._draft_pic = None
        try:
            self._render_my_avatar()
            self._render_settings_avatar()
        except Exception:
            pass
        # ---- notification ringtone + volume ----
        label = data.get('ringtone') or 'None'
        path = (data.get('ringtone_path') or '').strip()
        self.ringtone_label = self._apply_ringtone_choice(self.ringtone, label, path)
        if self.ringtone_label.startswith('Custom: ') and path:
            self.custom_ringtone_path = path
        try:
            self.ringtone.set_volume(int(data.get('notification_volume', self.ringtone.volume)))
        except Exception:
            pass
        # ---- call ringtone + volume ----
        clabel = data.get('call_ringtone') or 'None'
        cpath = (data.get('call_ringtone_path') or '').strip()
        self.call_ringtone_label = self._apply_ringtone_choice(self.call_ringtone, clabel, cpath)
        if self.call_ringtone_label.startswith('Custom: ') and cpath:
            self.custom_call_ringtone_path = cpath
        try:
            self.call_ringtone.set_volume(int(data.get('call_volume', self.call_ringtone.volume)))
        except Exception:
            pass
        # ---- system (device) volume ----
        try:
            self.volume.set(int(data.get('system_volume', self.volume.get())))
        except Exception:
            pass
        try:
            self.me_lbl.configure(text=self.my_username[:12])
        except Exception:
            pass

    def save_client_settings(self):
        prev_name = self.my_username
        self.my_username = (self._wget('pn', self.my_username) or self.my_username).strip() \
            or self.my_username

        def _vol(attr, fallback):
            try:
                return int(self._wget(attr, fallback))
            except Exception:
                return int(fallback)

        # the staged profile photo (None == untouched)
        draft = getattr(self, '_draft_pic', None)
        pic_before = self.my_pic
        new_pic = self.my_pic if draft is None else draft
        data = {
            'username': self.my_username,
            'prev_username': prev_name if prev_name != self.my_username else '',
            'theme': self._wget('tv', self.theme_name),
            'notification_volume': _vol('rt_vol_scale', self.ringtone.volume),
            'system_volume': _vol('vol_scale', 100),
            'ringtone': self._wget('rt_var', self.ringtone_label),
            'ringtone_path': getattr(self.rt_custom_path, 'strip', lambda: '')() or '',
            'call_ringtone': self._wget('ct_var', self.call_ringtone_label),
            'call_ringtone_path': getattr(self.ct_custom_path, 'strip', lambda: '')() or '',
            'call_volume': _vol('ct_vol_scale', self.call_ringtone.volume),
            'profile_color': self._wget('pc', self.my_color),
            'avatar': new_pic,
            'time_format': self._wget('timef_var', '') or
                           ('24-hour' if self.time_24h else '12-hour'),
        }
        # apply immediately on this running client, then persist on the server
        self._apply_settings_now(data, new_pic)
        sio.emit('update_settings', data)
        if new_pic != pic_before:
            sio.emit('update_profile', {'username': self.my_username,
                                        'avatar': new_pic})
        self._settings_clean()
        self.show_toast("Settings saved!")
        self.notify("Settings changed", f"Profile: {self.my_username}  \u2022  "
                    f"Ringtone: {data['ringtone']}  \u2022  "
                    f"{data['notification_volume']}%", kind='settings')
        self.switch_view('chats')

    def choose_profile_pic(self):
        """Pick an image from disk and use it as this client's profile photo."""
        if not PIL_OK:
            self.show_toast("Pillow install chahiye: pip install Pillow")
            self.notify("Profile photo", "Pillow missing (pip install Pillow)",
                        kind='error')
            return
        path = filedialog.askopenfilename(
            title="Choose profile photo",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            data = self._square_photo_bytes(path, 192)
            if not data:
                raise ValueError("cannot read image")
        except Exception as e:
            self.show_toast("Image load nahi hui")
            self.notify("Profile photo failed", str(e), kind='error')
            return
        # stage the photo; it is pushed to the server only on "Save Settings"
        self._draft_pic = base64.b64encode(data).decode("ascii")
        self._img_cache.pop((self._pic_hash(self._draft_pic), 72), None)
        self._render_settings_avatar()
        self._settings_dirty()
        self.show_toast("Photo selected \u2014 Save Settings to apply")

    def remove_profile_pic(self):
        # stage the removal; applied only on "Save Settings"
        self._draft_pic = ""
        self._render_settings_avatar()
        self._settings_dirty()
        self.show_toast("Photo removed \u2014 Save Settings to apply")

    def _render_settings_avatar(self):
        cv = getattr(self, 'set_av_cv', None)
        if cv is None:
            return
        # the preview follows the draft (staged) photo, if any
        pic = self.my_pic
        draft = getattr(self, '_draft_pic', None)
        if draft is not None:
            pic = draft
        self._draw_avatar(cv, 72, 20, self.my_username, self._my_avatar_color(), pic)

    def choose_ringtone_file(self):
        """Let the user add their own notification ringtone from disk."""
        path = filedialog.askopenfilename(
            title="Choose notification ringtone",
            filetypes=[("Audio", "*.wav *.mp3 *.m4a *.wma *.aac *.ogg"),
                       ("WAV", "*.wav"), ("All files", "*.*")])
        if not path:
            return
        # staged only: the live player is untouched until "Save Settings"
        self.rt_custom_path = path
        label = "Custom: " + os.path.basename(path)
        try:
            vals = list(self.rt_box.cget("values"))
        except Exception:
            vals = []
        if label not in vals:
            vals.insert(max(0, len(vals) - 2), label)
            self.rt_box.configure(values=vals)
        self.rt_var.set(label)
        self._settings_dirty()
        self.show_toast("Ringtone selected \u2014 Save Settings to apply")

    def on_ringtone_pick(self, *_a):
        """Combobox changed: pick a built-in tone or open the file browser.

        The choice is only previewed here; it is committed on "Save Settings".
        """
        label = self.rt_var.get()
        if label == "Custom…":
            self.choose_ringtone_file()
            return
        self._settings_dirty()
        self._preview_ringtone_choice(self.ringtone, label, self.rt_custom_path,
                                      self._wget('rt_vol_scale', self.ringtone.volume))

    def on_ringtone_volume(self, value):
        try:
            v = int(float(value))
        except Exception:
            return
        try:
            self.rt_vol_lbl.configure(text=f"{v}%")
        except Exception:
            pass
        self._settings_dirty()

    def preview_ringtone(self):
        self._preview_ringtone_choice(self.ringtone, self.rt_var.get(),
                                      self.rt_custom_path,
                                      self._wget('rt_vol_scale', self.ringtone.volume))


# ============================================================
# Modern range slider (filled track + round knob) used by Settings
# ============================================================
class ModernScale(tk.Canvas):
    """A modern filled-track range control (0..100 by default).

    Drop-in replacement for tk.Scale: exposes .get() / .set() / .pack() and
    calls ``command(value)`` while dragging, so the existing settings wiring
    (labels, dirty-flag, save/restore) keeps working unchanged.
    """

    def __init__(self, parent, from_=0, to=100, value=50, command=None,
                 bg='#2c2c2c', track='#3a3a3a', fill='#25d366',
                 knob='#ffffff', height=22, **kw):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0,
                         bd=0, cursor='hand2', **kw)
        self.from_ = float(from_)
        self.to = float(to)
        self._value = float(value)
        self.command = command
        self.track = track
        self.fill = fill
        self.knob = knob
        self.knob_r = 8
        self.pad = 10
        self.bind('<Configure>', lambda e: self._draw())
        self.bind('<Button-1>', self._press)
        self.bind('<B1-Motion>', self._drag)
        self.bind('<ButtonRelease-1>', lambda e: None)

    def _clamp(self, v):
        return max(self.from_, min(self.to, v))

    def _x_for(self, v):
        w = max(1, self.winfo_width())
        span = max(1.0, self.to - self.from_)
        return self.pad + (w - 2 * self.pad) * (v - self.from_) / span

    def _val_for(self, x):
        w = max(1, self.winfo_width())
        span = max(1.0, self.to - self.from_)
        ratio = (x - self.pad) / max(1.0, w - 2 * self.pad)
        ratio = max(0.0, min(1.0, ratio))
        return self.from_ + ratio * span

    def _draw(self):
        self.delete('all')
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4:
            return
        ty = h // 2
        tr = 4
        self.create_rectangle(self.pad, ty - tr, w - self.pad, ty + tr,
                              fill=self.track, outline='')
        x = self._x_for(self._value)
        self.create_rectangle(self.pad, ty - tr, x, ty + tr,
                              fill=self.fill, outline='')
        self.create_oval(x - self.knob_r, ty - self.knob_r,
                         x + self.knob_r, ty + self.knob_r,
                         fill=self.knob, outline=self.fill, width=2)

    def _set(self, x):
        self._value = self._clamp(self._val_for(x))
        self._draw()
        if self.command is not None:
            try:
                self.command(int(self._value))
            except Exception:
                try:
                    self.command(self._value)
                except Exception:
                    pass

    def _press(self, e):
        self._set(e.x)

    def _drag(self, e):
        self._set(e.x)

    def get(self):
        return int(self._value)

    def set(self, v):
        self._value = self._clamp(float(v))
        self._draw()
