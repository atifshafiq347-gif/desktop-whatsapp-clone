# client_chat.py — The conversation pane: message bubbles, files, voice notes, search,
# reactions, reply/forward.
from client_core import *


# coloured sender names for group chats (deterministic per name, so the same
# person always gets the same colour)
_GROUP_SENDER_COLORS = [
    "#e91e63", "#9c27b0", "#3f51b5", "#2196f3", "#00bcd4",
    "#4caf50", "#ff9800", "#ff5722", "#795548", "#607d8b",
    "#f44336", "#009688", "#673ab7", "#03a9f4",
]


class ChatMixin:

    def _quote_box(self, msg, wrap_w):
        """(sender, lines, height, content_width) for a message's reply quote."""
        if not msg:
            return '', [], 0, 0
        sender = msg.get('reply_sender') or ''
        text = msg.get('reply_text') or ''
        if not sender and not text:
            return '', [], 0, 0
        fq = tkfont.Font(font=self.QUOTE_FONT)
        fqn = tkfont.Font(font=self.QUOTE_NAME)
        lines = self._wrap_text(text, fq, max(80, wrap_w)) if text else []
        h = (len(lines) * fq.metrics("linespace") + 14 +
             (fqn.metrics("linespace") if sender else 0))
        w = max([fqn.measure(sender)] + [fq.measure(l) for l in lines] + [10]) + 26
        return sender, lines, h, w

    def _draw_quote(self, cv, msg, sender, lines, x, y, w, h, typ, jump=True):
        """Draw the quote block; the whole block is one clickable tag."""
        mid = (msg.get('reply_to') or '') if msg else ''
        if typ == 'sent':
            box_bg, bar, name_col, txt_col = '#cfe9c4', '#0a7c3e', '#0a7c3e', '#3b4a54'
        else:
            box_bg, bar, name_col, txt_col = '#2a3942', '#53bdeb', '#53bdeb', '#9aa8b0'
        tag = ('q_' + str(mid)) if mid else 'q_none'
        self._round_rect(cv, x, y, x + w, y + h, 6, box_bg, tags=(tag,))
        cv.create_rectangle(x + 3, y + 4, x + 6, y + h - 4, fill=bar, outline='',
                            tags=(tag,))
        fq = tkfont.Font(font=self.QUOTE_FONT)
        fqn = tkfont.Font(font=self.QUOTE_NAME)
        ty = y + 7
        if sender:
            cv.create_text(x + 13, ty, text=sender, anchor='nw', fill=name_col,
                           font=self.QUOTE_NAME, tags=(tag,))
            ty += fqn.metrics("linespace")
        for ln in lines:
            cv.create_text(x + 13, ty, text=ln, anchor='nw', fill=txt_col,
                           font=self.QUOTE_FONT, tags=(tag,))
            ty += fq.metrics("linespace")
        if mid and jump:
            cv.tag_bind(tag, '<Button-1>', lambda e, m=mid: self._jump_to_msg(m))
            try:
                cv.tag_bind(tag, '<Enter>', lambda e: cv.configure(cursor='hand2'))
                cv.tag_bind(tag, '<Leave>', lambda e: cv.configure(cursor=''))
            except Exception:
                pass

    def _jump_to_msg(self, mid):
        """Scroll to the message a reply points at and flash it."""
        if not mid:
            return
        w = getattr(self, '_bubble_widgets', {}).get(mid)
        if w is None or not w.winfo_exists():
            self.show_toast("Original message is not visible here")
            return
        try:
            self.mcv.update_idletasks()
            total = max(1, self.mi.winfo_height())
            self.mcv.yview_moveto(max(0.0, min(1.0, (w.winfo_y() - 90) / total)))
        except Exception:
            pass
        self._flash_bubble(mid)

    def _flash_bubble(self, mid):
        """Briefly paint the bubble yellow so the eye can find it."""
        info = getattr(self, '_bubble_rects', {}).get(mid)
        if not info:
            return
        cv, ids = info
        try:
            orig = cv.itemcget(ids[0], 'fill')
        except Exception:
            return

        def paint(col):
            for i in ids:
                try:
                    cv.itemconfigure(i, fill=col)
                except Exception:
                    pass
        paint('#ffe27a')
        try:
            self.root.after(240, lambda: paint('#ffd54f'))
            self.root.after(900, lambda: paint(orig))
        except Exception:
            paint(orig)

    def open_chat(self, u):
        self.current_chat_id = u['id']
        self.current_chat_name = u['name']
        self.current_chat_type = u.get('type', 'single')
        self.current_chat_color = u.get('color', '#2c2c2c')
        self.current_chat_avatar = u.get('avatar', 'U')
        self.current_chat_sid = u.get('sid')
        self.current_chat_gid = u.get('gid')
        self.current_status = u.get('status', 'active')

        # a preview left open for the previous chat must not leak into this one
        self._discard_file_preview()
        # a reply / history filter also belongs to the previous chat only
        self._cancel_reply()
        self.history_period = 'All'

        # opening a chat clears its unread badge (bubble disappears) - in place
        if u.get('unread'):
            u['unread'] = 0
            self._set_row_unread(u['id'], 0)
        # move the active highlight without rebuilding the whole list
        self._set_active_row(u['id'])

        self.ha.delete("all")
        self._draw_avatar(self.ha, 40, 12, self.current_chat_name,
                          self.current_chat_color, u.get('pic', ''))
        # truncate long names so they never overflow over the action icons
        disp = self.current_chat_name
        if len(disp) > 20:
            disp = disp[:19] + "…"
        self.cn.configure(text=disp)

        if self.current_chat_type == 'group':
            self.sd.configure(fg='#25d366')
            self.st.configure(text=self._group_members_line(u), fg='#8696a0')
        else:
            self._apply_header_status(self.current_status)

        # calling the dashboard "Server" makes no sense -> grey those buttons
        self._update_call_buttons_state()

        self.re.pack_forget()
        self.ra.pack(fill=tk.BOTH, expand=True)

        # fresh local copy of this chat's messages (used by the in-chat search)
        self._current_msgs = []
        self._reset_chat_search()

        # load only this chat's messages (do NOT reload the whole chat list)
        if self.current_chat_type == 'group':
            sio.emit('get_messages', {'me': self.my_username, 'group': self.current_chat_gid})
        else:
            sio.emit('get_messages', {'me': self.my_username, 'peer': self.current_chat_name})
            # opening the chat means we've read it -> sender's ticks turn green
            sio.emit('mark_read', {'me': self.my_username, 'peer': self.current_chat_name})
        self.mi_t.focus()
        self._save_ui_state()

    # ============================================================
    # MESSAGES (Right panel)
    # ============================================================
    def _wrap_text(self, text, font, maxw):
        """Wrap text (honouring explicit newlines) so each line fits maxw px."""
        out = []
        for para in text.split('\n'):
            if para == '':
                out.append('')
                continue
            cur = ''
            for word in para.split(' '):
                trial = word if not cur else cur + ' ' + word
                if font.measure(trial) <= maxw or not cur:
                    cur = trial
                else:
                    out.append(cur)
                    cur = word
            out.append(cur)
        return out or ['']

    def _fmt_time(self, ts):
        """Format a stored 'HH:MM' timestamp as 24-hour or 12-hour (settings)."""
        if not ts:
            return ts or ''
        if self.time_24h:
            return ts
        try:
            parts = str(ts).split(':')
            h, m = int(parts[0]), int(parts[1])
            ap = 'AM' if h < 12 else 'PM'
            h12 = h % 12 or 12
            return f"{h12}:{m:02d} {ap}"
        except Exception:
            return ts

    def render_msgs(self, d):
        for w in self.mi.winfo_children():
            w.destroy()
        self._bubble_labels = {}
        self._bubble_widgets = {}
        self._bubble_rects = {}
        tk.Label(self.mi, text="Today", bg='#121212', fg='#8696a0', font=("Segoe UI", 10)).pack(pady=10)
        q = getattr(self, '_search_q', '') or ""
        focus = getattr(self, 'chat_focus', None)
        for m in self._filter_history(d.get('messages', [])):
            if m.get('deleted'):
                self.bubble("[Message deleted]", m.get('type', 'received'),
                            m.get('time', ''), m.get('status', 'delivered'),
                            mid=m.get('mid'), msg=m, deleted=True)
            elif (m.get('kind') or 'text') != 'text':
                self.file_bubble(m, m.get('type', 'received'), m.get('time', ''),
                                 m.get('status', 'delivered'), mid=m.get('mid'),
                                 hl=q, focus=(m.get('mid') == focus))
            else:
                self.bubble(m.get('text', ''), m.get('type', 'received'), m.get('time', ''),
                            m.get('status', 'delivered'), highlight=q, mid=m.get('mid'),
                            msg=m, focus=(m.get('mid') == focus))
        # wheel over the messages panel (and its bubbles) scrolls ONLY this panel
        self._bind_mousewheel_recursive(self.mi, self.mcv)
        self._theme_subtree(self.mi)
        self._queue_scrollregion(self.mcv)
        self.mcv.update_idletasks()
        self.mcv.yview_moveto(1.0)

    def _set_tick(self, mid, status):
        """Update one message's delivery tick: sent ✓, delivered ✓✓, read ✓✓(green)."""
        lbl = self._bubble_labels.get(mid)
        if lbl is None:
            return
        bgmap, fgmap = self.theme.maps_for('Light')
        light = getattr(self, 'theme_name', 'Dark') == 'Light'

        def col(c):
            return fgmap.get(c, c) if light else c
        try:
            if status == 'read':
                lbl.configure(text="\u2713\u2713", fg=col('#53bdeb'))
            elif status == 'delivered':
                lbl.configure(text="\u2713\u2713", fg=col('#667781'))
            elif status == 'blocked':
                lbl.configure(text="\u2717", fg=col('#ff5c5c'))
            elif status == 'undelivered':
                lbl.configure(text="\u2713", fg=col('#e3b341'))
            else:
                lbl.configure(text="\u2713", fg=col('#667781'))
        except Exception:
            pass

    # ---- in-chat search (right panel header search icon) ----
    def toggle_chat_search(self):
        """Open / close the in-chat search bar under the chat header."""
        if getattr(self, 'chat_search_f', None) is None:
            self._build_chat_search()
        if self.chat_search_f.winfo_ismapped():
            self.hide_chat_search()
        else:
            self.chat_search_f.pack(fill=tk.X, after=self._chat_header)
            try:
                self.cs_entry.focus_set()
            except Exception:
                pass

    def _build_chat_search(self):
        """The search bar: [🔍] [query] 1/5 [▲] [▼] [✕] - like WhatsApp."""
        f = tk.Frame(self.ra, bg='#121212', height=48)
        f.pack_propagate(False)
        self.chat_search_f = f
        box = RoundedBox(f, radius=14, bg='#2c2c2c', parent_bg='#121212')
        box.pack(fill=tk.BOTH, expand=True, padx=12, pady=7)
        tk.Label(box, text=ICON["search"], bg='#2c2c2c', fg='#8696a0',
                 font=(self.icon_family, 12)).pack(side=tk.LEFT, padx=(10, 2))
        self.cs_entry = tk.Entry(box, bg='#2c2c2c', bd=0, font=("Segoe UI", 11),
                                 fg='#e9edef', insertbackground='#25d366',
                                 relief=tk.FLAT, highlightthickness=0)
        self.cs_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        self.cs_entry.bind('<KeyRelease>', lambda e: self.do_chat_search())
        self.cs_entry.bind('<Return>', lambda e: self.search_step(1))
        self.cs_entry.bind('<Escape>', lambda e: self.hide_chat_search())
        # "1/5" match counter
        self.cs_count = tk.Label(box, text="", bg='#2c2c2c', fg='#8696a0',
                                 font=("Segoe UI", 9, "bold"))
        self.cs_count.pack(side=tk.LEFT, padx=(0, 4))
        for icon, cmd, tip in ((ICON["chevup"], lambda: self.search_step(-1), "Previous match"),
                               (ICON["chevdn"], lambda: self.search_step(1), "Next match")):
            b = RoundedButton(box, icon=icon, icon_font=(self.icon_family, 10),
                              command=cmd, parent_bg='#2c2c2c',
                              width=26, height=26, radius=13,
                              active_bg='#2c2c2c', active_fg='#aebac1')
            b.set_active(True)
            b.pack(side=tk.LEFT, padx=1)
            try:
                b.info = tip
            except Exception:
                pass
        cb = RoundedButton(box, icon=ICON["close"], icon_font=(self.icon_family, 10),
                           command=self.hide_chat_search, parent_bg='#2c2c2c',
                           width=26, height=26, radius=13,
                           active_bg='#2c2c2c', active_fg='#aebac1')
        cb.set_active(True)
        cb.pack(side=tk.LEFT, padx=(1, 8))
        self._theme_subtree(f)

    def hide_chat_search(self):
        """Close the bar and drop every highlight."""
        self._search_q = ""
        self.chat_matches = []
        self.chat_idx = -1
        self.chat_focus = None
        if getattr(self, 'chat_search_f', None) is None:
            return
        self.chat_search_f.pack_forget()
        if getattr(self, 'cs_entry', None) is not None:
            self.cs_entry.delete(0, tk.END)
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})

    def _reset_chat_search(self):
        self._search_q = ""
        self.chat_matches = []
        self.chat_idx = -1
        self.chat_focus = None
        if getattr(self, 'chat_search_f', None) is not None and \
                self.chat_search_f.winfo_ismapped():
            self.chat_search_f.pack_forget()
        if getattr(self, 'cs_entry', None) is not None:
            self.cs_entry.delete(0, tk.END)

    @staticmethod
    def _msg_search_text(m):
        """Everything a query may match inside one message."""
        parts = [str(m.get('text') or '')]
        if (m.get('kind') or 'text') != 'text':
            parts.append(os.path.basename(str(m.get('file_name') or '')))
        if (m.get('kind') or 'text') != 'text':
            parts.append(str(m.get('file_kind') or ''))
        parts.append(str(m.get('reply_text') or ''))
        return ' '.join(parts).lower()

    def do_chat_search(self):
        """Highlight every match in the open chat (all messages stay visible)."""
        q = self.cs_entry.get().strip()
        self._search_q = q.lower()
        msgs = getattr(self, '_current_msgs', [])
        if not self._search_q:
            self.chat_matches = []
            self.chat_idx = -1
            self.chat_focus = None
        else:
            self.chat_matches = [m.get('mid') for m in msgs
                                 if self._search_q in self._msg_search_text(m)]
            # keep the previous position when the query is just refined
            self.chat_idx = 0 if self.chat_matches else -1
            self.chat_focus = self.chat_matches[0] if self.chat_matches else None
        self._update_search_count()
        self.render_msgs({'messages': msgs})
        if self.chat_focus:
            self._scroll_to_msg(self.chat_focus)

    def search_step(self, delta):
        """▲ / ▼ : walk through the matches."""
        if not self.chat_matches:
            return "break"
        self.chat_idx = (self.chat_idx + delta) % len(self.chat_matches)
        self.chat_focus = self.chat_matches[self.chat_idx]
        self._update_search_count()
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})
        self._scroll_to_msg(self.chat_focus)
        return "break"

    def _update_search_count(self):
        lbl = getattr(self, 'cs_count', None)
        if lbl is None:
            return
        if not self._search_q:
            txt = ""
        elif not self.chat_matches:
            txt = "0/0"
        else:
            txt = "%d/%d" % (self.chat_idx + 1, len(self.chat_matches))
        try:
            lbl.configure(text=txt, fg='#8696a0' if self.chat_matches else '#ff5c5c')
        except Exception:
            pass

    def _scroll_to_msg(self, mid):
        """Bring one message into view (no flash) - used by search navigation."""
        w = getattr(self, '_bubble_widgets', {}).get(mid)
        if w is None or not w.winfo_exists():
            return
        try:
            self.mcv.update_idletasks()
            total = max(1, self.mi.winfo_height())
            self.mcv.yview_moveto(max(0.0, min(1.0, (w.winfo_y() - 90) / total)))
        except Exception:
            pass

    def _draw_hl_line(self, cv, x, y, text, fspec, qlow, fg,
                      hl_idle='#ffe97a', hl_focus='#ffc400', hl_fg='#0b1a0e',
                      focus=False):
        """Draw one line of text, highlighting each occurrence of `qlow`.

        `qlow` must already be lower-case.  The rest of the line keeps `fg`, so
        a highlighted message still reads like a normal bubble.
        """
        if not text:
            return
        low = text.lower()
        if not qlow or qlow not in low:
            cv.create_text(x, y, text=text, fill=fg, font=fspec, anchor="nw")
            return
        f = tkfont.Font(font=fspec)
        lh = f.metrics("linespace")
        strip = hl_focus if focus else hl_idle
        cx, pos, n = x, 0, len(qlow)
        while True:
            k = low.find(qlow, pos)
            if k < 0:
                tail = text[pos:]
                if tail:
                    cv.create_text(cx, y, text=tail, fill=fg, font=fspec, anchor="nw")
                return
            if k > pos:
                seg = text[pos:k]
                cv.create_text(cx, y, text=seg, fill=fg, font=fspec, anchor="nw")
                cx += f.measure(seg)
            seg = text[k:k + n]
            w = f.measure(seg)
            cv.create_rectangle(cx - 1, y - 1, cx + w + 1, y + lh + 1,
                                fill=strip, outline='')
            cv.create_text(cx, y, text=seg, fill=hl_fg, font=fspec, anchor="nw")
            cx += w
            pos = k + n

    def bubble(self, text, typ, ts, status="delivered", highlight="", mid=None,
               msg=None, deleted=False, focus=False):
        """A rounded message bubble drawn on a canvas (real border-radius)."""
        font = tkfont.Font(font=("Segoe UI", 12))
        fmeta = tkfont.Font(font=("Segoe UI", 9))
        femoji = tkfont.Font(font=("Segoe UI Emoji", 11))
        fsender = tkfont.Font(font=("Segoe UI", 9, "bold"))
        maxw, padx, pady, radius = 320, 12, 8, 10
        ok = bool(msg) and not deleted
        # in a group chat, show who sent each incoming message (coloured name)
        is_group_chat = (getattr(self, 'current_chat_type', '') == 'group')
        sender_name = ''
        if ok and typ != 'sent' and is_group_chat:
            sender_name = (msg.get('sender') or '').strip()
        name_lh = (fsender.metrics("linespace") + 2) if sender_name else 0
        # small muted markers below the quote: forwarded / pinned / starred
        meta_lines = []
        if ok:
            if msg.get('forwarded'):
                meta_lines.append("\u21aa Forwarded")
            if msg.get('pinned'):
                meta_lines.append("\U0001F4CC Pinned")
            if msg.get('starred'):
                meta_lines.append("\u2605 Starred")
        # a real reply quote block (clickable -> jumps to the original message)
        q_sender, q_lines, qh, qw = self._quote_box(msg if ok else None, maxw - 40)

        lines = ["[Message deleted]"] if deleted else self._wrap_text(text, font, maxw)
        lh = font.metrics("linespace")
        mlh = fmeta.metrics("linespace")

        # emoji reactions shown as a small pill under the text
        reactions = {}
        if ok and isinstance(msg.get('reactions'), dict):
            reactions = {k: v for k, v in msg['reactions'].items() if v}
        mine_react = any(self.my_username in (v or [])
                         for v in reactions.values())
        rh = 26 if reactions else 0

        body_w = max([font.measure(l) for l in lines] +
                     [fmeta.measure(l) for l in meta_lines] + [10])
        if sender_name:
            body_w = max(body_w, fsender.measure(sender_name))
        if qh:
            body_w = max(body_w, qw)
        bw = min(maxw, body_w) + padx * 2
        bh = (qh + 6 if qh else 0) + name_lh + mlh * len(meta_lines) + lh * len(lines) + pady * 2 + rh

        fr = tk.Frame(self.mi, bg='#121212')
        fr.pack(fill=tk.X, pady=6, padx=22)

        if typ == 'sent':
            # light WhatsApp-green bubble with dark text: easy to read, and it
            # keeps looking right in both the dark and light app themes
            bubble_bg, bubble_fg, tcol, badge_bg = '#d9fdd3', '#111b21', '#667781', '#ffffff'
        else:
            bubble_bg, bubble_fg, tcol, badge_bg = '#1e1e1e', '#e9edef', '#8696a0', '#2c2c2c'
        if deleted:
            bubble_fg = tcol

        cv = tk.Canvas(fr, width=bw, height=bh, bg='#121212', highlightthickness=0, bd=0)
        self._round_rect(cv, 0, 0, bw, bh, radius, bubble_bg)
        if mid:
            self._bubble_widgets[mid] = fr
            self._bubble_rects[mid] = (cv, tuple(cv.find_all()))
        y = pady
        if sender_name:
            col = _GROUP_SENDER_COLORS[hash(sender_name) % len(_GROUP_SENDER_COLORS)]
            cv.create_text(padx, y, text=sender_name, fill=col,
                           font=("Segoe UI", 9, "bold"), anchor="nw")
            y += name_lh
        if qh:
            self._draw_quote(cv, msg, q_sender, q_lines,
                             padx - 4, y, bw - 2 * padx + 8, qh, typ)
            y += qh + 6
        for ln in meta_lines:
            cv.create_text(padx, y, text=ln, fill=tcol, font=("Segoe UI", 9), anchor="nw")
            y += mlh
        for i, ln in enumerate(lines):
            ly = y + i * lh
            if (not deleted) and highlight:
                # only the matching characters are highlighted (not the whole
                # line), and the focused match gets the stronger amber tone
                self._draw_hl_line(cv, padx, ly, ln, ("Segoe UI", 12), highlight,
                                   bubble_fg, focus=focus)
            else:
                cv.create_text(padx, ly, text=ln, fill=bubble_fg,
                               font=("Segoe UI", 12), anchor="nw")

        if reactions:
            keys = list(reactions.keys())[:3]
            total = sum(len(v) for v in reactions.values())
            emo = " ".join(keys)
            cnt = str(total) if total > 1 else ""
            ew = femoji.measure(emo)
            cw = (fmeta.measure(" " + cnt) if cnt else 0)
            rw = ew + cw + 22
            by = bh - rh + 3
            # a WhatsApp-like reaction chip: green-tinted when it is mine
            if typ == 'sent':
                pill_bg = '#ffffff'
                pill_border = '#25d366' if mine_react else '#dff3d1'
                pill_fg, cnt_fg = '#111b21', '#667781'
            else:
                pill_bg = '#233138'
                pill_border = '#25d366' if mine_react else '#3b4a54'
                pill_fg, cnt_fg = '#e9edef', '#8696a0'
            # draw a slightly larger pill in the border colour, then the fill
            # on top (the rounded-rect helper has no real outline of its own).
            self._round_rect(cv, padx - 7, by - 1, padx - 5 + rw, by + 21, 11,
                             pill_border)
            self._round_rect(cv, padx - 6, by, padx - 6 + rw, by + 20, 10,
                             pill_bg)
            cv.create_text(padx + 1, by + 10, text=emo, anchor="w",
                           fill=pill_fg, font=("Segoe UI Emoji", 11))
            if cnt:
                cv.create_text(padx - 6 + rw - 9, by + 10, text=cnt, anchor="e",
                               fill=cnt_fg, font=("Segoe UI", 9, "bold"))

        tsfr = tk.Frame(fr, bg='#121212')
        tk.Label(tsfr, text=self._fmt_time(ts), bg='#121212', fg=tcol, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        # delivery/read ticks belong to the sender's side only
        if typ == 'sent':
            if status == 'read':
                tick, tickcol = "\u2713\u2713", '#53bdeb'
            elif status == 'delivered':
                tick, tickcol = "\u2713\u2713", '#667781'
            elif status == 'blocked':
                tick, tickcol = "\u2717", '#ff5c5c'
            elif status == 'undelivered':
                tick, tickcol = "\u2713", '#e3b341'
            else:
                tick, tickcol = "\u2713", '#667781'
            lbl = tk.Label(tsfr, text=tick, bg='#121212', fg=tickcol,
                           font=("Segoe UI", 9, "bold"))
            lbl.pack(side=tk.LEFT, padx=(5, 0))
            if mid:
                self._bubble_labels[mid] = lbl

        if typ == 'sent':
            cv.pack(side=tk.RIGHT)
            tsfr.pack(side=tk.RIGHT, padx=6)
        else:
            cv.pack(side=tk.LEFT)
            tsfr.pack(side=tk.LEFT, padx=6)

        self._bind_mousewheel_recursive(cv, self.mcv)
        self._theme_subtree(fr)
        if msg:
            self._bind_msg_menu(fr, msg)

    def add_msg(self, data):
        if data.get('deleted'):
            self.bubble("[Message deleted]", data.get('type', 'received'),
                        data.get('time', ''), data.get('status', 'delivered'),
                        mid=data.get('mid'), msg=data, deleted=True)
            self._current_msgs = getattr(self, '_current_msgs', []) + [data]
            self.mcv.update_idletasks()
            self.mcv.yview_moveto(1.0)
            return
        if (data.get('kind') or 'text') != 'text':
            self.add_file_msg(data)
            return
        self.bubble(data.get('text', ''), data.get('type', 'received'), data.get('time', ''),
                    data.get('status', 'delivered'), mid=data.get('mid'), msg=data)
        try:
            self._current_msgs = getattr(self, '_current_msgs', []) + [data]
        except Exception:
            pass
        self.mcv.update_idletasks()
        self.mcv.yview_moveto(1.0)

    def add_file_msg(self, data):
        """Render an attachment bubble (and remember it for search / opening)."""
        if not data.get('_local_path') and data.get('file_data'):
            self._materialize_file(data)          # save to downloads/ on arrival
        self.file_bubble(data, data.get('type', 'received'), data.get('time', ''),
                         data.get('status', 'delivered'), mid=data.get('mid'))
        self._current_msgs = getattr(self, '_current_msgs', []) + [data]
        self.mcv.update_idletasks()
        self.mcv.yview_moveto(1.0)

    # ============================================================
    # FILES / ATTACHMENTS (software logo + in-panel preview + open)
    # ============================================================
    def _draw_file_logo(self, cv, x, y, size, filename, kind=''):
        """Draw the file's software logo as a crisp rounded 'app tile'.

        A .docx gets the blue Word tile with a 'W', .xlsx the green Excel 'X',
        .pptx the orange 'P', PDFs the red 'PDF', media/code files a themed
        glyph, and so on.  Returns the app title that was drawn.
        """
        title, color, mark, glyph = file_logo(filename, kind)
        r = max(3, int(size * 0.22))
        self._round_rect(cv, x, y, x + size, y + size, r, color)
        if glyph:
            cv.create_text(x + size / 2, y + size / 2,
                           text=ICON.get(glyph, ICON['file']), fill='white',
                           font=(self.icon_family, max(9, int(size * 0.44))))
        else:
            m = (mark or 'F')[:3]
            fs = 0.46 if len(m) == 1 else (0.32 if len(m) == 2 else 0.24)
            cv.create_text(x + size / 2, y + size / 2, text=m, fill='white',
                           font=("Segoe UI", max(8, int(size * fs)), "bold"))
        return title

    @staticmethod
    def _lighten(color, amount=0.12):
        """Return a lighter (amount > 0) or darker (amount < 0) shade."""
        try:
            r = int(color[1:3], 16); g = int(color[3:5], 16); b = int(color[5:7], 16)
            r = max(0, min(255, int(r + (255 - r) * amount)))
            g = max(0, min(255, int(g + (255 - g) * amount)))
            b = max(0, min(255, int(b + (255 - b) * amount)))
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return color

    # ---------- in-panel preview page ----------
    def _build_file_preview(self, parent):
        """Build the preview page shown inside the right panel before sending."""
        pv = tk.Frame(parent, bg='#121212')

        head = tk.Frame(pv, bg='#121212', height=50)
        head.pack(fill=tk.X, padx=14, pady=(8, 0))
        head.pack_propagate(False)
        tk.Label(head, text="Send file", bg='#121212', fg='#e9edef',
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        xb = RoundedButton(head, icon=ICON["close"], icon_font=(self.icon_family, 13),
                           command=self._cancel_file_preview, parent_bg='#121212',
                           width=32, height=32, radius=16,
                           active_bg='#1e1e1e', active_fg='#8696a0')
        xb.set_active(True)
        xb.pack(side=tk.RIGHT)

        card = tk.Frame(pv, bg='#1e1e1e')
        card.pack(fill=tk.X, padx=26, pady=(16, 0))
        self.pv_logo = tk.Canvas(card, width=112, height=112, bg='#1e1e1e',
                                 highlightthickness=0, bd=0)
        self.pv_logo.pack(pady=(20, 6))
        self.pv_app = tk.Label(card, text="", bg='#1e1e1e', fg='#8696a0',
                               font=("Segoe UI", 10))
        self.pv_app.pack()
        self.pv_name = tk.Label(card, text="", bg='#1e1e1e', fg='#e9edef',
                                font=("Segoe UI", 13, "bold"), wraplength=430,
                                justify="center")
        self.pv_name.pack(pady=(6, 2), padx=16)
        self.pv_meta = tk.Label(card, text="", bg='#1e1e1e', fg='#8696a0',
                                font=("Segoe UI", 10))
        self.pv_meta.pack(pady=(0, 20))

        tk.Label(pv, text="Add a caption (optional)", bg='#121212', fg='#8696a0',
                 font=("Segoe UI", 10), anchor='w').pack(fill=tk.X, padx=28, pady=(16, 4))
        cap_box = RoundedBox(pv, radius=16, bg='#2c2c2c', parent_bg='#121212')
        cap_box.pack(fill=tk.X, padx=26)
        self.pv_caption = tk.Entry(cap_box, bg='#2c2c2c', bd=0, font=("Segoe UI", 12),
                                   fg='white', insertbackground='#25d366', relief=tk.FLAT)
        self.pv_caption.pack(fill=tk.X, expand=True, padx=14, pady=8)
        self.pv_caption.bind('<Return>', lambda e: self._send_pending_file())

        bf = tk.Frame(pv, bg='#121212')
        bf.pack(pady=20)
        self.pv_send = RoundedButton(bf, text="Send", icon=ICON["send"],
                                     icon_font=(self.icon_family, 15),
                                     command=self._send_pending_file,
                                     font=("Segoe UI", 12, "bold"),
                                     parent_bg='#121212', width=150, height=44, radius=22,
                                     active_bg='#25d366', active_fg='white')
        self.pv_send.set_active(True)
        self.pv_send.pack(side=tk.LEFT, padx=8)
        cb = RoundedButton(bf, text="Cancel", command=self._cancel_file_preview,
                           font=("Segoe UI", 12, "bold"), parent_bg='#121212',
                           width=120, height=44, radius=22,
                           active_bg='#2c2c2c', active_fg='#e9edef')
        cb.set_active(True)
        cb.pack(side=tk.LEFT, padx=8)
        # Enter anywhere on the preview page sends the file too
        pv.bind('<Return>', lambda e: self._send_pending_file())
        return pv

    def _show_file_preview(self):
        """Reveal the in-panel preview for the currently pending attachment."""
        pf = self._pending_file
        if not pf:
            return
        name = pf.get('name', '')
        kind = pf.get('kind', 'file')
        title, color, mark, glyph = file_logo(name, kind)
        self.pv_logo.delete('all')
        self._draw_file_logo(self.pv_logo, 9, 9, 94, name, kind)
        self.pv_app.configure(text=title)
        self.pv_name.configure(text=name)
        self.pv_meta.configure(text=f"{human_size(pf.get('size', 0))}  \u00b7  "
                                    f"{kind.capitalize()} file  \u00b7  Enter to send")
        self.pv_caption.delete(0, tk.END)
        # swap the message list for the preview (both live inside the right panel)
        try:
            self.messages_area.pack_forget()
        except Exception:
            pass
        self.preview_panel.pack(fill=tk.BOTH, expand=True, before=self.input_area)
        self.sb.set_enabled(True)
        self._theme_subtree(self.preview_panel)
        try:
            self.pv_caption.focus_set()
        except Exception:
            pass

    def _hide_file_preview(self):
        """Close the preview page and bring the message list back."""
        try:
            self.preview_panel.pack_forget()
        except Exception:
            pass
        try:
            if not self.messages_area.winfo_ismapped():
                self.messages_area.pack(fill=tk.BOTH, expand=True, before=self.input_area)
        except Exception:
            pass

    def _cancel_file_preview(self):
        """Discard the pending attachment without sending it."""
        self._pending_file = None
        self._hide_file_preview()
        self.sb.set_enabled(bool(self.mi_t.get().strip()))
        try:
            self.mi_t.focus_set()
        except Exception:
            pass

    def _discard_file_preview(self):
        """Quietly drop any pending attachment (used when switching chats)."""
        self._pending_file = None
        self._hide_file_preview()

    def _send_pending_file(self):
        """Send the previewed file (via the Send button or Enter)."""
        pf = self._pending_file
        if pf is None or self.current_chat_id is None:
            return
        try:
            caption = self.pv_caption.get().strip()
        except Exception:
            caption = ''
        self._pending_file = None
        self._hide_file_preview()
        self.sb.set_enabled(bool(self.mi_t.get().strip()))
        self._dispatch_file(pf['name'], pf['mime'], pf['kind'], pf['data'],
                            caption=caption, local_path=pf['path'])
        self.show_toast(f"Sent: {pf['name']}")
        try:
            self.mi_t.focus_set()
        except Exception:
            pass

    @staticmethod
    def _file_preview_label(msg):
        """Short chat-list preview, e.g. 'Document: report.docx'."""
        label = FILE_KIND_LABEL.get(msg.get('file_kind') or 'file', 'File')
        if label == 'Document':
            label = 'Document: ' + os.path.basename(str(msg.get('file_name') or 'file'))
        cap = (msg.get('text') or '').strip()
        return label + (': ' + cap if cap else '')

    # ---------- attachment bubble ----------
    def file_bubble(self, msg, typ, ts, status="delivered", mid=None,
                    hl="", focus=False):
        """A rounded attachment bubble: software logo + name + size.

        Clicking it opens the file with the software it belongs to (Word files
        open in Word, PDFs in the PDF viewer, and so on).
        """
        fname = os.path.basename(str(msg.get('file_name') or 'file')) or 'file'
        kind = msg.get('file_kind') or file_kind_of(fname, msg.get('file_mime'))
        size_txt = human_size(msg.get('file_size') or 0)
        caption = (msg.get('text') or '').strip()
        is_group = (getattr(self, 'current_chat_type', '') == 'group')
        sender_name = ''
        if typ != 'sent' and is_group and msg:
            sender_name = (msg.get('sender') or '').strip()

        f_name = tkfont.Font(font=("Segoe UI", 12, "bold"))
        f_sub = tkfont.Font(font=("Segoe UI", 9))
        f_cap = tkfont.Font(font=("Segoe UI", 11))
        maxw, padx, pady, radius = 320, 13, 12, 12
        logo = 46
        text_max = max(140, maxw - logo - 14)
        name_lines = self._wrap_text(fname, f_name, text_max)
        f_meta = tkfont.Font(font=("Segoe UI", 9))
        dur = int(msg.get('file_dur') or 0)
        if kind == 'audio':
            dstr = "%d:%02d" % (dur // 60, dur % 60)
            meta = f"\u25b6 {dstr}  \u00b7  Voice message" if fname.startswith('voice_') \
                else f"\u25b6 {dstr}  \u00b7  Audio"
        else:
            meta = f"{size_txt}  \u00b7  {kind.capitalize()}"
        meta_lines = []
        if msg.get('forwarded'):
            meta_lines.append("\u21aa Forwarded")
        if msg.get('pinned'):
            meta_lines.append("\U0001F4CC Pinned")
        if msg.get('starred'):
            meta_lines.append("\u2605 Starred")
        rr = msg.get('reactions')
        if isinstance(rr, dict) and any(rr.values()):
            rkeys = [k for k, v in rr.items() if v]
            meta_lines.append(" ".join(rkeys[:3]) + "  " +
                              str(sum(len(v) for v in rr.values() if v)))
        # clickable reply quote (full file name of the original, never truncated)
        q_sender, q_lines, qh, qw = self._quote_box(msg, maxw - 40)
        cap_lines = self._wrap_text(caption, f_cap, maxw) if caption else []
        fsender = tkfont.Font(font=("Segoe UI", 9, "bold"))
        lh_name = f_name.metrics("linespace")
        lh_sub = f_sub.metrics("linespace")
        lh_cap = f_cap.metrics("linespace")
        lh_meta = f_meta.metrics("linespace")
        meta_h = lh_meta * len(meta_lines)
        name_lh = (fsender.metrics("linespace") + 2) if sender_name else 0
        text_w = max([f_name.measure(l) for l in name_lines] + [f_sub.measure(meta), 120])
        if qh:
            text_w = max(text_w, qw)
        header_h = len(name_lines) * lh_name + 3 + lh_sub
        content_h = max(logo, header_h)
        bw = min(maxw, logo + 14 + text_w) + padx * 2
        bh = pady + name_lh + (qh + 6 if qh else 0) + meta_h + content_h + \
            (len(cap_lines) * lh_cap + 9 if cap_lines else 0) + pady

        fr = tk.Frame(self.mi, bg='#121212')
        fr.pack(fill=tk.X, pady=6, padx=22)
        if typ == 'sent':
            bubble_bg, fg_main, fg_sub, tcol = '#d9fdd3', '#111b21', '#667781', '#667781'
        else:
            bubble_bg, fg_main, fg_sub, tcol = '#1e1e1e', '#e9edef', '#8696a0', '#8696a0'

        cv = tk.Canvas(fr, width=bw, height=bh, bg='#121212',
                       highlightthickness=0, bd=0, cursor="hand2")
        self._round_rect(cv, 0, 0, bw, bh, radius, bubble_bg)
        if mid:
            self._bubble_widgets[mid] = fr
            self._bubble_rects[mid] = (cv, tuple(cv.find_all()))
        my = pady
        if sender_name:
            col = _GROUP_SENDER_COLORS[hash(sender_name) % len(_GROUP_SENDER_COLORS)]
            cv.create_text(padx, my, text=sender_name, fill=col,
                           font=("Segoe UI", 9, "bold"), anchor="nw")
            my += name_lh
        if qh:
            self._draw_quote(cv, msg, q_sender, q_lines, padx - 4, my,
                             bw - 2 * padx + 8, qh, typ, jump=False)
            my += qh + 6
        for ln in meta_lines:
            cv.create_text(padx, my, text=ln, anchor="nw", fill=tcol, font=("Segoe UI", 9))
            my += lh_meta
        top = my + meta_h
        self._draw_file_logo(cv, padx, top, logo, fname, kind)
        if kind == 'audio':
            self._round_rect(cv, padx + logo - 17, top + logo - 17,
                             padx + logo, top + logo, 6, bubble_bg)
            cv.create_text(padx + logo - 9, top + logo - 9, text="\u25b6",
                           fill=fg_main, font=("Segoe UI", 8))
        tx = padx + logo + 14
        y = top
        for ln in name_lines:
            if hl:
                self._draw_hl_line(cv, tx, y, ln, ("Segoe UI", 12, "bold"), hl,
                                   fg_main, focus=focus)
            else:
                cv.create_text(tx, y, text=ln, anchor="nw", fill=fg_main,
                               font=("Segoe UI", 12, "bold"))
            y += lh_name
        y += 3
        cv.create_text(tx, y, text=meta, anchor="nw", fill=fg_sub, font=("Segoe UI", 9))
        if cap_lines:
            y = top + content_h + 8
            for ln in cap_lines:
                if hl:
                    self._draw_hl_line(cv, padx, y, ln, ("Segoe UI", 11), hl,
                                       fg_main, focus=focus)
                else:
                    cv.create_text(padx, y, text=ln, anchor="nw", fill=fg_main,
                                   font=("Segoe UI", 11))
                y += lh_cap

        def on_click(e, m=msg, quote_h=qh, base=pady):
            # a click inside the quote jumps to the original message; anywhere
            # else opens / plays the attachment
            if quote_h and getattr(e, 'y', 1e9) <= base + quote_h + 4:
                self._jump_to_msg(m.get('reply_to') or '')
            else:
                self._click_attachment(m)
        cv.bind('<Button-1>', on_click)

        tsfr = tk.Frame(fr, bg='#121212')
        tk.Label(tsfr, text=self._fmt_time(ts), bg='#121212', fg=tcol, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        if typ == 'sent':
            if status == 'read':
                tick, tickcol = "\u2713\u2713", '#25d366'
            elif status == 'delivered':
                tick, tickcol = "\u2713\u2713", '#8696a0'
            elif status == 'blocked':
                tick, tickcol = "\u2717", '#ff5c5c'
            elif status == 'undelivered':
                tick, tickcol = "\u2713", '#e3b341'
            else:
                tick, tickcol = "\u2713", '#8696a0'
            lbl = tk.Label(tsfr, text=tick, bg='#121212', fg=tickcol,
                           font=("Segoe UI", 9, "bold"))
            lbl.pack(side=tk.LEFT, padx=(5, 0))
            if mid:
                self._bubble_labels[mid] = lbl
        if typ == 'sent':
            cv.pack(side=tk.RIGHT)
            tsfr.pack(side=tk.RIGHT, padx=6)
        else:
            cv.pack(side=tk.LEFT)
            tsfr.pack(side=tk.LEFT, padx=6)

        self._bind_mousewheel_recursive(cv, self.mcv)
        self._theme_subtree(fr)
        self._bind_msg_menu(fr, msg)

    # ---------- saving + opening attachments ----------
    def _click_attachment(self, msg):
        """Open the attachment in a separate window with its default software.

        Voice notes / audio now open in the OS media player (a separate
        player window), exactly like documents open in Word, PDFs in the PDF
        viewer, and so on.
        """
        self._open_attachment(msg)
    def _materialize_file(self, msg):
        """Write a received attachment to downloads/<mid>/<name> and return it."""
        path = msg.get('_local_path')
        if path and os.path.exists(path):
            return path
        b64 = msg.get('file_data')
        if not b64:
            return None
        fname = os.path.basename(str(msg.get('file_name') or 'file')) or 'file'
        mid = str(msg.get('mid') or uuid.uuid4().hex[:12])
        folder = os.path.join(APP_DIR, 'downloads', mid)
        path = os.path.join(folder, fname)
        try:
            os.makedirs(folder, exist_ok=True)
            if not os.path.exists(path):
                with open(path, 'wb') as f:
                    f.write(base64.b64decode(b64))
            msg['_local_path'] = path
            self._file_cache[mid] = path
            return path
        except Exception as e:
            self.notify("Save failed", str(e), kind='error')
            return None

    def _open_attachment(self, msg):
        """Open an attachment with its default software (Word, PDF viewer, ...)."""
        path = msg.get('_local_path')
        if not path or not os.path.exists(path):
            path = self._materialize_file(msg)
        if not path:
            self.notify("Cannot open", "File data missing", kind='error')
            return
        if self._open_with_default(path):
            self.show_toast(f"Opening {os.path.basename(path)}")
        else:
            self.notify("Cannot open", os.path.basename(path), kind='error')

    @staticmethod
    def _open_with_default(path):
        """Hand the file to the OS so it opens in its associated app."""
        try:
            if sys.platform.startswith('win'):
                os.startfile(path)                      # noqa: S606 (Windows)
            elif sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(['open', path])
            else:
                import subprocess
                subprocess.Popen(['xdg-open', path])
            return True
        except Exception:
            return False

    # ============================================================
    # VOICE MESSAGES (WhatsApp-style recording UI)
    # ============================================================
    def _build_recorder_row(self, parent):
        """The recording bar that replaces the composer while recording."""
        row = tk.Frame(parent, bg='#1e1e1e')
        self.rec_cancel = RoundedButton(row, icon=ICON["close"],
                                        icon_font=(self.icon_family, 15),
                                        command=self.cancel_recording, parent_bg='#1e1e1e',
                                        width=36, height=36, radius=18,
                                        active_bg='#1e1e1e', active_fg='#ff5c5c')
        self.rec_cancel.set_active(True)
        self.rec_cancel.pack(side=tk.LEFT, padx=(8, 2), pady=12)
        self.rec_dot = tk.Canvas(row, width=18, height=18, bg='#1e1e1e',
                                 highlightthickness=0, bd=0)
        self.rec_dot.pack(side=tk.LEFT, padx=(2, 6))
        self.rec_dot_item = self.rec_dot.create_oval(4, 4, 14, 14, fill='#ff3b30', outline='')
        self.rec_timer = tk.Label(row, text="0:00", bg='#1e1e1e', fg='#e9edef',
                                  font=("Segoe UI", 12, "bold"), width=4, anchor='w')
        self.rec_timer.pack(side=tk.LEFT)
        self.rec_wave = tk.Canvas(row, bg='#1e1e1e', height=34, highlightthickness=0, bd=0)
        self.rec_wave.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.rec_hint = tk.Label(row, text="Slide to cancel  \u2039", bg='#1e1e1e',
                                 fg='#8696a0', font=("Segoe UI", 10), cursor="hand2")
        self.rec_hint.pack(side=tk.LEFT, padx=4)
        self.rec_hint.bind('<Button-1>', lambda e: self.cancel_recording())
        self.rec_send = RoundedButton(row, icon=ICON["send"],
                                      icon_font=(self.icon_family, 16),
                                      command=self.stop_recording, parent_bg='#1e1e1e',
                                      width=38, height=36, radius=18,
                                      active_bg='#25d366', active_fg='white')
        self.rec_send.set_active(True)
        self.rec_send.pack(side=tk.LEFT, padx=(2, 8), pady=12)
        return row

    def start_recording(self):
        """Mic button: begin recording and show the WhatsApp-style bar."""
        if self.current_chat_id is None:
            self.notify("Voice message", "Pehle koi chat kholo", kind='error')
            return
        if self._recording:
            return
        if not PYAUDIO_OK:
            self.notify("Voice message", "pyaudio install karo: pip install pyaudio",
                        kind='error')
            return
        self._rec_frames = []
        self._rec_levels = []
        self._rec_start = time.time()
        self._rec_phase = 0
        try:
            self._pa = _pyaudio.PyAudio()
            self._rec_stream = self._pa.open(format=_pyaudio.paInt16, channels=1,
                                             rate=self.REC_RATE, input=True,
                                             frames_per_buffer=self.REC_CHUNK)
        except Exception as e:
            self.notify("Mic error", str(e), kind='error')
            self._close_recorder_audio()
            return
        self._recording = True
        threading.Thread(target=self._rec_loop, daemon=True).start()
        try:
            self.input_row.pack_forget()
            self.rec_row.pack(fill=tk.BOTH, expand=True)
        except Exception:
            pass
        self._theme_subtree(self.rec_row)
        try:
            self.rec_wave.update_idletasks()
        except Exception:
            pass
        self._rec_tick()
        try:
            self.root.bind('<Escape>', lambda e: self.cancel_recording())
        except Exception:
            pass

    def _rec_loop(self):
        while self._recording:
            try:
                data = self._rec_stream.read(self.REC_CHUNK, exception_on_overflow=False)
            except Exception:
                break
            self._rec_frames.append(data)
            try:
                a = array.array('h')
                a.frombytes(data)
                rms = (sum(v * v for v in a) / len(a)) ** 0.5 if len(a) else 0
            except Exception:
                rms = 0
            self._rec_levels.append(rms)
            if len(self._rec_levels) > 160:
                del self._rec_levels[0]

    def _rec_tick(self):
        if not self._recording:
            return
        elapsed = time.time() - self._rec_start
        try:
            self.rec_timer.configure(text="%d:%02d" % (int(elapsed) // 60,
                                                        int(elapsed) % 60))
        except Exception:
            pass
        # pulsing red dot
        try:
            self._rec_phase = (self._rec_phase + 1) % 20
            r = 4 + 3 * abs(math.sin(self._rec_phase / 20.0 * math.pi))
            self.rec_dot.coords(self.rec_dot_item, 9 - r, 9 - r, 9 + r, 9 + r)
        except Exception:
            pass
        self._draw_rec_wave()
        if elapsed >= 300:                  # 5 minute cap -> auto send
            self.stop_recording()
            return
        self._rec_job = self.root.after(80, self._rec_tick)

    def _draw_rec_wave(self):
        """Animated live waveform while recording."""
        cv = self.rec_wave
        try:
            cv.delete('all')
            w = cv.winfo_width() or 240
            h = 34
            n = max(8, int(w // 6))
            lv = self._rec_levels[-n:]
            for i in range(n):
                v = lv[i] if i < len(lv) else 0
                bh = 4 + min(1.0, v / 6000.0) * (h - 10)
                x = 3 + i * ((w - 6) / float(n))
                cv.create_line(x, h / 2 - bh / 2, x, h / 2 + bh / 2,
                               fill='#25d366', width=2, capstyle=tk.ROUND)
            cv.create_oval(w - 10, h / 2 - 4, w - 2, h / 2 + 4, fill='#ff3b30', outline='')
        except Exception:
            pass

    def _close_recorder_audio(self):
        try:
            if getattr(self, '_rec_stream', None):
                self._rec_stream.stop_stream()
                self._rec_stream.close()
        except Exception:
            pass
        try:
            if getattr(self, '_pa', None):
                self._pa.terminate()
        except Exception:
            pass
        self._rec_stream = None
        self._pa = None

    def _hide_recorder(self):
        try:
            self.rec_row.pack_forget()
            self.input_row.pack(fill=tk.BOTH, expand=True)
        except Exception:
            pass
        try:
            self.root.unbind('<Escape>')
        except Exception:
            pass

    def stop_recording(self):
        """Stop and send the recorded voice message."""
        if not self._recording:
            return
        self._recording = False
        try:
            if self._rec_job:
                self.root.after_cancel(self._rec_job)
        except Exception:
            pass
        self._rec_job = None
        time.sleep(0.08)
        self._close_recorder_audio()
        self._hide_recorder()
        frames = b"".join(self._rec_frames)
        self._rec_frames = []
        if not frames:
            self.notify("Voice message", "Kuch record nahi hua", kind='error')
            return
        dur = len(frames) / float(self.REC_RATE * 2)
        if dur < 0.4:
            self.notify("Voice message", "Recording bohat choti thi", kind='error')
            return
        wav = self._frames_to_wav(frames)
        self._dispatch_file("voice_%s.wav" % uuid.uuid4().hex[:8], "audio/wav",
                            "audio", base64.b64encode(wav).decode('ascii'),
                            duration=max(1, int(round(dur))))

    def cancel_recording(self):
        if not self._recording:
            return
        self._recording = False
        try:
            if self._rec_job:
                self.root.after_cancel(self._rec_job)
        except Exception:
            pass
        self._rec_job = None
        time.sleep(0.05)
        self._close_recorder_audio()
        self._rec_frames = []
        self._hide_recorder()
        self.show_toast("Recording cancelled")

    def _frames_to_wav(self, frames):
        bio = io.BytesIO()
        with wave.open(bio, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.REC_RATE)
            w.writeframes(frames)
        return bio.getvalue()

    def _play_audio_file(self, path):
        """Play a voice note / audio attachment inline."""
        if not path or not os.path.exists(path):
            return False
        try:
            if path.lower().endswith('.wav') and winsound is not None:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC |
                                   winsound.SND_NODEFAULT)
                return True
        except Exception:
            pass
        try:
            winmm = ctypes.windll.winmm
            winmm.mciSendStringW('close cnchat_audio', None, 0, 0)
            rc = winmm.mciSendStringW('open "%s" alias cnchat_audio' % path, None, 0, 0)
            if rc == 0:
                winmm.mciSendStringW('play cnchat_audio', None, 0, 0)
                return True
        except Exception:
            pass
        return False

    # ---- shared file/text sending ----
    def _reply_fields(self):
        """Snapshot of the message being replied to (or empty)."""
        r = self.reply_to
        if not r:
            return {}
        sender = r.get('sender') or ('You' if r.get('type') == 'sent'
                                     else self.current_chat_name)
        # attachments quote their FULL file name (never truncated) so the other
        # side can tell exactly which file is being answered
        if (r.get('kind') or 'text') != 'text' and r.get('file_name'):
            fname = os.path.basename(str(r['file_name']))
            cap = (r.get('text') or '').strip()
            snippet = fname + (('  \u00b7  ' + cap) if cap else '')
        else:
            snippet = (r.get('text') or '')
        return {'reply_to': r.get('mid'),
                'reply_text': snippet[:300],
                'reply_sender': sender}

    def _dispatch_file(self, name, mime, kind, data_b64, caption='',
                       local_path=None, duration=0, forwarded=False):
        """Send an attachment to the open chat and show it locally."""
        if self.current_chat_id is None:
            self.notify("File", "Pehle koi chat kholo", kind='error')
            return None
        ts = datetime.now().strftime("%H:%M")
        mid = uuid.uuid4().hex[:12]
        try:
            size = len(base64.b64decode(data_b64)) if data_b64 else 0
        except Exception:
            size = 0
        msg = {'mid': mid, 'text': caption, 'type': 'sent', 'time': ts,
               'status': 'sent', 'kind': 'file', 'file_name': name, 'file_kind': kind,
               'file_mime': mime, 'file_size': size, 'file_data': data_b64,
               'file_dur': duration, 'day': datetime.now().strftime("%Y-%m-%d"),
               'forwarded': forwarded}
        if local_path:
            msg['_local_path'] = local_path
        msg.update(self._reply_fields())
        self.add_file_msg(msg)
        preview = self._file_preview_label(msg)
        self._update_chat_preview(self.current_chat_id, preview, ts)
        for u in getattr(self, '_peers', []):
            if u.get('id') == self.current_chat_id:
                u['lastMsg'] = preview
                u['time'] = ts
                break
        self._touch_chat(self.current_chat_id)
        payload = {'mid': mid, 'text': caption, 'sender': self.my_username,
                   'kind': 'file', 'file_name': name, 'file_kind': kind,
                   'file_mime': mime, 'file_size': size, 'file_data': data_b64,
                   'file_dur': duration}
        if forwarded:
            payload['forwarded'] = True
        payload.update(self._reply_fields())
        if self.current_chat_type == 'group':
            payload['to_group'] = self.current_chat_gid
        else:
            payload['to_name'] = self.current_chat_name
            payload['to_sid'] = getattr(self, 'current_chat_sid', None)
            payload['from_ip'] = self._local_ipv4()
        sio.emit('send_message', payload)
        self._cancel_reply()
        return msg

    def _emit_text_msg(self, text, forwarded=False):
        """Send a text message to the open chat (reply / forwarded aware)."""
        if not text or self.current_chat_id is None:
            return None
        ts = datetime.now().strftime("%H:%M")
        mid = uuid.uuid4().hex[:12]
        local = {'mid': mid, 'text': text, 'type': 'sent', 'time': ts,
                 'status': 'sent', 'forwarded': forwarded,
                 'day': datetime.now().strftime("%Y-%m-%d")}
        local.update(self._reply_fields())
        self.bubble(text, 'sent', ts, 'sent', mid=mid, msg=local)
        self._current_msgs = getattr(self, '_current_msgs', []) + [local]
        self._update_chat_preview(self.current_chat_id, text, ts)
        for u in getattr(self, '_peers', []):
            if u.get('id') == self.current_chat_id:
                u['lastMsg'] = text
                u['time'] = ts
                break
        self._touch_chat(self.current_chat_id)
        payload = {'mid': mid, 'text': text, 'sender': self.my_username}
        if forwarded:
            payload['forwarded'] = True
        payload.update(self._reply_fields())
        if self.current_chat_type == 'group':
            payload['to_group'] = self.current_chat_gid
        else:
            payload['to_name'] = self.current_chat_name
            payload['to_sid'] = getattr(self, 'current_chat_sid', None)
            payload['from_ip'] = self._local_ipv4()
        sio.emit('send_message', payload)
        self._cancel_reply()
        self.mcv.update_idletasks()
        self.mcv.yview_moveto(1.0)
        return local

    def _menu_do(self, fn):
        """Run a menu action right after the popup has closed.

        Dialogs (messagebox / Toplevel) opened *while* the popup still holds its
        grab can end up behind the menu - deferring by a few ms fixes that.
        """
        try:
            self.root.after(12, fn)
        except Exception:
            fn()

    def _my_reaction(self, msg):
        rx = msg.get('reactions') or {}
        if not isinstance(rx, dict):
            return ''
        for e, users in rx.items():
            if self.my_username in (users or []):
                return e
        return ''

    def _is_starred(self, msg):
        return self.my_username in (msg.get('starred_for') or [])

    def _msg_menu(self, event, msg):
        m = tk.Menu(self.root, tearoff=0)
        # --- React: quick emoji row, exactly like the real app ---
        mine = self._my_reaction(msg)
        react = tk.Menu(m, tearoff=0)
        for e in self.REACT_EMOJIS:
            react.add_command(label=e + ("   \u2713" if e == mine else ""),
                              command=lambda e=e: self._menu_do(
                                  lambda: self._react_msg(msg, e)))
        if mine:
            react.add_separator()
            react.add_command(label="Remove reaction",
                              command=lambda: self._menu_do(
                                  lambda: self._react_msg(msg, '')))
        m.add_cascade(label="React", menu=react)
        m.add_separator()
        if (msg.get('kind') or 'text') == 'text' and (msg.get('text') or ''):
            m.add_command(label="Copy", command=lambda: self._copy_msg(msg))
        m.add_command(label="Reply", command=lambda: self._start_reply(msg))
        m.add_command(label="Forward", command=lambda: self._menu_do(
            lambda: self._forward_msg(msg)))
        m.add_separator()
        m.add_command(label="Unpin" if msg.get('pinned') else "Pin",
                      command=lambda: self._toggle_pin(msg))
        m.add_command(label="Unstar" if self._is_starred(msg) else "Star",
                      command=lambda: self._toggle_star(msg))
        if msg.get('file_name'):
            m.add_command(label="Open / play",
                          command=lambda: self._open_attachment(msg))
        m.add_command(label="Message info",
                      command=lambda: self._menu_do(
                          lambda: self._msg_info(msg)))
        m.add_separator()
        # --- Delete: submenu so nothing is hit by accident ---
        dele = tk.Menu(m, tearoff=0)
        dele.add_command(label="Delete for me",
                         command=lambda: self._menu_do(
                             lambda: self._delete_msg(msg, 'me')))
        if msg.get('type') == 'sent' or msg.get('sender') == self.my_username:
            dele.add_command(label="Delete for everyone",
                             command=lambda: self._menu_do(
                                 lambda: self._delete_msg(msg, 'all')))
        m.add_cascade(label="Delete", menu=dele)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                m.grab_release()
            except Exception:
                pass

    def _react_msg(self, msg, emoji):
        """Add / switch / remove my emoji reaction on a message."""
        mid = msg.get('mid')
        if not mid:
            return
        gid = self.current_chat_gid if self.current_chat_type == 'group' else ''
        # Send FIRST: the server is the source of truth and pushes the final
        # reaction to everyone.  Doing this before the local re-render makes
        # sure the reaction is never lost if rendering raises.
        sent = False
        try:
            sio.emit('react_message', {'mid': mid, 'emoji': emoji,
                                       'me': self.my_username,
                                       'peer': self.current_chat_name, 'group': gid})
            sent = True
        except Exception:
            sent = False
        rx = {}
        for k, v in (msg.get('reactions') or {}).items():
            rest = [u for u in (v or []) if u != self.my_username]
            if rest:
                rx[k] = rest
        if emoji:
            rx.setdefault(emoji, []).append(self.my_username)
        try:
            self._apply_reactions(mid, rx)
        except Exception:
            pass
        if not sent:
            self.show_toast("Reaction bheji nahi ja saki")

    def _apply_reactions(self, mid, rx):
        for m in getattr(self, '_current_msgs', []):
            if m.get('mid') == mid:
                m['reactions'] = rx
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})

    def _toggle_star(self, msg):
        mid = msg.get('mid')
        if not mid:
            return
        star = not self._is_starred(msg)
        lst = [u for u in (msg.get('starred_for') or []) if u != self.my_username]
        if star:
            lst.append(self.my_username)
        for m in getattr(self, '_current_msgs', []):
            if m.get('mid') == mid:
                m['starred_for'] = lst
        gid = self.current_chat_gid if self.current_chat_type == 'group' else ''
        try:
            sio.emit('star_message', {'mid': mid, 'star': star,
                                      'me': self.my_username,
                                      'peer': self.current_chat_name, 'group': gid})
        except Exception:
            pass
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})
        self.show_toast("Starred" if star else "Unstarred")

    def _msg_info(self, msg):
        """The 'Message info' dialog (sender, time, status, reactions...)."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Message info")
        dlg.configure(bg="#121212")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("370x340")
        tk.Label(dlg, text="Message info", bg="#121212", fg="#e9edef",
                 font=("Segoe UI", 15, "bold")).pack(pady=(16, 10))
        kind = (msg.get('kind') or 'text')
        rows = [
            ("From", msg.get('sender') or ('You' if msg.get('type') == 'sent'
                                          else self.current_chat_name or '')),
            ("Type", "Text" if kind == 'text'
             else (msg.get('file_kind') or 'file').capitalize()),
        ]
        if msg.get('file_name'):
            rows.append(("File", os.path.basename(str(msg['file_name']))))
            rows.append(("Size", human_size(msg.get('file_size') or 0)))
        rows += [
            ("Time", self._fmt_time(msg.get('time', ''))),
            ("Date", msg.get('day') or '\u2014'),
            ("Status", (msg.get('status') or 'sent').capitalize()),
        ]
        if msg.get('pinned'):
            rows.append(("Pinned", "Yes"))
        if self._is_starred(msg):
            rows.append(("Starred", "Yes"))
        rx = msg.get('reactions') or {}
        if isinstance(rx, dict) and rx:
            rows.append(("Reactions", "  ".join(
                "%s %d" % (k, len(v or [])) for k, v in rx.items())))
        body = tk.Frame(dlg, bg="#121212")
        body.pack(fill=tk.BOTH, expand=True, padx=18)
        for k, v in rows:
            row = tk.Frame(body, bg="#121212")
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=k, bg="#121212", fg="#8696a0", width=11, anchor='w',
                     font=("Segoe UI", 10)).pack(side=tk.LEFT)
            tk.Label(row, text=str(v), bg="#121212", fg="#e9edef", anchor='w',
                     font=("Segoe UI", 10, 'bold'), wraplength=230,
                     justify='left').pack(side=tk.LEFT, fill=tk.X, expand=True)
        cb = RoundedButton(dlg, text="Close", command=dlg.destroy,
                           parent_bg="#121212", width=96, height=32, radius=10,
                           active_bg="#25d366", active_fg="white")
        cb.set_active(True)
        cb.pack(pady=14)
        self._theme_subtree(dlg)

    def _bind_msg_menu(self, widget, msg):
        widget.bind('<Button-3>', lambda e, m=msg: self._msg_menu(e, m))
        widget.bind('<Button-2>', lambda e, m=msg: self._msg_menu(e, m))
        for c in widget.winfo_children():
            self._bind_msg_menu(c, msg)

    def _copy_msg(self, msg):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(msg.get('text') or msg.get('file_name') or '')
            self.show_toast("Copied")
        except Exception:
            pass

    def _start_reply(self, msg):
        self.reply_to = msg
        self._show_reply_bar()

    def _show_reply_bar(self):
        if getattr(self, 'reply_bar', None) is None:
            rb = tk.Frame(self.ra, bg='#1e1e1e')
            tk.Frame(rb, bg='#25d366', width=4).pack(side=tk.LEFT, fill=tk.Y)
            info = tk.Frame(rb, bg='#1e1e1e')
            info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10, pady=6)
            self.reply_title = tk.Label(info, text="", bg='#1e1e1e', fg='#25d366',
                                        font=("Segoe UI", 10, "bold"), anchor='w')
            self.reply_title.pack(fill=tk.X)
            self.reply_text = tk.Label(info, text="", bg='#1e1e1e', fg='#8696a0',
                                       font=("Segoe UI", 9), anchor='w')
            self.reply_text.pack(fill=tk.X)
            xb = RoundedButton(rb, icon=ICON["close"], icon_font=(self.icon_family, 12),
                               command=self._cancel_reply, parent_bg='#1e1e1e',
                               width=28, height=28, radius=14,
                               active_bg='#1e1e1e', active_fg='#8696a0')
            xb.set_active(True)
            xb.pack(side=tk.RIGHT, padx=8)
            self.reply_bar = rb
        r = self.reply_to or {}
        sender = r.get('sender') or ('You' if r.get('type') == 'sent'
                                     else self.current_chat_name)
        self.reply_title.configure(text="Replying to " + str(sender))
        if (r.get('kind') or 'text') != 'text' and r.get('file_name'):
            snippet = os.path.basename(str(r['file_name']))
        else:
            snippet = r.get('text') or ''
        self.reply_text.configure(text=snippet[:150])
        self.reply_bar.pack(fill=tk.X, before=self.input_area)
        self._theme_subtree(self.reply_bar)
        try:
            self.mi_t.focus_set()
        except Exception:
            pass

    def _cancel_reply(self):
        self.reply_to = None
        try:
            if getattr(self, 'reply_bar', None) is not None:
                self.reply_bar.pack_forget()
        except Exception:
            pass

    def _forward_msg(self, msg):
        """Pick a chat from a list and forward this message into it."""
        peers = list(getattr(self, '_peers', []))
        if not peers:
            self.notify("Forward", "Koi chat available nahi", kind='info')
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Forward to")
        dlg.configure(bg="#121212")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("360x440")
        tk.Label(dlg, text="Forward to", bg="#121212", fg="#e9edef",
                 font=("Segoe UI", 14, "bold")).pack(pady=12)
        body = tk.Frame(dlg, bg="#121212")
        body.pack(fill=tk.BOTH, expand=True, padx=14)

        def do_forward(target):
            dlg.destroy()
            self._forward_into(msg, target)

        for u in peers:
            row = tk.Frame(body, bg="#1e1e1e", cursor="hand2")
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=u.get('name', '?'), bg="#1e1e1e", fg="#e9edef",
                     font=("Segoe UI", 12), anchor="w").pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=12, pady=10)
            self._bind_click_recursive(row, lambda e, t=u: do_forward(t))
            self._bind_hover_recursive(row, row, "#1e1e1e", "#2c2c2c")
        self._theme_subtree(dlg)

    def _forward_into(self, msg, target):
        """Send `msg` content into the `target` chat (text and/or file)."""
        kind = msg.get('kind') or 'text'
        name = msg.get('file_name') or ''
        data = msg.get('file_data') or ''
        text = msg.get('text') or ''
        if kind != 'text' and data:
            payload = {'text': text, 'sender': self.my_username, 'kind': kind,
                       'file_name': name,
                       'file_kind': msg.get('file_kind') or 'file',
                       'file_mime': msg.get('file_mime') or '',
                       'file_size': int(msg.get('file_size') or 0),
                       'file_dur': int(msg.get('file_dur') or 0),
                       'file_data': data, 'forwarded': True}
        else:
            payload = {'text': text, 'sender': self.my_username, 'forwarded': True}
        if target.get('type') == 'group':
            payload['to_group'] = target.get('gid')
        else:
            payload['to_name'] = target.get('name')
            payload['to_sid'] = target.get('sid')
            payload['from_ip'] = self._local_ipv4()
        sio.emit('send_message', payload)
        self.show_toast("Forwarded to " + (target.get('name') or ''))

    def _forward_target(self, target):
        self._saved_chat = (self.current_chat_id, self.current_chat_name,
                            self.current_chat_type, self.current_chat_sid,
                            self.current_chat_gid)
        self.current_chat_id = target.get('id')
        self.current_chat_name = target.get('name')
        self.current_chat_type = target.get('type', 'single')
        self.current_chat_sid = target.get('sid')
        self.current_chat_gid = target.get('gid')

    def _restore_after_forward(self, msg):
        (cid, cname, ctype, csid, cgid) = getattr(
            self, '_saved_chat', (None, None, None, None, None))
        if cid is None:
            return
        self.current_chat_id, self.current_chat_name = cid, cname
        self.current_chat_type, self.current_chat_sid = ctype, csid
        self.current_chat_gid = cgid
        # the forwarded bubble should not appear in the currently open chat view
        try:
            self.render_msgs({'messages': getattr(self, '_current_msgs', [])})
        except Exception:
            pass

    def _send_to_target(self, target, text, forwarded=False):
        if not text:
            return
        ts = datetime.now().strftime("%H:%M")
        mid = uuid.uuid4().hex[:12]
        payload = {'mid': mid, 'text': text, 'sender': self.my_username}
        if forwarded:
            payload['forwarded'] = True
        if target.get('type') == 'group':
            payload['to_group'] = target.get('gid')
        else:
            payload['to_name'] = target.get('name')
            payload['to_sid'] = target.get('sid')
            payload['from_ip'] = self._local_ipv4()
        sio.emit('send_message', payload)

    def _toggle_pin(self, msg):
        mid = msg.get('mid')
        peer = msg.get('peer') or self.current_chat_name
        gid = self.current_chat_gid if self.current_chat_type == 'group' else ''
        pin = not bool(msg.get('pinned'))
        msg['pinned'] = pin
        if pin:
            self.pinned[self.current_chat_id] = mid
        elif self.pinned.get(self.current_chat_id) == mid:
            self.pinned.pop(self.current_chat_id, None)
        sio.emit('pin_message', {'mid': mid, 'pin': pin, 'me': self.my_username,
                                 'peer': peer, 'group': gid})
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})
        self.show_toast("Pinned" if pin else "Unpinned")

    def _delete_msg(self, msg, scope):
        if not messagebox.askyesno("Delete",
                                   "Delete this message?" if scope == 'me'
                                   else "Delete this message for everyone?"):
            return
        mid = msg.get('mid')
        gid = self.current_chat_gid if self.current_chat_type == 'group' else ''
        peer = self.current_chat_name
        if scope == 'me':
            self._current_msgs = [m for m in getattr(self, '_current_msgs', [])
                                  if m.get('mid') != mid]
        else:
            for m in getattr(self, '_current_msgs', []):
                if m.get('mid') == mid:
                    m['deleted'] = True
                    m['text'] = ''
        sio.emit('delete_message', {'mid': mid, 'scope': scope, 'me': self.my_username,
                                    'peer': peer, 'group': gid})
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})

    # ============================================================
    # ATTACH MENU (image / video / audio / document / location / ...)
    # ============================================================
    def _queue_file(self, path):
        """Prepare a chosen file and open its in-panel preview."""
        if not path:
            return
        try:
            size = os.path.getsize(path)
            with open(path, 'rb') as fh:
                raw = fh.read()
        except Exception as e:
            self.notify("Attach file", f"Could not read file: {e}", kind='error')
            return
        limit = 25 * 1024 * 1024
        if size > limit:
            self.notify("File too large", f"Max {human_size(limit)}", kind='error')
            return
        name = os.path.basename(path)
        mime = mimetypes.guess_type(name)[0] or ''
        self._pending_file = {'path': path, 'name': name, 'mime': mime,
                              'kind': file_kind_of(name, mime), 'size': size,
                              'data': base64.b64encode(raw).decode('ascii')}
        self._show_file_preview()

    def _attach_pick(self, title, types):
        path = filedialog.askopenfilename(title=title, filetypes=types)
        if path:
            self._queue_file(path)

    def attach_menu(self):
        """Chooser: image / video / audio / document + location / contact / poll."""
        if self.current_chat_id is None:
            self.notify("Attach", "Pehle koi chat kholo", kind='error')
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Attach")
        dlg.configure(bg="#121212")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("340x430")
        tk.Label(dlg, text="Share something", bg="#121212", fg="#e9edef",
                 font=("Segoe UI", 14, "bold")).pack(pady=12)

        def pick(title, types, fn):
            dlg.destroy()
            fn(title, types)

        opts = [
            (ICON["photo"], "Image / Photo", lambda: pick(
                "Choose image", [("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                                 ("All files", "*.*")], self._attach_pick)),
            (ICON["video"], "Video", lambda: pick(
                "Choose video", [("Video", "*.mp4 *.mov *.avi *.mkv *.webm *.wmv"),
                                 ("All files", "*.*")], self._attach_pick)),
            (ICON["music"], "Audio", lambda: pick(
                "Choose audio", [("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.wma"),
                                 ("All files", "*.*")], self._attach_pick)),
            (ICON["doc"], "Document", lambda: pick(
                "Choose document", [("Documents", "*.pdf *.doc *.docx *.txt *.xls *.xlsx "
                                                  "*.ppt *.pptx *.csv"),
                                    ("All files", "*.*")], self._attach_pick)),
        ]
        for icon, label, cmd in opts:
            self._attach_row(dlg, icon, label, cmd)
        self._attach_row(dlg, "\U0001F4CD", "Location",
                         lambda: (dlg.destroy(), self._share_location()))
        self._attach_row(dlg, ICON["person"], "Contact",
                         lambda: (dlg.destroy(), self._share_contact()))
        self._attach_row(dlg, "\U0001F4CA", "Poll",
                         lambda: (dlg.destroy(), self._share_poll()))
        self._theme_subtree(dlg)

    def _attach_row(self, dlg, icon, label, cmd):
        fr = tk.Frame(dlg, bg="#1e1e1e", cursor="hand2")
        fr.pack(fill=tk.X, padx=16, pady=3)
        cv = tk.Canvas(fr, width=34, height=34, bg="#1e1e1e",
                       highlightthickness=0, bd=0)
        cv.pack(side=tk.LEFT, padx=10, pady=6)
        self._round_rect(cv, 0, 0, 34, 34, 9, "#25d366")
        cv.create_text(17, 17, text=icon, fill="white",
                       font=(self.icon_family, 15))
        tk.Label(fr, text=label, bg="#1e1e1e", fg="#e9edef",
                 font=("Segoe UI", 12), anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True, pady=8)
        self._bind_click_recursive(fr, lambda e: cmd())
        self._bind_hover_recursive(fr, fr, "#1e1e1e", "#2c2c2c")

    def _share_location(self):
        place = simpledialog.askstring("Share location", "Place / address:",
                                       parent=self.root)
        if place:
            self._emit_text_msg("\U0001F4CD Location: " + place)

    def _share_contact(self):
        name = simpledialog.askstring("Share contact", "Name:", parent=self.root)
        if not name:
            return
        phone = simpledialog.askstring("Share contact", "Phone / email (optional):",
                                       parent=self.root) or ""
        self._emit_text_msg("\U0001F464 Contact: %s  |  %s" % (name, phone))

    def _share_poll(self):
        q = simpledialog.askstring("Create poll", "Question:", parent=self.root)
        if not q:
            return
        raw = simpledialog.askstring("Create poll", "Options (comma separated):",
                                     parent=self.root)
        opts = [x.strip() for x in (raw or "").split(',') if x.strip()]
        if len(opts) < 2:
            self.notify("Poll", "Kam az kam 2 options do", kind='error')
            return
        self._emit_text_msg("\U0001F4CA Poll: %s\n%s" % (q, "\n".join(
            "%d. %s" % (i + 1, o) for i, o in enumerate(opts))))

    def emoji_menu(self):
        emojis = ["\U0001F600", "\U0001F602", "\U0001F60D", "\U0001F44D",
                  "\U0001F64F", "\U0001F525", "\u2764", "\U0001F389",
                  "\U0001F44C", "\U0001F622", "\U0001F621", "\U0001F60E",
                  "\U0001F44B", "\U0001F4A9", "\U0001F62D", "\U0001F618"]
        dlg = tk.Toplevel(self.root)
        dlg.title("Emoji")
        dlg.configure(bg="#121212")
        dlg.transient(self.root)
        f = tk.Frame(dlg, bg="#121212")
        f.pack(padx=10, pady=10)

        def pick(e):
            """Append the emoji and enable Send straight away (no Enter needed)."""
            try:
                self.mi_t.insert(tk.END, e)
                self.on_tc()                      # light up the Send button
            except Exception:
                pass

        for i, e in enumerate(emojis):
            tk.Button(f, text=e, font=("Segoe UI Emoji", 16), bg="#1e1e1e",
                      fg="white", bd=0, relief=tk.FLAT, cursor="hand2",
                      command=lambda e=e: pick(e)).grid(
                row=i // 8, column=i % 8, padx=2, pady=2)
        self._theme_subtree(dlg)

    # ============================================================
    # HISTORY FILTER / EXPORT / MEDIA / DIAGNOSTICS / MUTE
    # ============================================================
    def _msg_date(self, m):
        d = m.get('day')
        if d:
            try:
                return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
            except Exception:
                return None
        return None

    def _filter_history(self, msgs):
        period = getattr(self, 'history_period', 'All')
        if period == 'All':
            return msgs
        today = datetime.now().date()
        out = []
        for m in msgs:
            d = self._msg_date(m) or today
            if period == 'Today' and d == today:
                out.append(m)
            elif period == 'Yesterday' and d == today - timedelta(days=1):
                out.append(m)
            elif period == 'Last 7 Days' and today - timedelta(days=6) <= d <= today:
                out.append(m)
            elif period == 'This Week' and \
                    today - timedelta(days=today.weekday()) <= d <= today:
                out.append(m)
            elif period == 'This Month' and d.year == today.year and d.month == today.month:
                out.append(m)
        return out

    def history_filter_menu(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("History filter")
        dlg.configure(bg="#121212")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("300x330")
        tk.Label(dlg, text="Show history", bg="#121212", fg="#e9edef",
                 font=("Segoe UI", 14, "bold")).pack(pady=12)
        var = tk.StringVar(value=getattr(self, 'history_period', 'All'))
        for opt in ["All", "Today", "Yesterday", "Last 7 Days", "This Week",
                    "This Month"]:
            tk.Radiobutton(dlg, text=opt, variable=var, value=opt,
                           command=lambda o=opt: (setattr(self, 'history_period', o),
                                                  dlg.destroy(),
                                                  self.render_msgs(
                                                      {'messages': getattr(self, '_current_msgs', [])})),
                           bg="#121212", fg="#e9edef", selectcolor="#121212",
                           activebackground="#121212", activeforeground="white",
                           font=("Segoe UI", 11)).pack(anchor="w", padx=26, pady=3)
        self._theme_subtree(dlg)

    def export_chat(self):
        if self.current_chat_id is None:
            self.notify("Export", "Pehle koi chat kholo", kind='error')
            return
        path = filedialog.asksaveasfilename(
            title="Export chat", defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("JSON", "*.json")])
        if not path:
            return
        msgs = getattr(self, '_current_msgs', [])
        try:
            with open(path, 'w', encoding='utf-8') as f:
                if path.lower().endswith('.json'):
                    json.dump(msgs, f, ensure_ascii=False, indent=2)
                else:
                    for m in msgs:
                        who = 'You' if m.get('type') == 'sent' else \
                            (m.get('sender') or self.current_chat_name)
                        f.write("[%s] %s: %s\n" % (m.get('time', ''), who,
                                                   m.get('text', '')))
            self.notify("Export", "Saved: " + os.path.basename(path), kind='info')
        except Exception as e:
            self.notify("Export failed", str(e), kind='error')

    def _simple_window(self, title, lines):
        w = tk.Toplevel(self.root)
        w.title(title)
        w.configure(bg="#121212")
        w.geometry("560x380")
        box = tk.Text(w, bg="#1e1e1e", fg="#e9edef", bd=0, relief=tk.FLAT,
                      font=("Consolas", 10), wrap=tk.WORD)
        box.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        box.insert("1.0", "\n".join(lines) if lines else "(nothing)")
        box.configure(state='disabled')

    def group_media(self):
        msgs = [m for m in getattr(self, '_current_msgs', [])
                if (m.get('kind') or 'text') != 'text']
        self._simple_window("Shared media", [
            "%s  |  %s  |  %s" % (m.get('time', ''), m.get('file_kind', ''),
                                  m.get('file_name', '')) for m in msgs] or
            ["No media in this chat yet."])

    def send_msg(self):
        # a previewed attachment is sent with the same Send button / Enter key
        if self._pending_file is not None:
            self._send_pending_file()
            return
        txt = self.mi_t.get().strip()
        if not txt or self.current_chat_id is None:
            return
        self.mi_t.delete(0, tk.END)
        self.sb.set_enabled(False)
        self._emit_text_msg(txt)

    def on_tc(self, e=None):
        c = self.mi_t.get().strip()
        self.sb.set_enabled(bool(c) or self._pending_file is not None)

    def on_ep(self, e):
        if e.state & 0x1:
            return
        self.send_msg()
        return "break"
