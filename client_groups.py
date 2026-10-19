# client_groups.py — Group chats: info window, admin (add/remove/rename/photo/delete).
from client_core import *


class GroupMixin:

    # ============================================================
    # GROUP INFO  (creator name + IP, admin add / remove members)
    # ============================================================
    def open_group_info(self, u):
        """Group info window: creator + IP and admin member controls."""
        gid = u.get('gid')
        name = u.get('name') or 'Group'
        members = list(u.get('members') or [])
        creator = u.get('creator') or ''
        creator_ip = u.get('creator_ip') or ''
        is_admin = bool(creator) and (self.my_username == creator)

        w = tk.Toplevel(self.root)
        w.title("Group info")
        w.configure(bg='#121212')
        w.resizable(False, False)
        w.transient(self.root)
        try:
            w.geometry("440x600")
        except Exception:
            pass
        self._group_info_win = w
        self._group_info_gid = gid

        av = tk.Canvas(w, width=72, height=72, bg='#121212',
                       highlightthickness=0, bd=0)
        av.pack(pady=(18, 6))
        self._round_rect(av, 0, 0, 72, 72, 20, u.get('color', '#75b798'))
        av.create_text(36, 36, text=self._initials(name), fill='white',
                       font=("Segoe UI", 22, "bold"))
        name_lbl = tk.Label(w, text=name, bg='#121212', fg='#e9edef',
                            font=("Segoe UI", 15, "bold"))
        name_lbl.pack()
        who_lbl = tk.Label(w, text="", bg='#121212', fg='#8696a0',
                           font=("Segoe UI", 10))
        who_lbl.pack(pady=(2, 2))
        count_lbl = tk.Label(w, text="", bg='#121212', fg='#25d366',
                             font=("Segoe UI", 10, "bold"))
        count_lbl.pack(pady=(0, 6))
        admin_lbl = tk.Label(w, text="You are the admin", bg='#121212',
                             fg='#25d366', font=("Segoe UI", 10, "bold"))
        if is_admin:
            admin_lbl.pack()

        body = tk.Frame(w, bg='#1e1e1e')
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(10, 4))
        cv = tk.Canvas(body, bg='#1e1e1e', highlightthickness=0, bd=0)
        sb = tk.Scrollbar(body, orient=tk.VERTICAL, command=cv.yview)
        inner = tk.Frame(cv, bg='#1e1e1e')
        cv.create_window((0, 0), window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        inner.bind("<Configure>",
                   lambda e: cv.configure(scrollregion=cv.bbox("all")))
        self._bind_mousewheel_recursive(inner, cv)

        def rebuild():
            members[:] = [str(m) for m in (u.get('members') or []) if m]
            creator = u.get('creator') or ''
            is_admin = bool(creator) and self.my_username == creator
            for c in inner.winfo_children():
                c.destroy()
            for m in members:
                row = tk.Frame(inner, bg='#1e1e1e')
                row.pack(fill=tk.X, pady=1)
                rv = tk.Canvas(row, width=34, height=34, bg='#1e1e1e',
                               highlightthickness=0, bd=0)
                rv.pack(side=tk.LEFT, padx=(8, 10), pady=6)
                self._round_rect(rv, 0, 0, 34, 34, 10, '#2c2c2c')
                rv.create_text(17, 17, text=self._initials(m), fill='white',
                               font=("Segoe UI", 11, "bold"))
                tag = (" (admin)" if m == creator
                       else (" (you)" if m == self.my_username else ""))
                tk.Label(row, text=m + tag, bg='#1e1e1e', fg='#e9edef',
                         font=("Segoe UI", 11), anchor="w").pack(
                    side=tk.LEFT, fill=tk.X, expand=True)
                if is_admin and m != creator:
                    rb = RoundedButton(
                        row, text="Remove",
                        command=lambda mm=m: self._group_remove_member(
                            gid, mm, members, rebuild),
                        font=("Segoe UI", 9, "bold"), parent_bg='#1e1e1e',
                        width=68, height=26, radius=8,
                        active_bg='#e53935', active_fg='white',
                        inactive_bg='#2c2c2c', inactive_fg='#e9edef')
                    rb.set_active(False)
                    rb.pack(side=tk.RIGHT, padx=8)
            if not members:
                tk.Label(inner, text="(only you)", bg='#1e1e1e',
                         fg='#8696a0', font=("Segoe UI", 11)).pack(pady=20)
            # header: name, creator + IP, and a LIVE member count
            cur = u.get('name') or 'Group'
            name_lbl.configure(text=cur)
            who = ("Created by %s" % creator) if creator else "Group"
            if creator and (u.get('creator_ip') or ''):
                who += "   (%s)" % u.get('creator_ip')
            who_lbl.configure(text=who)
            n = len(members)
            count_lbl.configure(text="%d member%s" % (n, "" if n == 1 else "s"))
            try:
                av.delete("all")
                self._round_rect(av, 0, 0, 72, 72, 20, u.get('color', '#75b798'))
                av.create_text(36, 36, text=self._initials(cur), fill='white',
                               font=("Segoe UI", 22, "bold"))
            except Exception:
                pass
            if is_admin:
                try:
                    admin_lbl.pack()
                except Exception:
                    pass

        rebuild()
        # let the app re-render this window when the group changes elsewhere
        w._gi_update = lambda peer: rebuild()

        if is_admin:
            bf = tk.Frame(w, bg='#121212')
            bf.pack(pady=(8, 2))
            add = RoundedButton(bf, text="Add member",
                                command=lambda: self._group_add_member_dialog(
                                    u, members, rebuild),
                                font=("Segoe UI", 10, "bold"),
                                parent_bg='#121212', width=140, height=34,
                                radius=12, active_bg='#25d366',
                                active_fg='#0b1a0e', inactive_bg='#2c2c2c',
                                inactive_fg='#e9edef')
            add.set_active(True)
            add.pack(side=tk.LEFT, padx=4)
            rn = RoundedButton(bf, text="Change name",
                               command=lambda: self._group_change_name(u, rebuild),
                               font=("Segoe UI", 10, "bold"),
                               parent_bg='#121212', width=134, height=34,
                               radius=12, active_bg='#2196f3',
                               active_fg='white', inactive_bg='#2c2c2c',
                               inactive_fg='#e9edef')
            rn.set_active(False)
            rn.pack(side=tk.LEFT, padx=4)

            bf2 = tk.Frame(w, bg='#121212')
            bf2.pack(pady=(2, 10))
            rp = RoundedButton(bf2, text="Change photo",
                               command=lambda: self._group_change_photo(u, rebuild),
                               font=("Segoe UI", 10, "bold"),
                               parent_bg='#121212', width=140, height=34,
                               radius=12, active_bg='#2196f3',
                               active_fg='white', inactive_bg='#2c2c2c',
                               inactive_fg='#e9edef')
            rp.set_active(False)
            rp.pack(side=tk.LEFT, padx=4)
            rd = RoundedButton(bf2, text="Delete group",
                               command=lambda: self._group_delete(u),
                               font=("Segoe UI", 10, "bold"),
                               parent_bg='#121212', width=134, height=34,
                               radius=12, active_bg='#e53935',
                               active_fg='white', inactive_bg='#2c2c2c',
                               inactive_fg='#e9edef')
            rd.set_active(False)
            rd.pack(side=tk.LEFT, padx=4)
        self._theme_subtree(w)

    def _group_change_name(self, u, refresh=None):
        """Admin: rename the group (pushed to every member)."""
        gid = u.get('gid')
        cur = u.get('name') or 'Group'
        try:
            new = simpledialog.askstring("Change group name",
                                         "New group name:",
                                         initialvalue=cur, parent=self.root)
        except Exception:
            new = None
        new = (new or '').strip()
        if not new or new == cur:
            return
        try:
            sio.emit('group_rename', {'gid': gid, 'name': new,
                                      'from': self.my_username})
        except Exception:
            pass
        # optimistic local update
        for p in getattr(self, '_peers', []):
            if p.get('gid') == gid:
                p['name'] = new
                break
        if refresh:
            try:
                refresh()
            except Exception:
                pass
        self.refresh_middle_list()
        self._save_ui_state()
        self.show_toast("Group renamed")

    def _group_change_photo(self, u, refresh=None):
        """Admin: pick a new group profile photo and push it to members."""
        gid = u.get('gid')
        try:
            path = filedialog.askopenfilename(
                title="Choose a group photo",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                           ("All files", "*.*")])
        except Exception:
            path = None
        if not path:
            return
        b64 = ''
        try:
            raw = self._square_photo_bytes(path, 192)
            if raw:
                b64 = base64.b64encode(raw).decode('ascii')
        except Exception:
            b64 = ''
        if not b64:
            self.notify("Group photo", "Could not read that image", kind='error')
            return
        try:
            sio.emit('group_set_pic', {'gid': gid, 'pic': b64,
                                       'from': self.my_username})
        except Exception:
            pass
        for p in getattr(self, '_peers', []):
            if p.get('gid') == gid:
                p['pic'] = b64
                break
        self.refresh_middle_list()
        self._save_ui_state()
        self.show_toast("Group photo updated")

    def _group_remove_member(self, gid, member, members, refresh=None):
        try:
            sio.emit('group_remove_member',
                     {'gid': gid, 'member': member, 'from': self.my_username})
        except Exception:
            pass
        # optimistic local update so the UI reacts instantly
        try:
            if member in members:
                members.remove(member)
        except Exception:
            pass
        for u in getattr(self, '_peers', []):
            if u.get('gid') == gid:
                try:
                    u['members'] = [m for m in (u.get('members') or [])
                                    if m != member]
                except Exception:
                    pass
                break
        if refresh:
            try:
                refresh()
            except Exception:
                pass
        self.refresh_middle_list()
        self._save_ui_state()
        self.show_toast("Removed %s" % member)

    def _group_delete(self, u):
        """Admin: delete the whole group for every member."""
        gid = u.get('gid')
        name = u.get('name') or 'this group'
        try:
            ok = messagebox.askyesno(
                "Delete group",
                "Delete \u201c%s\u201d for everyone?\n\n"
                "The group and its messages are removed for all members.\n"
                "This cannot be undone." % name,
                icon='warning', parent=self.root)
        except Exception:
            ok = True
        if not ok:
            return
        try:
            sio.emit('group_delete', {'gid': gid, 'from': self.my_username})
        except Exception:
            pass
        # optimistic local removal (the server confirms with 'group_deleted')
        self._remove_group_local(gid)
        self.show_toast("Group deleted")

    def _remove_group_local(self, gid, name=''):
        """Drop a group (by gid) from the middle list + close it if open."""
        try:
            self._peers = [p for p in getattr(self, '_peers', [])
                           if p.get('gid') != gid]
        except Exception:
            pass
        if getattr(self, 'current_chat_gid', None) == gid:
            try:
                self._close_open_chat()
            except Exception:
                pass
        # close an open Group-info window for this group
        try:
            if getattr(self, '_group_info_gid', None) == gid:
                win = getattr(self, '_group_info_win', None)
                if win is not None and win.winfo_exists():
                    win.destroy()
                self._group_info_win = None
                self._group_info_gid = None
        except Exception:
            pass
        self.refresh_middle_list()
        self._save_ui_state()

    def _group_add_member_dialog(self, u, members, refresh=None):
        gid = u.get('gid')
        cands = [c for c in self._peer_candidates()
                 if c.get('username')
                 and c.get('username') not in set(members)
                 and c.get('username') not in getattr(self, 'blocked', set())]
        dlg = tk.Toplevel(self.root)
        dlg.title("Add member")
        dlg.configure(bg='#121212')
        dlg.resizable(False, False)
        dlg.transient(self.root)
        try:
            dlg.geometry("390x430")
        except Exception:
            pass
        tk.Label(dlg, text="Add member to %s" % (u.get('name') or 'Group'),
                 bg='#121212', fg='#e9edef',
                 font=("Segoe UI", 13, "bold")).pack(pady=(14, 8))
        body = tk.Frame(dlg, bg='#1e1e1e')
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)
        if not cands:
            tk.Label(body, text="No other clients are online",
                     bg='#1e1e1e', fg='#8696a0',
                     font=("Segoe UI", 11)).pack(pady=30)
        for c in cands:
            nm = c.get('username')
            row = tk.Frame(body, bg='#1e1e1e', cursor="hand2")
            row.pack(fill=tk.X, pady=1)
            rv = tk.Canvas(row, width=32, height=32, bg='#1e1e1e',
                           highlightthickness=0, bd=0)
            rv.pack(side=tk.LEFT, padx=(8, 10), pady=6)
            self._round_rect(rv, 0, 0, 32, 32, 10, '#2c2c2c')
            rv.create_text(16, 16, text=self._initials(nm), fill='white',
                           font=("Segoe UI", 10, "bold"))
            tk.Label(row, text="%s   (%s)" % (nm, c.get('ip', '?')),
                     bg='#1e1e1e', fg='#e9edef', font=("Segoe UI", 11),
                     anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

            def add(e=None, nm=nm):
                try:
                    sio.emit('group_add_member',
                             {'gid': gid, 'member': nm,
                              'from': self.my_username})
                except Exception:
                    pass
                try:
                    if nm not in members:
                        members.append(nm)
                except Exception:
                    pass
                for p in getattr(self, '_peers', []):
                    if p.get('gid') == gid:
                        p.setdefault('members', [])
                        if nm not in p['members']:
                            p['members'].append(nm)
                        break
                self.show_toast("Added %s" % nm)
                try:
                    dlg.destroy()
                except Exception:
                    pass
                if refresh:
                    try:
                        refresh()
                    except Exception:
                        pass
                self.refresh_middle_list()
                self._save_ui_state()

            self._bind_click_recursive(row, add)
            self._bind_hover_recursive(row, row, '#1e1e1e', '#2c2c2c')
        self._theme_subtree(dlg)

    def _group_members_line(self, u):
        """'5 members  ·  Ali, Bob, Carol…' shown under a group's title."""
        members = [str(m) for m in (u.get('members') or []) if m]
        n = len(members)
        head = "%d member%s" % (n, "" if n == 1 else "s")
        if not members:
            return head
        line = head + "  \u00b7  " + ", ".join(members)
        if len(line) > 48:
            line = line[:47] + "\u2026"
        return line

    def _refresh_open_group_header(self, u):
        """Update the open chat's header after a group rename/photo/member change."""
        try:
            self.current_chat_name = u.get('name') or self.current_chat_name
            self.current_chat_color = u.get('color', self.current_chat_color)
            self.current_chat_avatar = u.get('avatar', self.current_chat_avatar)
            self.ha.delete("all")
            self._draw_avatar(self.ha, 40, 12, self.current_chat_name,
                              self.current_chat_color, u.get('pic', ''))
            disp = self.current_chat_name or ''
            if len(disp) > 20:
                disp = disp[:19] + "\u2026"
            self.cn.configure(text=disp)
            # a group shows its total members *and* their names, live
            self.sd.configure(fg='#25d366')
            self.st.configure(text=self._group_members_line(u), fg='#8696a0')
        except Exception:
            pass
        # keep an open Group-info window in sync too
        self._refresh_group_info_window(u)

    def _refresh_group_info_window(self, u):
        """Re-render the Group-info window if it is open for this group."""
        try:
            if u.get('gid') != getattr(self, '_group_info_gid', None):
                return
            win = getattr(self, '_group_info_win', None)
            if win is None or not win.winfo_exists():
                return
            win._gi_update(u)
        except Exception:
            pass

    def _add_group(self, g):
        """Add (or refresh) a group in the middle chat list."""
        gid = g.get('id')
        name = g.get('name') or 'Group'
        pic = g.get('avatar', '')
        peers = getattr(self, '_peers', [])
        for u in peers:
            if (gid and u.get('gid') == gid) or u.get('name') == name:
                u['gid'] = gid or u.get('gid')
                u['type'] = 'group'
                u['name'] = name
                u['status'] = 'active'
                u['members'] = g.get('members', u.get('members'))
                if g.get('creator'):
                    u['creator'] = g.get('creator')
                u['creator_ip'] = g.get('creator_ip', u.get('creator_ip', ''))
                if pic:
                    u['pic'] = pic
                # a fresh group event bumps it to the top of the list
                u['_act'] = datetime.now().timestamp()
                # if this group is currently open, refresh its header live
                if gid and gid == getattr(self, 'current_chat_gid', None):
                    self._refresh_open_group_header(u)
                else:
                    self._refresh_group_info_window(u)
                self.refresh_middle_list()
                self._save_ui_state()
                return
        nid = max([u.get('id', 0) for u in peers] + [0]) + 1
        peers.append({
            'id': nid, 'name': name, 'type': 'group', 'gid': gid,
            'avatar': self._initials(name), 'color': '#75b798', 'status': 'active',
            'members': g.get('members', []), 'lastMsg': 'Group created',
            'time': datetime.now().strftime("%H:%M"), 'unread': 0,
            'pinned': False, 'pin_ts': 0, '_act': datetime.now().timestamp(),
            'creator': g.get('creator', ''), 'creator_ip': g.get('creator_ip', ''),
            'pic': pic or '',
        })
        self._peers = peers
        if self.current_view != 'chats':
            self.switch_view('chats')
        else:
            self.refresh_middle_list()
        self._save_ui_state()

    def create_group(self):
        """Dialog: group name + click clients to add them, then create."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Create Group")
        dlg.configure(bg="#121212")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        w, h = 460, 520
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - w) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dlg, text="Create Group", bg="#121212", fg="#e9edef",
                 font=("Segoe UI", 15, "bold")).pack(pady=(16, 2))
        tk.Label(dlg, text="Group name", bg="#121212", fg="#8696a0",
                 font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=26, pady=(8, 2))
        name_e = tk.Entry(dlg, bg="#1e1e1e", fg="white", insertbackground="#25d366",
                          relief=tk.FLAT, bd=0, font=("Segoe UI", 12))
        name_e.pack(fill=tk.X, padx=26, ipady=6)
        name_e.focus_set()

        tk.Label(dlg, text="Select clients (click to add)", bg="#121212", fg="#8696a0",
                 font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=26, pady=(12, 4))

        body = tk.Frame(dlg, bg="#1e1e1e")
        body.pack(fill=tk.BOTH, expand=True, padx=26)
        cv = tk.Canvas(body, bg="#1e1e1e", highlightthickness=0, bd=0)
        sb = tk.Scrollbar(body, orient=tk.VERTICAL, command=cv.yview)
        inner = tk.Frame(cv, bg="#1e1e1e")
        cv.create_window((0, 0), window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))

        selected = set()
        cands = self._peer_candidates()
        if not cands:
            tk.Label(inner, text="No clients connected yet", bg="#1e1e1e",
                     fg="#6b7780", font=("Segoe UI", 11)).pack(pady=30)
        for c in cands:
            nm = c.get('username', '?')
            row = tk.Frame(inner, bg="#1e1e1e", cursor="hand2")
            row.pack(fill=tk.X, pady=1)
            box = tk.Canvas(row, width=22, height=22, bg="#1e1e1e",
                            highlightthickness=0, bd=0)
            box.pack(side=tk.LEFT, padx=(10, 10), pady=8)

            def draw_box(sel, box=box):
                box.delete("all")
                self._round_rect(box, 2, 2, 20, 20, 6,
                                 self._tbg("#25d366") if sel else self._tbg("#3a3a3a"))
                if sel:
                    box.create_text(11, 11, text="\u2713", fill="#0b1a0e",
                                    font=("Segoe UI", 11, "bold"))

            draw_box(False)
            tk.Label(row, text=f"{nm}   ({c.get('ip', '?')})", bg="#1e1e1e",
                     fg="#e9edef", font=("Segoe UI", 11), anchor="w").pack(
                side=tk.LEFT, fill=tk.X, expand=True)

            def toggle(e=None, nm=nm, draw=draw_box):
                if nm in selected:
                    selected.discard(nm)
                else:
                    selected.add(nm)
                draw(nm in selected)

            self._bind_click_recursive(row, toggle)
            self._bind_hover_recursive(row, row, "#1e1e1e", "#2c2c2c")

        self._bind_mousewheel_recursive(inner, cv)

        err = tk.Label(dlg, text="", bg="#121212", fg="#ff5c5c",
                       font=("Segoe UI", 10, "bold"))
        err.pack(pady=(8, 0))

        def cancel():
            try:
                dlg.grab_release()
            except Exception:
                pass
            dlg.destroy()

        def submit(_=None):
            gname = name_e.get().strip()
            if not gname:
                err.configure(text="Enter a group name")
                return
            if not selected:
                err.configure(text="Select at least one client")
                return
            sio.emit('create_group', {'name': gname, 'members': sorted(selected),
                                      'creator': self.my_username})
            cancel()
            self.show_toast(f"Creating group '{gname}'")

        bf = tk.Frame(dlg, bg="#121212")
        bf.pack(pady=14)
        tk.Button(bf, text="Create", command=submit, bg="#25d366", fg="#0b1a0e",
                  font=("Segoe UI", 11, "bold"), bd=0, relief=tk.FLAT,
                  cursor="hand2", width=10).pack(side=tk.LEFT, padx=8)
        tk.Button(bf, text="Cancel", command=cancel, bg="#2c2c2c", fg="white",
                  font=("Segoe UI", 11, "bold"), bd=0, relief=tk.FLAT,
                  cursor="hand2", width=10).pack(side=tk.LEFT, padx=8)
        dlg.bind("<Return>", submit)
        dlg.bind("<Escape>", lambda e: cancel())
        self._theme_subtree(dlg)

    def _group_info(self):
        if self.current_chat_type != 'group':
            self.notify("Group info", "Ye group chat nahi hai", kind='info')
            return
        u = None
        for p in getattr(self, '_peers', []):
            if p.get('gid') == self.current_chat_gid:
                u = p
                break
        if u is None:
            u = {'name': self.current_chat_name, 'gid': self.current_chat_gid,
                 'members': [], 'creator': '', 'creator_ip': '',
                 'color': getattr(self, 'current_chat_color', '#75b798')}
        self.open_group_info(u)
