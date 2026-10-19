# client_calls.py — the call window, its widgets and the call
# mixin (start/accept/end, signalling handlers, call log).
from client_core import *




class CallWindow(tk.Toplevel):
    """WhatsApp-style voice / video call window.

    - caller: name + "Calling…" (peer offline) or "Ringing…" (peer online)
    - callee: name + "Incoming call" with Accept / Decline
    - once answered the status turns into a live mm:ss counter
    - bottom bar: speaker, video, mute, end (real WhatsApp-style icons)
    - video calls show the other side full-window with your own camera as a
      small picture-in-picture tile in the corner
    """

    SR = 16000          # audio sample rate used on the wire
    CHUNK = 1024        # audio frames per packet (~64 ms)
    # 16 kHz is the wire format.  Plenty of Windows sound cards refuse it, so a
    # device that says no is opened at its own rate and resampled instead of
    # silently dropping every packet.
    RATES = (16000, 32000, 44100, 48000)
    EARPIECE_GAIN = 0.55    # playback level when "speaker" is switched off

    def __init__(self, app, peer, kind='voice', direction='out',
                 call_id=None, online=False, group='', group_name=''):
        super().__init__(app.root)
        self.app = app
        self.peer = peer or {}
        self.kind = kind if kind in ('voice', 'video') else 'voice'
        self.direction = direction
        self.call_id = call_id or uuid.uuid4().hex[:10]
        self.online = bool(online)
        self.group = group or ''
        self.is_group = bool(self.group)
        self.group_name = group_name or ''
        # a group call is titled with the group (a 1:1 call with the person)
        self.peer_name = ((self.group_name if self.is_group
                           else self.peer.get('name')) or 'Unknown')
        self.from_name = self.peer.get('from') or ''
        self.participants = 1

        self.status = 'incoming' if direction == 'in' else \
            ('ringing' if self.online else 'calling')
        self.connected = False
        self._ended = False
        self._destroying = False
        self.muted = False
        # Speakerphone starts OFF (earpiece level).  Turning it on boosts the
        # playback to full volume - see toggle_speaker()/_audio_play_loop().
        # Speakerphone is ON by default: laptop calls use the speakers, so audio
        # plays at full volume instead of the quiet "earpiece" level.
        self.speaker_on = True
        self.video_on = (self.kind == 'video')
        self.muted_video = False
        self.peer_cams_off = set()      # names whose camera is switched off
        self.remote_from = ''           # who sent the frame on screen (groups)
        self.avatar_shown_for = ''      # whose profile picture is on screen
        # per-participant video tiles (group calls only)
        self.remote_tiles = {}
        self.remote_tile_order = []
        self._remote_live = False       # True while live remote video is drawn
        self.cam_index = 0
        self.camera_ok = False
        self._cam_warned = False        # "no camera" message shown only once
        self._dep_warned = False        # "install opencv/numpy" shown only once

        self._media_on = False
        self._want_video = False
        self._vid_gen = 0
        self._t0 = None
        self._dur = 0
        self._ring_job = None
        self._timer_job = None
        self._noans_job = None
        self._play_q = queue.Queue(maxsize=50)   # ~3 s of 64 ms frames max
        self._photo_ref = {'remote': None, 'local': None}
        # newest-frame slots so the Tk queue never backs up with stale video
        self._pending_remote = None
        self._pending_local = None
        self._remote_scheduled = False
        self._local_scheduled = False
        self._threads = []
        self._stream_in = None
        self._stream_out = None
        self._cv = None
        # IMPORTANT: pyaudio only exposes open() on a PyAudio *instance* - the
        # bare module has no open() at all.  Using the module here made both
        # audio loops die silently on an AttributeError, so no voice ever left
        # (and no voice was ever played back).
        try:
            self._pa = _pyaudio.PyAudio() if PYAUDIO_OK else None
        except Exception:
            self._pa = None

        self.title("Call \u2022 " + self.peer_name)
        self.configure(bg='#0b141a')
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        try:
            self.transient(app.root)
        except Exception:
            pass

        self._build()
        self._center()
        try:
            self.attributes('-topmost', True)
            self.after(500, lambda: self._safe_attr_topmost(False))
        except Exception:
            pass
        # Video calls open the camera immediately - before the callee answers -
        # so the other side can already see you (exactly like the real app).
        if self.kind == 'video':
            self._start_video()
        self._start_ring()
        # nobody picks up -> give up automatically (caller) / stop (callee)
        self._noans_job = self.after(35000, lambda: self._timeout())

    # ---------- layout ----------
    def _build(self):
        head = tk.Frame(self, bg='#0b141a')
        head.pack(fill=tk.X, pady=(18, 6))
        self.name_lbl = tk.Label(head, text=self.peer_name, bg='#0b141a',
                                 fg='#e9edef', font=("Segoe UI", 20, "bold"))
        self.name_lbl.pack()
        self.status_lbl = tk.Label(head, text='', bg='#0b141a', fg='#8696a0',
                                   font=("Segoe UI", 13))
        self.status_lbl.pack(pady=(2, 0))

        self.body = tk.Frame(self, bg='#0b141a')
        self.body.pack(fill=tk.BOTH, expand=True)

        self.ctrl = tk.Frame(self, bg='#0b141a')
        self.ctrl.pack(fill=tk.X, pady=(12, 22))

        self._build_body()
        self._render_controls()
        self._refresh_status()

    def _build_body(self):
        for w in self.body.winfo_children():
            w.destroy()
        self.remote_cv = None
        self.local_cv = None
        self.remote_tiles = {}
        self.remote_tile_order = []
        if self.kind == 'video':
            if self.is_group:
                self.remote_cv = None
                self._remote_ph = None
                self.grid_cv = tk.Canvas(self.body, bg='#111b21',
                                         highlightthickness=0, bd=0)
                self.grid_sb = tk.Scrollbar(self.body, orient=tk.VERTICAL,
                                           command=self.grid_cv.yview)
                self.grid_inner = tk.Frame(self.grid_cv, bg='#111b21')
                self.grid_win = self.grid_cv.create_window(
                    (0, 0), window=self.grid_inner, anchor='nw')
                self.grid_cv.configure(yscrollcommand=self.grid_sb.set)
                self.grid_cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                self.grid_inner.bind('<Configure>', lambda e: self._update_grid_scroll())
                self.grid_cv.bind('<Configure>', self._on_grid_resize)
                self._grid_placeholder = tk.Label(self.grid_inner,
                                                  text="Waiting for participants\\u2026",
                                                  bg='#111b21', fg='#4a5a63',
                                                  font=("Segoe UI", 13, "bold"))
                self._grid_placeholder.pack(pady=40)
                self.after(90, self._draw_remote_placeholder)
            else:
                self.remote_cv = tk.Canvas(self.body, bg='#111b21',
                                           highlightthickness=0, bd=0)
                self.remote_cv.pack(fill=tk.BOTH, expand=True)
                self._remote_ph = self.remote_cv.create_text(
                    200, 160, text="Waiting for " + self.peer_name + "\u2026",
                    fill='#4a5a63', font=("Segoe UI", 15, "bold"), tags='ph')
                self.after(90, self._draw_remote_placeholder)
                self.body.bind('<Configure>', self._on_body_resize, add='+')
            # picture-in-picture: my own camera, small, top-right
            self.local_cv = tk.Canvas(self.body, width=136, height=102,
                                       bg='#202c33', highlightthickness=0, bd=0)
            self.local_cv.place(relx=1.0, rely=0.0, x=-14, y=14, anchor='ne')
            self.local_cv.create_text(68, 51, text="Camera", fill='#8696a0',
                                      font=("Segoe UI", 10), tags='ph')
        else:
            self.avatar_cv = tk.Canvas(self.body, width=190, height=190,
                                       bg='#0b141a', highlightthickness=0, bd=0)
            self.avatar_cv.pack(expand=True)
            self._draw_avatar_placeholder()


    def _on_body_resize(self, e):
        try:
            if self.remote_cv is None:
                return
            if not getattr(self, '_remote_live', False):
                # keep the profile picture centred while video has not started
                self._draw_remote_placeholder()
            elif self._remote_ph is not None:
                self.remote_cv.coords(self._remote_ph, e.width / 2, e.height / 2)
        except Exception:
            pass

    # ---------- group video grid helpers ----------
    def _ensure_remote_tile(self, name):
        """Create (or reuse) a video tile for a remote participant (groups)."""
        if not self.is_group or not name:
            return None
        if name in self.remote_tiles:
            return self.remote_tiles[name]
        # drop the "waiting" placeholder once the first tile appears
        try:
            if getattr(self, '_grid_placeholder', None) is not None:
                self._grid_placeholder.destroy()
        except Exception:
            pass
        self._grid_placeholder = None
        tile = tk.Frame(self.grid_inner, bg='#111b21')
        cv = tk.Canvas(tile, bg='#111b21', highlightthickness=0, bd=0)
        cv.pack(fill=tk.BOTH, expand=True)
        lbl = tk.Label(tile, text=name, bg='#111b21', fg='#e9edef',
                       font=("Segoe UI", 9, "bold"), anchor='center')
        lbl.pack(side=tk.BOTTOM, fill=tk.X, pady=(2, 4))
        self.remote_tiles[name] = {'frame': tile, 'canvas': cv, 'label': lbl}
        self.remote_tile_order.append(name)
        self._relayout_remote_tiles()
        return self.remote_tiles[name]

    def _relayout_remote_tiles(self):
        if not self.is_group:
            return
        n = len(self.remote_tile_order)
        if n <= 1:
            cols = 1
        elif n == 2:
            cols = 2
        else:
            cols = 3
        for i, name in enumerate(self.remote_tile_order):
            t = self.remote_tiles.get(name)
            if not t:
                continue
            try:
                t['frame'].grid(row=i // cols, column=i % cols, sticky='nsew',
                                padx=3, pady=3)
            except Exception:
                pass
        for c in range(cols):
            self.grid_inner.grid_columnconfigure(c, weight=1)
        rows = (n + cols - 1) // cols if n else 1
        for r in range(rows):
            self.grid_inner.grid_rowconfigure(r, weight=1)
        self._update_grid_scroll()

    def _update_grid_scroll(self):
        try:
            self.grid_inner.update_idletasks()
            self.grid_cv.configure(scrollregion=self.grid_cv.bbox('all'))
            if self.grid_inner.winfo_reqheight() > self.grid_cv.winfo_height() + 4:
                self.grid_sb.pack(side=tk.RIGHT, fill=tk.Y)
            else:
                self.grid_sb.pack_forget()
        except Exception:
            pass

    def _on_grid_resize(self, e):
        try:
            self.grid_cv.itemconfigure(self.grid_win, width=e.width)
        except Exception:
            pass

    def _remove_remote_tile(self, name):
        if not self.is_group or name not in self.remote_tiles:
            return
        t = self.remote_tiles.pop(name, None)
        if name in self.remote_tile_order:
            self.remote_tile_order.remove(name)
        try:
            if t and t['frame'].winfo_exists():
                t['frame'].destroy()
        except Exception:
            pass
        self._relayout_remote_tiles()

    def _draw_remote_placeholder(self):
        """Big profile picture (or initials) shown before their video arrives."""
        cv = getattr(self, 'remote_cv', None)
        if cv is None or self._ended:
            return
        try:
            cv.delete('all')
            w = max(cv.winfo_width(), 360)
            h = max(cv.winfo_height(), 280)
            d = max(90, min(w, h) // 3)
            self._draw_avatar_tagged(
                cv, d, self.peer_name,
                self.peer.get('color') or '#2a3942',
                self.peer.get('pic') or '', 'rav',
                (w - d) / 2, (h - d) / 2 - 16)
            if self.direction == 'out' and not self.connected:
                cap = "Calling %s\u2026" % self.peer_name
            elif self.direction == 'in' and not self.connected:
                cap = "Incoming %s call" % self.kind
            else:
                cap = "Connecting video\u2026"
            cv.create_text(w / 2, (h + d) / 2 + 2, text=cap,
                           fill='#8696a0', font=("Segoe UI", 12), tags='ph')
            self.avatar_shown_for = self.peer_name
        except Exception:
            pass

    def _draw_avatar_tagged(self, cv, size, name, color, pic, tag, x=0, y=0):
        """Circular profile photo (or coloured initials) on `cv` under `tag`."""
        try:
            cv.delete(tag)
        except Exception:
            pass
        ph = None
        if pic:
            try:
                ph = self.app._avatar_photo(pic, int(size))
            except Exception:
                ph = None
        if ph is not None:
            cv.create_image(x + size / 2, y + size / 2, image=ph, tags=tag)
            self._photo_ref['p_' + tag] = ph        # keep a reference
            return
        _rrect(cv, x, y, x + size, y + size, size / 2, color or '#2c2c2c',
               outline='', tags=tag)
        try:
            txt = self.app._initials(name) if name else 'U'
        except Exception:
            txt = (name[:1] or 'U').upper()
        cv.create_text(x + size / 2, y + size / 2, text=txt, fill='white',
                       font=("Segoe UI", max(9, int(size * 0.34)), "bold"),
                       tags=tag)

    def _draw_avatar_placeholder(self):
        cv = getattr(self, 'avatar_cv', None)
        if cv is None:
            return
        cv.delete('all')
        d = 190
        self._draw_avatar_tagged(cv, d, self.peer_name,
                                 self.peer.get('color') or '#2a3942',
                                 self.peer.get('pic') or '', 'avatar')

    def _render_controls(self, ended=False):
        for w in self.ctrl.winfo_children():
            w.destroy()
        if ended:
            return
        IF = self.app.icon_family
        # ONE horizontal row, centred in the window (WhatsApp-style layout).
        # The inner 'holder' frame expands horizontally so the buttons always sit
        # side by side (x-axis) and never wrap onto separate lines.
        row = tk.Frame(self.ctrl, bg='#0b141a')
        row.pack(fill=tk.X, padx=12)
        holder = tk.Frame(row, bg='#0b141a')
        holder.pack(expand=True)
        if self.direction == 'in' and not self.connected:
            # Incoming call, exactly like WhatsApp: Decline (red, left) and
            # Accept (green, right), side by side.
            CallBtn(holder, ICON["hangup"], self.reject, size=64, rotation=135,
                    bg='#e53935', fg='white', icon_font=(IF, 26)).pack(
                        side=tk.LEFT, padx=16)
            CallBtn(holder, ICON["phone"], self.accept, size=64,
                    bg='#25d366', fg='#0b141a', icon_font=(IF, 26)).pack(
                        side=tk.LEFT, padx=16)
            return
        # In-call / outgoing row: all buttons in a single horizontal line
        self.btn_speaker = CallBtn(holder, ICON["volume"], self.toggle_speaker,
                                   size=58, icon_font=(IF, 20))
        self.btn_speaker.pack(side=tk.LEFT, padx=7)
        if self.kind == 'video':
            self.btn_video = CallBtn(holder, ICON["camoff"], self.toggle_video,
                                     size=58, icon_font=(IF, 20))
            self.btn_video.pack(side=tk.LEFT, padx=7)
            self.btn_flip = CallBtn(holder, ICON["switch"], self.switch_camera,
                                    size=58, icon_font=(IF, 20))
            self.btn_flip.pack(side=tk.LEFT, padx=7)
        else:
            self.btn_video = CallBtn(holder, ICON["video"], self.toggle_video,
                                     size=58, icon_font=(IF, 20))
            self.btn_video.pack(side=tk.LEFT, padx=7)
            # A voice call starts with the camera OFF: show the button in the
            # "camera off" state so the user sees it is not sending video yet.
            self.btn_video.restyle(slash=True)
        self.btn_mute = CallBtn(holder, ICON["mic"], self.toggle_mute,
                                size=58, icon_font=(IF, 20))
        self.btn_mute.pack(side=tk.LEFT, padx=7)
        self.btn_end = CallBtn(holder, ICON["hangup"], self.hangup, size=64,
                               rotation=135, bg='#e53935', fg='white',
                               icon_font=(IF, 26))
        self.btn_end.pack(side=tk.LEFT, padx=12)
        # reflect current toggle states
        if self.muted:
            self.btn_mute.restyle(bg='#e53935', slash=True)
        if self.kind == 'video' and not self.video_on:
            self.btn_video.restyle(bg='#e53935', slash=True)
        if self.speaker_on:
            self.btn_speaker.restyle(bg='#25d366', fg='#0b141a')

    def _center(self):
        w, h = (780, 610) if self.kind == 'video' else (400, 620)
        try:
            self.update_idletasks()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
            self.geometry('%dx%d+%d+%d' % (w, h, x, y))
        except Exception:
            pass

    def _safe_attr_topmost(self, on):
        try:
            self.attributes('-topmost', on)
        except Exception:
            pass

    # ---------- status / ring / timer ----------
    def _refresh_status(self):
        if self.connected or self._ended:
            return
        if self.is_group:
            kind = "video" if self.kind == 'video' else "voice"
            if self.direction == 'in':
                txt = "Group %s call \u2022 %s" % (kind, self.from_name or 'invited you')
            else:
                txt = ("Starting group %s call\u2026" % kind if self.online
                       else "Calling group\u2026")
        elif self.direction == 'in':
            txt = "Incoming video call" if self.kind == 'video' else "Incoming voice call"
        else:
            txt = "Ringing\u2026" if self.online else "Calling\u2026"
        try:
            self.status_lbl.configure(text=txt)
        except Exception:
            pass

    def _start_ring(self):
        if self._ended or self.connected:
            return
        try:
            self.app.call_ringtone.play()
        except Exception:
            pass
        try:
            self._ring_job = self.after(2300, self._start_ring)
        except Exception:
            self._ring_job = None

    def _stop_ring(self):
        if self._ring_job:
            try:
                self.after_cancel(self._ring_job)
            except Exception:
                pass
            self._ring_job = None
        try:
            self.app.call_ringtone.stop()
        except Exception:
            pass

    def _start_timer(self):
        self._t0 = time.time()
        self._tick()

    def _tick(self):
        if self._ended or not self.connected:
            return
        self._dur = int(time.time() - self._t0)
        try:
            self.status_lbl.configure(text=self._live_status_text())
        except Exception:
            pass
        self._timer_job = self.after(1000, self._tick)

    def _live_status_text(self):
        t = self._fmt_elapsed(self._dur)
        if self.is_group:
            return "%d in call \u2022 %s" % (max(1, self.participants), t)
        return t

    @staticmethod
    def _fmt_elapsed(s):
        h, r = divmod(int(s), 3600)
        m, sec = divmod(r, 60)
        return ("%d:%02d:%02d" % (h, m, sec)) if h else ("%02d:%02d" % (m, sec))

    # ---------- lifecycle ----------
    def accept(self):
        if self._ended or self.connected:
            return
        self._stop_ring()
        self.connected = True
        try:
            sio.emit('call_accept', {'call_id': self.call_id, 'from': self.app.my_username})
        except Exception:
            pass
        self._begin()

    def on_accepted(self):
        """Peer answered (caller side)."""
        if self._ended or self.connected:
            return
        self._stop_ring()
        self.connected = True
        self._begin()

    def _begin(self):
        # cancel the no-answer timeout now that we're connected
        if self._noans_job:
            try:
                self.after_cancel(self._noans_job)
            except Exception:
                pass
            self._noans_job = None
        self._start_timer()
        self._render_controls()
        self._start_media()

    def reject(self):
        if self._ended:
            return
        try:
            sio.emit('call_reject', {'call_id': self.call_id, 'from': self.app.my_username})
        except Exception:
            pass
        self._finish('Declined')

    def hangup(self):
        if self._ended:
            return
        try:
            sio.emit('call_end', {'call_id': self.call_id, 'from': self.app.my_username})
        except Exception:
            pass
        self._finish('Call ended')

    def on_rejected(self):
        self._finish('Call declined')

    def on_remote_end(self):
        self._finish('Call ended')

    def on_peer_upgraded(self):
        """The other side switched a voice call to video.

        Only the side that *clicked* turns its camera on.  Here we just switch
        this window to the video layout and keep OUR own camera off (profile
        picture in the little tile) - the user can tap the camera button if
        they want to send video too.
        """
        if self._ended or self.kind == 'video':
            return
        self.kind = 'video'
        self.video_on = False          # my camera stays OFF until I tap it
        self.muted_video = True
        self._build_body()
        self._render_controls()
        self._show_my_avatar()
        self._warn("Video call", "%s turned on video" % self.peer_name,
                   kind='info')
    def _timeout(self):
        if self._ended or self.connected:
            return
        if self.direction == 'out':
            try:
                sio.emit('call_end', {'call_id': self.call_id, 'from': self.app.my_username})
            except Exception:
                pass
            self._finish('No answer')
        else:
            try:
                sio.emit('call_reject', {'call_id': self.call_id, 'from': self.app.my_username})
            except Exception:
                pass
            self._finish('Missed')

    def _finish(self, reason='Call ended'):
        if self._ended:
            return
        self._ended = True
        self._stop_ring()
        self._stop_media()
        self._cancel_jobs()
        if reason == 'Call ended' and self.connected and self._dur >= 0:
            reason = 'Call ended \u2022 ' + self._fmt_elapsed(self._dur)
        try:
            self.status_lbl.configure(text=reason)
        except Exception:
            pass
        try:
            self.app.record_call(self.peer_name, self.kind, self.peer,
                                 outcome=reason, dur=self._dur)
        except Exception:
            pass
        self._render_controls(ended=True)
        try:
            self.after(1500, self.destroy)
        except Exception:
            pass

    def _cancel_jobs(self):
        for attr in ('_ring_job', '_timer_job', '_noans_job'):
            jid = getattr(self, attr, None)
            if jid:
                try:
                    self.after_cancel(jid)
                except Exception:
                    pass
                setattr(self, attr, None)

    def on_close(self):
        if self._ended:
            self.destroy()
            return
        if self.connected:
            self.hangup()
        elif self.direction == 'out':
            self.hangup()
        else:
            self.reject()

    def destroy(self):
        if self._destroying:
            return
        self._destroying = True
        self._ended = True
        self._stop_ring()
        self._stop_media()
        self._cancel_jobs()
        try:
            if getattr(self.app, '_call', None) is self:
                self.app._call = None
        except Exception:
            pass
        try:
            super().destroy()
        except Exception:
            pass

    # ---------- controls ----------
    def toggle_mute(self):
        """Mute my microphone only - the other side can't hear me, but I can
        still hear them (playback keeps running)."""
        self.muted = not self.muted
        try:
            if self.muted:
                self.btn_mute.restyle(bg='#e53935', slash=True)
            else:
                self.btn_mute.restyle(bg='#2a3942', slash=False)
        except Exception:
            pass
        self._warn("Microphone muted" if self.muted else "Microphone on",
                   "The other side cannot hear you" if self.muted
                   else "You are live again", kind='info')

    def toggle_speaker(self):
        self.speaker_on = not self.speaker_on
        try:
            if self.speaker_on:
                self.btn_speaker.restyle(bg='#25d366', fg='#0b141a')
            else:
                self.btn_speaker.restyle(bg='#2a3942', fg='#e9edef')
        except Exception:
            pass
        # the button really changes the playback level: speakerphone = full
        # volume, "earpiece" (default) = quieter (EARPIECE_GAIN)
        self._warn("Speaker " + ("on" if self.speaker_on else "off"),
                   "Loud volume" if self.speaker_on
                   else "Earpiece volume (quieter)", kind='info')

    def toggle_video(self):
        if self.kind == 'video':
            self.video_on = not self.video_on
            self.muted_video = not self.video_on
            try:
                if self.video_on:
                    self.btn_video.restyle(bg='#2a3942', slash=False)
                else:
                    self.btn_video.restyle(bg='#e53935', slash=True)
            except Exception:
                pass
            if self.video_on:
                if not self._video_ready():   # no camera on this machine
                    self.video_on = False
                    self.muted_video = True
                    try:
                        self.btn_video.restyle(bg='#e53935', slash=True)
                    except Exception:
                        pass
                    self._show_my_avatar()
                    self._warn_camera_missing()
                    return
                self._start_video()          # camera + LED back on
            else:
                self._stop_video()           # release the camera
                self._show_my_avatar()       # profile picture in my PIP
            # let the other side swap my camera for my profile picture
            try:
                sio.emit('call_video', {
                    'call_id': self.call_id, 'on': bool(self.video_on),
                    'from': self.app.my_username,
                    'pic': self.app.my_pic or '',
                    'color': getattr(self.app, 'my_color', '') or '#2c2c2c',
                    'name': self.app.my_username})
            except Exception:
                pass
        else:
            # voice -> video upgrade (tell the other side too)
            if not self._video_ready():
                self._warn_camera_missing()
                return
            self.kind = 'video'
            self.video_on = True
            self.muted_video = False
            self._build_body()
            self._render_controls()
            try:
                sio.emit('call_upgrade', {'call_id': self.call_id, 'kind': 'video',
                                          'from': self.app.my_username})
            except Exception:
                pass
            self._start_video()

    def _video_ready(self):
        """True when this machine can actually capture video (cv2 present)."""
        return bool(CV2_OK and _cv2 is not None and _np is not None)

    def _warn_camera_missing(self):
        """Tell the user (once) that video needs opencv-python + numpy."""
        if self._dep_warned:
            return
        self._dep_warned = True
        self._show_my_avatar()
        self._warn("Camera unavailable",
                   "Video calls need  opencv-python  and  numpy  on this machine. "
                   "Install them with:   pip install opencv-python numpy",
                   kind='error')

    def switch_camera(self):
        self.cam_index = 1 - self.cam_index
        self._stop_video()
        if self.kind == 'video' and self.video_on:
            self._start_video()

    # ---------- media ----------
    def _sched(self, fn):
        """Run fn on the Tk main thread (safe from capture/socket threads)."""
        try:
            self.app._ui(fn)
        except Exception:
            pass

    def _start_media(self):
        if self._media_on:
            return
        self._media_on = True
        # audio only once the call is answered (video already runs from the
        # moment the call window opens, see __init__)
        if self._pa is None:
            self._warn("Audio unavailable",
                       "No audio device (or pyaudio is missing) - the call will "
                       "run without sound.")
            return
        for fn in (self._audio_send_loop, self._audio_play_loop):
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            self._threads.append(t)

    def _warn(self, title, message, kind='error'):
        """Toast a message (media-device problem, speaker state, ...)."""
        try:
            self._sched(lambda: self.app.notify(title, message, kind=kind))
        except Exception:
            pass

    def _open_audio(self, capture):
        """Open a 16-bit mono stream at a rate this device actually accepts."""
        if self._pa is None:
            return None, 0
        for rate in self.RATES:
            try:
                s = self._pa.open(format=_pyaudio.paInt16, channels=1, rate=rate,
                                  input=bool(capture), output=not capture,
                                  frames_per_buffer=self.CHUNK)
                return s, rate
            except Exception:
                continue
        return None, 0

    @staticmethod
    def _pcm_rate(data, src, dst):
        """Resample 16-bit mono PCM from `src` Hz to `dst` Hz.

        `audioop` was removed from Python 3.13+, so a numpy (or, as a last
        resort, the `audioop` module where it still exists) path keeps two
        laptops whose sound cards disagree on a rate talking to each other.
        """
        if not data or src == dst:
            return data
        if _audioop is not None:
            try:
                return _audioop.ratecv(data, 2, 1, src, dst, None)[0]
            except Exception:
                pass
        if _np is not None:
            try:
                a = _np.frombuffer(data, dtype='<i2').astype(_np.float32)
                if a.size < 2:
                    return data
                n = max(1, int(round(a.size * float(dst) / float(src))))
                idx = _np.linspace(0, a.size - 1, n)
                out = _np.interp(idx, _np.arange(a.size), a)
                return _np.clip(out, -32768, 32767).astype('<i2').tobytes()
            except Exception:
                pass
        return data

    @staticmethod
    def _apply_gain(data, gain):
        """Scale 16-bit mono PCM volume by `gain` (0..1) without audioop."""
        if not data or gain >= 0.999:
            return data
        if _audioop is not None:
            try:
                return _audioop.mul(data, 2, gain)
            except Exception:
                pass
        if _np is not None:
            try:
                a = _np.frombuffer(data, dtype='<i2').astype(_np.float32) * gain
                return _np.clip(a, -32768, 32767).astype('<i2').tobytes()
            except Exception:
                pass
        try:
            a = array.array('h')
            a.frombytes(data)
            for i, v in enumerate(a):
                a[i] = max(-32768, min(32767, int(v * gain)))
            return a.tobytes()
        except Exception:
            return data

    def _stop_media(self):
        self._media_on = False
        self._stop_video()
        # Let the capture/playback threads leave their blocking read()/write()
        # BEFORE the streams (and PortAudio itself) are torn down.  Closing a
        # stream while a thread sits inside it crashes the interpreter - the
        # old code never hit this only because the streams never opened at all.
        for t in list(self._threads):
            if t is not threading.current_thread() and t.is_alive():
                try:
                    t.join(timeout=1.0)
                except Exception:
                    pass
        for s in (self._stream_in, self._stream_out):
            if s is not None:
                try:
                    s.stop_stream()
                except Exception:
                    pass
                try:
                    s.close()
                except Exception:
                    pass
        self._stream_in = self._stream_out = None
        # release the audio device (in case a loop is still coming up, clear the
        # handle first so it bails out instead of opening a dead device)
        pa, self._pa = self._pa, None
        if pa is not None:
            try:
                pa.terminate()
            except Exception:
                pass

    def _audio_send_loop(self):
        stream, rate = self._open_audio(True)
        if stream is None:
            self._warn("Microphone unavailable",
                       "Could not open the microphone - the other side will not "
                       "hear you. Install pyaudio: py -3.12 -m pip install pyaudio")
            return
        self._stream_in = stream
        cv = None
        try:
            while self._media_on and not self._ended:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                except Exception:
                    break
                if self.muted:
                    continue
                if rate != self.SR and _audioop is not None:
                    try:                       # device rate -> 16 kHz wire rate
                        data, cv = _audioop.ratecv(data, 2, 1, rate, self.SR, cv)
                    except Exception:
                        continue
                elif rate != self.SR:
                    data = self._pcm_rate(data, rate, self.SR)
                if not data:
                    continue
                try:
                    sio.emit('call_media', {
                        'call_id': self.call_id, 'k': 'a',
                        'from': self.app.my_username,
                        'd': base64.b64encode(data).decode('ascii')})
                except Exception as e:
                    print("[audio] send emit failed:", e)
        finally:
            try:
                stream.stop_stream(); stream.close()
            except Exception:
                pass

    def _audio_play_loop(self):
        stream, rate = self._open_audio(False)
        if stream is None:
            # no output device: say so, then just drain the queue
            self._warn("Speaker unavailable",
                       "Could not open the speaker - you will not hear the "
                       "other side. Install pyaudio: py -3.12 -m pip install pyaudio")
            while self._media_on and not self._ended:
                try:
                    self._play_q.get(timeout=0.2)
                except Exception:
                    pass
            return
        self._stream_out = stream
        cv = None
        try:
            while self._media_on and not self._ended:
                # keep playback live: if we have fallen behind, throw away the
                # stale backlog instead of playing old audio late (this also
                # makes the other side's mute take effect almost instantly)
                try:
                    while self._play_q.qsize() > 6:
                        self._play_q.get_nowait()
                except Exception:
                    pass
                try:
                    data = self._play_q.get(timeout=0.2)
                except Exception:
                    continue
                if rate != self.SR and _audioop is not None:
                    try:                       # 16 kHz wire rate -> device rate
                        data, cv = _audioop.ratecv(data, 2, 1, self.SR, rate, cv)
                    except Exception:
                        continue
                elif rate != self.SR:
                    data = self._pcm_rate(data, self.SR, rate)
                if not self.speaker_on:
                    # speakerphone off (default) -> earpiece level; turning the
                    # speaker on leaves the samples untouched (full volume)
                    data = self._apply_gain(data, self.EARPIECE_GAIN)
                try:
                    stream.write(data)
                except Exception:
                    break
        finally:
            try:
                stream.stop_stream(); stream.close()
            except Exception:
                pass

    def _start_video(self):
        if not self._video_ready():
            # no capture support -> show the profile picture / avatar instead
            self._show_my_avatar()
            self._warn_camera_missing()
            return
        self._want_video = True
        self._vid_gen += 1
        gen = self._vid_gen
        t = threading.Thread(target=self._video_loop, args=(gen,), daemon=True)
        t.start()
        self._threads.append(t)
        # watchdog: if the camera never opens (no device / busy), say so instead
        # of leaving the "Camera" placeholder up for ever
        self.after(4500, lambda g=gen: self._camera_watchdog(g))

    def _camera_watchdog(self, gen):
        if self._ended or gen != self._vid_gen or self.camera_ok:
            return
        if self.video_on:
            # couldn't grab a frame -> fall back to the profile picture / avatar
            self._show_my_avatar()
            if not self._cam_warned:
                self._cam_warned = True
                self._warn("Camera not available",
                           "Could not open the webcam. Close any other app using "
                           "it (Zoom/Teams/Camera) and try again. On Windows also "
                           "allow camera access in Settings > Privacy and, if the "
                           "app still can't see it, run:  pip install --upgrade "
                           "opencv-python", kind='error')

    def _stop_video(self):
        self._want_video = False
        self._vid_gen += 1               # invalidate any running capture loop
        # The capture loop releases its own device the moment it notices
        # _want_video; releasing it underneath an in-flight read() is a native
        # crash waiting to happen, so only force it as a last resort.
        for _ in range(30):
            if self._cv is None:
                break
            time.sleep(0.02)
        if self._cv is not None:
            try:
                self._cv.release()
            except Exception:
                pass
            self._cv = None

    def _open_camera(self):
        """Open the webcam, preferring the fast DirectShow backend on Windows.

        cv2.VideoCapture(0) uses MSMF on Windows, which can sit there for half a
        minute before it hands over the first frame (looking exactly like 'the
        other side's camera never opens').  Each backend must actually deliver a
        frame before it is accepted.  We also try the other camera indexes in
        case the user flipped to a camera that does not exist.
        """
        if _cv2 is None:
            return None
        indices = [self.cam_index]
        for i in (0, 1):
            if i not in indices:
                indices.append(i)
        for idx in indices:
            candidates = []
            if os.name == 'nt' and hasattr(_cv2, 'CAP_DSHOW'):
                candidates.append((idx, _cv2.CAP_DSHOW))
            if hasattr(_cv2, 'CAP_ANY'):
                candidates.append((idx, _cv2.CAP_ANY))
            candidates.append((idx,))
            if os.name == 'nt' and hasattr(_cv2, 'CAP_MSMF'):
                candidates.append((idx, _cv2.CAP_MSMF))
            for args in candidates:
                cap = None
                try:
                    cap = _cv2.VideoCapture(*args)
                    if cap.isOpened():
                        cap.set(_cv2.CAP_PROP_FRAME_WIDTH, 320)
                        cap.set(_cv2.CAP_PROP_FRAME_HEIGHT, 240)
                        for _ in range(6):             # wait for a real frame
                            ok, frame = cap.read()
                            if ok and frame is not None:
                                self.cam_index = idx
                                return cap
                except Exception:
                    pass
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
        return None

    def _video_loop(self, gen):
        cap = self._open_camera()
        if cap is None:
            if gen == self._vid_gen:
                self.camera_ok = False
                # show the profile picture / avatar instead of a bare message
                self._sched(lambda: self._show_my_avatar())
                if self.video_on and not self._cam_warned:
                    self._cam_warned = True
                    self._warn("Camera not available",
                               "Could not open the webcam. Close any other app "
                               "using it (Zoom/Teams/Camera) and check Windows "
                               "camera privacy settings, then try again.",
                               kind='error')
            return
        self._cv = cap
        self.camera_ok = True
        last = 0.0
        while self._want_video and not self._ended and gen == self._vid_gen:
            try:
                ok, frame = cap.read()
            except Exception:
                ok = False
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            try:
                frame = _cv2.resize(frame, (320, 240))
            except Exception:
                continue
            if gen != self._vid_gen:
                break
            if self.video_on:
                self._queue_local(frame.copy())
                now = time.time()
                if now - last >= 0.085:
                    last = now
                    try:
                        ok2, buf = _cv2.imencode(
                            '.jpg', frame,
                            [int(_cv2.IMWRITE_JPEG_QUALITY), 55])
                        if ok2:
                            sio.emit('call_media', {
                                'call_id': self.call_id, 'k': 'v',
                                'from': self.app.my_username,
                                'd': base64.b64encode(buf.tobytes()).decode('ascii')})
                    except Exception:
                        pass
            else:
                time.sleep(0.05)
        try:
            cap.release()
        except Exception:
            pass
        if self._cv is cap:
            self._cv = None          # tell _stop_video the device is free

    def on_media(self, d):
        """Called (from the socket thread) for every relayed media packet."""
        if self._ended:
            return
        k = d.get('k')
        data = d.get('d')
        if not data:
            return
        if k == 'a':
            # queue it: playback only starts once the call is answered, so this
            # cannot be heard early - but the first packets are never dropped.
            # If the buffer is full, drop the OLDEST frame (keep live audio).
            pkt = base64.b64decode(data)
            try:
                self._play_q.put_nowait(pkt)
            except queue.Full:
                try:
                    self._play_q.get_nowait()
                    self._play_q.put_nowait(pkt)
                except Exception:
                    pass
            except Exception:
                pass
        elif k == 'v':
            who = d.get('from') or ''
            if who and who in self.peer_cams_off:
                return                       # their camera is off right now
            if who and who != self.remote_from:
                self.remote_from = who       # group calls: label who is on screen
                self._sched(lambda w=who: self._set_remote_label(w))
            # video is shown even before the callee answers (like the real app).
            # Coalesce frames so a fast stream never floods the Tk event queue.
            self._queue_remote(data)

    def _queue_remote(self, data):
        """Schedule the newest remote frame on the UI thread (drop older ones)."""
        self._pending_remote = data
        if not self._remote_scheduled:
            self._remote_scheduled = True
            self._sched(self._pump_remote)

    def _pump_remote(self):
        self._remote_scheduled = False
        data = self._pending_remote
        self._pending_remote = None
        if data is not None:
            self._show_remote(data)

    def _queue_local(self, frame):
        """Schedule the newest local frame on the UI thread (drop older ones)."""
        self._pending_local = frame
        if not self._local_scheduled:
            self._local_scheduled = True
            self._sched(self._pump_local)

    def _pump_local(self):
        self._local_scheduled = False
        frame = self._pending_local
        self._pending_local = None
        if frame is not None:
            self._show_local_frame(frame)

    def _set_remote_label(self, name):
        """Small corner tag naming the participant currently on screen."""
        if self.is_group:
            return
        cv = getattr(self, 'remote_cv', None)
        if cv is None or self._ended or not name:
            return
        try:
            cv.delete('who')
            cv.create_text(14, 14, text=name, fill='#e9edef',
                           font=("Segoe UI", 11, "bold"), anchor='nw', tags='who')
        except Exception:
            pass

    def on_remote_video(self, on, who='', pic='', color='#2c2c2c', name=''):
        """Somebody switched their camera on/off (1:1 or a group participant)."""
        if self._ended or self.kind != 'video':
            return
        who = who or self.peer_name
        if on:
            self.peer_cams_off.discard(who)
            if self.is_group:
                tile = self._ensure_remote_tile(who)
                if tile is not None:
                    try:
                        tile['canvas'].delete('rav')
                        tile['canvas'].delete('who')
                    except Exception:
                        pass
                if self.avatar_shown_for == who:
                    self.avatar_shown_for = ''
                self._remote_live = False
            else:
                self.remote_from = ''
                self._clear_remote_avatar()
        else:
            self.peer_cams_off.add(who)
            self._show_remote_avatar(name or who, pic, color)

    def on_peer_left(self, name, count=0):
        """A group participant hung up but the call carries on."""
        self.participants = max(1, int(count or 0))
        if self.is_group and name in self.remote_tiles:
            self._remove_remote_tile(name)
        try:
            self._sched(lambda: self.app.notify(
                "Call", "%s left the call" % (name or 'Someone'), kind='info'))
        except Exception:
            pass

    # ---------- camera on/off -> profile picture ----------
    def _show_my_avatar(self):
        """My profile picture in the small PIP (my camera is off)."""
        cv = getattr(self, 'local_cv', None)
        if cv is None:
            return
        try:
            cv.delete('all')
            d = 52
            self._draw_avatar_tagged(
                cv, d, self.app.my_username,
                getattr(self.app, 'my_color', '') or '#2c2c2c',
                getattr(self.app, 'my_pic', '') or '',
                'myav', 68 - d / 2, 40 - d / 2)
            cv.create_text(68, 84, text="Camera off", fill='#8696a0',
                           font=("Segoe UI", 8), tags='myav')
        except Exception:
            pass

    def _show_remote_avatar(self, name, pic='', color='#2c2c2c'):
        """The other side's profile picture (on their tile in a group call)."""
        if self.is_group:
            tile = self._ensure_remote_tile(name or self.peer_name)
            if tile is None or self._ended:
                return
            cv = tile['canvas']
        else:
            cv = getattr(self, 'remote_cv', None)
            if cv is None or self._ended:
                return
        try:
            cv.delete('all')
            w = max(cv.winfo_width(), 360)
            h = max(cv.winfo_height(), 280)
            d = max(90, min(w, h) // 3)
            self._draw_avatar_tagged(cv, d, name or self.peer_name, color, pic,
                                     'rav', (w - d) / 2, (h - d) / 2 - 16)
            label = ("%s's camera is off" % (name or self.peer_name))
            cv.create_text(w / 2, (h + d) / 2 + 2, text=label,
                           fill='#8696a0', font=("Segoe UI", 11), tags='rav')
            self.avatar_shown_for = name or self.peer_name
            self._remote_live = False
        except Exception:
            pass

    def _clear_remote_avatar(self):
        if self.is_group:
            name = self.avatar_shown_for
            if name and name in self.remote_tiles:
                try:
                    self.remote_tiles[name]['canvas'].delete('rav')
                    self.remote_tiles[name]['canvas'].delete('who')
                except Exception:
                    pass
            self.avatar_shown_for = ''
            self._remote_live = False
            return
        cv = getattr(self, 'remote_cv', None)
        if cv is None or self._ended:
            return
        try:
            cv.delete('rav')
            cv.delete('who')
            self.avatar_shown_for = ''
            self._remote_live = False
            self._draw_remote_placeholder()
        except Exception:
            pass

    def _clear_local(self, text='Camera'):
        cv = getattr(self, 'local_cv', None)
        if cv is None:
            return
        try:
            cv.delete('frame')
            cv.delete('ph')
            cv.create_text(68, 51, text=text, fill='#8696a0',
                           font=("Segoe UI", 10), tags='ph')
        except Exception:
            pass

    def _show_local_frame(self, frame_bgr):
        cv = getattr(self, 'local_cv', None)
        if self._ended or cv is None or Image is None:
            return
        try:
            rgb = _cv2.cvtColor(frame_bgr, _cv2.COLOR_BGR2RGB)
            self._draw_on(cv, Image.fromarray(rgb), 'local')
        except Exception:
            pass

    def _show_remote(self, b64data):
        # Only Pillow is strictly required to *display* the other side's video.
        # OpenCV/numpy are used for the fast path, but a peer that only has
        # Pillow installed must still be able to see the incoming stream.
        if self._ended or Image is None:
            return
        if self.is_group:
            tile = self._ensure_remote_tile(self.remote_from or self.peer_name)
            if tile is None:
                return
            cv = tile['canvas']
        else:
            cv = getattr(self, 'remote_cv', None)
            if cv is None:
                return
        try:
            raw = base64.b64decode(b64data)
            pil = None
            if _cv2 is not None and _np is not None:
                arr = _np.frombuffer(raw, _np.uint8)
                frame = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
                if frame is not None:
                    rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
                    pil = Image.fromarray(rgb)
            if pil is None:                        # Pillow-only decoder fallback
                pil = Image.open(io.BytesIO(raw))
                pil.load()
            try:
                cv.delete('ph')
                cv.delete('rav')
            except Exception:
                pass
            self._remote_live = True
            self._draw_on(cv, pil, 'remote')
        except Exception:
            pass

    def _draw_on(self, canvas, pil_img, key):
        try:
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w < 4 or h < 4:
                w, h = canvas.winfo_reqwidth(), canvas.winfo_reqheight()
            if w < 4 or h < 4:
                w, h = 320, 240
            iw, ih = pil_img.size
            scale = min(w / iw, h / ih)
            nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
            photo = ImageTk.PhotoImage(pil_img.resize((nw, nh)))
            self._photo_ref[key] = photo          # keep a reference (avoid GC)
            canvas.delete('frame')
            canvas.create_image(w / 2, h / 2, image=photo, tags='frame')
            canvas.tag_raise('frame')
        except Exception:
            pass

class CallsMixin:

    # ---- Calls view (middle panel) ----
    def record_call(self, name, kind, u=None, outcome='', dur=0):
        """Add a call entry at the current time (newest appears on top).

        The entry is also pushed to the server so the Calls tab survives a
        restart / reconnect (it comes back inside `restore_state`).
        """
        u = u or {}
        now = datetime.now()
        entry = {
            'name': name,
            'avatar': (u.get('avatar') or (name[:1] if name else 'U')).upper(),
            'color': u.get('color', '#2c2c2c'),
            'kind': kind,
            'time': now.strftime("%H:%M"),
            'day': now.strftime("%Y-%m-%d"),
            'outcome': outcome,
            'dur': dur,
        }
        self.call_log.insert(0, entry)      # newest on top
        try:
            if sio.connected:
                sio.emit('record_call', {
                    'me': self.my_username,
                    'name': name, 'kind': kind,
                    'avatar': entry['avatar'], 'color': entry['color'],
                    'outcome': outcome, 'dur': dur,
                    'time': entry['time'], 'day': entry['day'],
                })
        except Exception:
            pass
        if self.current_view == 'calls':
            self.show_calls_inline()

    def _load_call_history(self, calls):
        """Rebuild the Calls tab from the server's stored history."""
        if not isinstance(calls, list):
            return
        loaded = []
        for c in calls:
            if not isinstance(c, dict):
                continue
            name = str(c.get('peer') or c.get('name') or '')
            if not name:
                continue
            loaded.append({
                'name': name,
                'avatar': (c.get('peer_avatar') or c.get('avatar')
                           or (name[:1] if name else 'U')).upper(),
                'color': c.get('peer_color') or c.get('color') or '#2c2c2c',
                'kind': 'video' if c.get('kind') == 'video' else 'voice',
                'time': c.get('time') or '',
                'outcome': c.get('outcome') or '',
                'dur': int(c.get('dur') or 0),
            })
        if not loaded:
            return
        self.call_log = loaded + [c for c in self.call_log
                                  if c not in loaded]
        if self.current_view == 'calls':
            self.show_calls_inline()

    def _on_call_recorded(self, d):
        """Another session of *this* user recorded a call -> keep Calls in sync.

        The client already inserts its own entry when a call ends, so this is
        de-duplicated on (peer, time, day); it mainly covers a second device
        logged in as the same user.
        """
        try:
            name = str(d.get('peer') or d.get('name') or '')
            if not name:
                return
            kind = 'video' if d.get('kind') == 'video' else 'voice'
            t, day = str(d.get('time') or ''), str(d.get('day') or '')
            for c in getattr(self, 'call_log', []):
                if (str(c.get('name') or '') == name
                        and str(c.get('time') or '') == t
                        and (c.get('kind') or 'voice') == kind):
                    return
            log = getattr(self, 'call_log', None)
            if log is None:
                log = self.call_log = []
            log.insert(0, {
                'name': name,
                'avatar': (d.get('peer_avatar') or d.get('avatar')
                           or name[:1]).upper(),
                'color': d.get('peer_color') or d.get('color') or '#2c2c2c',
                'kind': kind,
                'time': t, 'day': day,
                'outcome': str(d.get('outcome') or ''),
                'dur': int(d.get('dur') or 0),
            })
            del log[300:]
            if self.current_view == 'calls':
                self.show_calls_inline()
        except Exception:
            pass

    def show_calls_inline(self):
        for w in self.cii.winfo_children():
            w.destroy()
        if not self.call_log:
            tk.Label(self.cii, text=ICON["phone"], bg='#1e1e1e', fg='#2c2c2c',
                     font=(self.icon_family, 48)).pack(pady=(70, 10))
            tk.Label(self.cii, text="No calls yet", bg='#1e1e1e', fg='#e9edef',
                     font=("Segoe UI", 14, "bold")).pack()
            tk.Label(self.cii, text="Start a call from any chat header",
                     bg='#1e1e1e', fg='#8696a0', font=("Segoe UI", 11)).pack(pady=(4, 0))
            self._bind_mousewheel_recursive(self.cii, self.ccv)
            self._theme_subtree(self.cii)
            self._queue_scrollregion(self.ccv)
            return
        for c in self.call_log:
            self.call_item(c)
        self._bind_mousewheel_recursive(self.cii, self.ccv)
        self._theme_subtree(self.cii)
        self._queue_scrollregion(self.ccv)

    def call_item(self, c):
        fr = tk.Frame(self.cii, bg='#1e1e1e')
        fr.pack(fill=tk.X, padx=4, pady=1)

        av = tk.Canvas(fr, width=40, height=40, bg='#1e1e1e',
                       highlightthickness=0, bd=0)
        av.pack(side=tk.LEFT, padx=(8, 10), pady=8)
        self._round_rect(av, 0, 0, 40, 40, 12, c.get('color', '#2c2c2c'))
        av.create_text(20, 20, text=c.get('avatar', 'U'), fill="white",
                       font=("Segoe UI", 14, "bold"))

        inf = tk.Frame(fr, bg='#1e1e1e')
        inf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        tk.Label(inf, text=c['name'], bg='#1e1e1e', fg='#e9edef',
                 font=("Segoe UI", 13, "bold"), anchor="w").pack(fill=tk.X)

        meta = tk.Frame(inf, bg='#1e1e1e')
        meta.pack(fill=tk.X)
        oc = (c.get('outcome') or '').strip()
        bad = any(w in oc for w in ('Declined', 'Missed', 'No answer'))
        arrow = ICON["video"] if c.get('kind') == 'video' else ICON["phone"]
        tk.Label(meta, text=arrow, bg='#1e1e1e',
                 fg=('#f15c6d' if bad else '#8696a0'),
                 font=(self.icon_family, 10)).pack(side=tk.LEFT)
        kind_lbl = "Video call" if c.get('kind') == 'video' else "Voice call"
        if oc.startswith('Call ended') and c.get('dur'):
            label = "%s \u2022 %s" % (kind_lbl, CallWindow._fmt_elapsed(c.get('dur')))
        elif oc:
            label = "%s \u2022 %s" % (kind_lbl, oc)
        else:
            label = "Outgoing %s" % kind_lbl.lower()
        tk.Label(meta, text=label, bg='#1e1e1e',
                 fg=('#f15c6d' if bad else '#8696a0'),
                 font=("Segoe UI", 11), anchor="w").pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(fr, text=self._fmt_time(c.get('time', '')), bg='#1e1e1e', fg='#8696a0',
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=10)

    # ---- live calls (voice / video) ----
    def _peer_online(self, name, sid=None):
        """Is the named contact currently connected to the server?

        The server's live client list is authoritative; a contact whose sid we
        still remember from an old chat is NOT online until it appears here.
        """
        try:
            for c in getattr(self, 'clients', []) or []:
                if c.get('sid') == self.my_sid:
                    continue
                if (sid and c.get('sid') == sid) or (name and c.get('username') == name):
                    return True
        except Exception:
            pass
        for p in getattr(self, '_peers', []) or []:
            if p.get('name') == name and not p.get('is_server'):
                return (p.get('status') or '').strip().lower() in ('active', 'online')
        return False

    def _group_pic(self, gid):
        for p in getattr(self, '_peers', []) or []:
            if p.get('gid') == gid:
                return p.get('pic', '') or ''
        return ''

    def _group_online_members(self, gid, me):
        """Best-effort list of group members currently connected (client side)."""
        members = []
        for p in getattr(self, '_peers', []) or []:
            if p.get('gid') == gid:
                members = list(p.get('members') or [])
                break
        if not members:
            # fall back to whatever peers claim to belong to this group
            members = [p.get('name') for p in getattr(self, '_peers', []) or []
                       if p.get('gid') == gid and p.get('name')]
        return [m for m in members if m and m != me and self._peer_online(m)]

    def start_call(self, kind):
        """Open the call window and ring the current chat (1:1 or a group)."""
        if getattr(self, '_call', None) is not None:
            self.show_toast("Ek call pehle se chal rahi hai")
            return
        name = self.current_chat_name or 'Unknown'
        call_id = uuid.uuid4().hex[:10]

        if self.current_chat_type == 'group':
            gid = self.current_chat_gid
            if not gid:
                self.notify("Call", "Group info nahi mili", kind='info')
                return
            peer = {
                'name': name,
                'sid': None,
                'avatar': self.current_chat_avatar or (name[:1] or 'U').upper(),
                'color': self.current_chat_color or '#2c2c2c',
                'pic': self._group_pic(gid),
            }
            live = self._group_online_members(gid, self.my_username)
            win = CallWindow(self, peer, kind, 'out', call_id,
                             online=bool(live), group=gid, group_name=name)
            win.from_name = self.my_username
            self._call = win
            try:
                sio.emit('start_call', {'to': name, 'kind': kind,
                                        'from': self.my_username,
                                        'call_id': call_id, 'group': gid})
            except Exception:
                pass
            # if nobody is really online the server sends call_offline and the
            # user is told then (our local member list can be incomplete)
            return

        peer = {
            'name': name,
            'sid': self.current_chat_sid,
            'avatar': self.current_chat_avatar or (name[:1] or 'U').upper(),
            'color': self.current_chat_color or '#2c2c2c',
            'pic': self._peer_pic(name),
        }
        online = self._peer_online(name, peer.get('sid'))
        win = CallWindow(self, peer, kind, 'out', call_id, online=online)
        self._call = win
        try:
            sio.emit('start_call', {'to': name, 'to_sid': peer.get('sid'),
                                    'kind': kind, 'from': self.my_username,
                                    'call_id': call_id})
        except Exception:
            pass

    def _on_incoming_call(self, d):
        if getattr(self, '_call', None) is not None:
            # already busy -> politely decline the new caller
            try:
                sio.emit('call_reject', {'call_id': d.get('call_id'),
                                         'from': self.my_username})
            except Exception:
                pass
            return
        gid = d.get('group') or ''
        gname = d.get('group_name') or ''
        name = d.get('from') or 'Unknown'
        if gid:
            gpeer = None
            for p in getattr(self, '_peers', []):
                if p.get('gid') == gid:
                    gpeer = p
                    break
            peer = {'name': gname or 'Group',
                    'sid': d.get('from_sid'),
                    'avatar': ((gname or 'G')[:1]).upper(),
                    'color': (gpeer or {}).get('color', '#2c2c2c'),
                    'pic': (gpeer or {}).get('pic', '') or d.get('group_avatar', '')}
        else:
            peer = {'name': name,
                    'sid': d.get('from_sid'),
                    'avatar': (name[:1] or 'U').upper(),
                    'color': '#2c2c2c',
                    'pic': d.get('avatar') or ''}
        call_id = d.get('call_id') or uuid.uuid4().hex[:10]
        win = CallWindow(self, peer, d.get('kind', 'voice'), 'in', call_id,
                         group=gid, group_name=gname)
        win.from_name = name
        self._call = win

    def _on_call_accepted(self, d):
        w = getattr(self, '_call', None)
        if w is None or d.get('call_id') != w.call_id:
            return
        try:
            w.participants = max(2, int(d.get('count') or 2))
        except Exception:
            w.participants = 2
        if w.connected:
            # a group call: somebody else joined -> refresh the counter
            try:
                w.status_lbl.configure(text=w._live_status_text())
            except Exception:
                pass
            return
        w.on_accepted()

    def _on_call_rejected(self, d):
        w = getattr(self, '_call', None)
        if w is None or d.get('call_id') != w.call_id:
            return
        if w.is_group:
            # one invitee said no - the rest of the group call carries on
            self.notify("Group call",
                        "%s declined" % (d.get('by') or 'Someone'), kind='info')
            return
        w.on_rejected()

    def _on_call_ended(self, d):
        w = getattr(self, '_call', None)
        if w is not None and d.get('call_id') == w.call_id:
            w.on_remote_end()

    def _on_call_peer_left(self, d):
        w = getattr(self, '_call', None)
        if w is None or d.get('call_id') != w.call_id:
            return
        w.on_peer_left(d.get('by') or 'Someone', d.get('count') or 0)

    def _on_call_video(self, d):
        w = getattr(self, '_call', None)
        if w is None or d.get('call_id') != w.call_id:
            return
        w.on_remote_video(bool(d.get('on')), who=d.get('from') or '',
                          pic=d.get('pic') or '',
                          color=d.get('color') or '#2c2c2c',
                          name=d.get('name') or '')

    def _on_call_upgraded(self, d):
        w = getattr(self, '_call', None)
        if w is not None and d.get('call_id') == w.call_id:
            w.on_peer_upgraded()

    def _on_call_offline(self, d):
        """Server says the callee is not connected: keep it as 'Calling…'."""
        w = getattr(self, '_call', None)
        if w is None or d.get('call_id') != w.call_id or w.connected:
            return
        w.online = False
        try:
            w.status_lbl.configure(text="No members online" if w.is_group
                                   else "Calling\u2026")
        except Exception:
            pass
        if w.is_group:
            self.notify("Group call", "Koi member online nahi hai", kind='info')

    def _call_end_all(self):
        """Called when the app shuts down: end any call cleanly."""
        w = getattr(self, '_call', None)
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass
            self._call = None

    # ---- call ringtone ----
    def choose_call_ringtone_file(self):
        path = filedialog.askopenfilename(
            title="Choose call ringtone",
            filetypes=[("Audio", "*.wav *.mp3 *.m4a *.wma *.aac *.ogg"),
                       ("WAV", "*.wav"), ("All files", "*.*")])
        if not path:
            return
        # staged only: the live player is untouched until "Save Settings"
        self.ct_custom_path = path
        label = "Custom: " + os.path.basename(path)
        try:
            vals = list(self.ct_box.cget("values"))
        except Exception:
            vals = []
        if label not in vals:
            vals.insert(max(0, len(vals) - 2), label)
            self.ct_box.configure(values=vals)
        self.ct_var.set(label)
        self._settings_dirty()
        self.show_toast("Call ringtone selected \u2014 Save Settings to apply")

    def on_call_ringtone_pick(self, *_a):
        label = self.ct_var.get()
        if label == "Custom…":
            self.choose_call_ringtone_file()
            return
        self._settings_dirty()
        self._preview_ringtone_choice(self.call_ringtone, label, self.ct_custom_path,
                                      self._wget('ct_vol_scale', self.call_ringtone.volume))

    def preview_call_ringtone(self):
        self._preview_ringtone_choice(self.call_ringtone, self.ct_var.get(),
                                      self.ct_custom_path,
                                      self._wget('ct_vol_scale', self.call_ringtone.volume))

    def on_call_volume(self, value):
        try:
            v = int(float(value))
        except Exception:
            return
        try:
            self.ct_vol_lbl.configure(text=f"{v}%")
        except Exception:
            pass
        self._settings_dirty()

    def play_call_ringtone(self):
        """Called when a call starts (outgoing or incoming)."""
        if self.call_ringtone.path:
            self.call_ringtone.play()

    def _is_server_chat(self):
        """True when the open chat is the dashboard's 'Server' contact."""
        cid = getattr(self, 'current_chat_id', None)
        for u in getattr(self, '_peers', []):
            if u.get('id') == cid:
                return bool(u.get('is_server')) or u.get('name') == 'Server'
        return self.current_chat_name == 'Server'

    def _update_call_buttons_state(self):
        """Voice/video calls are disabled for the Server chat."""
        try:
            dis = self._is_server_chat()
            for t in ("Video Call", "Voice Call"):
                b = getattr(self, 'hbtns', {}).get(t)
                if b is not None:
                    b.set_enabled(not dis)
        except Exception:
            pass
