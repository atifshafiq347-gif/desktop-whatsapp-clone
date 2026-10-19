# client_net.py — Socket connection, event handlers, session restore/save.
from client_core import *


class NetMixin:

    def _ui(self, fn):
        """Run `fn` on the Tk main thread, safely.

        Socket callbacks arrive on a background thread; scheduling them with
        `root.after` is required, but if the window has already been closed Tk
        raises 'main thread is not in main loop'.  Swallow that so a shutdown
        never dumps a traceback on the terminal.
        """
        try:
            self.root.after(0, fn)
        except (RuntimeError, tk.TclError):
            pass

    # ============================================================
    # SOCKET CONNECTION (LAN)
    # ============================================================
    def connect_to_server(self):
        def ct():
            # ---- register EVERY handler *before* connecting ----------------
            # python-socketio silently drops events that arrive before a
            # handler is bound.  The server answers 'join' with restore_state,
            # user_list and the client list within milliseconds; binding the
            # handlers first guarantees none of those are missed, which is
            # what makes session restore immediate.
            @sio.on('server_full')
            def sf(d):
                self._ui(lambda: (
                    self.show_toast(d.get('message', 'Server Full')),
                    self.notify("Server full", d.get('message', ''), kind='error')))

            @sio.on('login_rejected')
            def lr(d):
                self._ui(lambda: self._on_login_rejected(d))

            @sio.on('messages_history')
            def mh(d):
                self._ui(lambda: self._on_history(d))

            @sio.on('new_message')
            def nm(d):
                self._ui(lambda: self._on_incoming(d))

            @sio.on('message_sent')
            def mst(d):
                self._ui(lambda: self._on_sent(d))

            @sio.on('message_delivered')
            def mdl(d):
                self._ui(lambda: self._on_delivered(d))

            @sio.on('message_undelivered')
            def mud(d):
                self._ui(lambda: self._on_undelivered(d))

            @sio.on('messages_read')
            def mrd(d):
                self._ui(lambda: self._on_read(d))

            @sio.on('settings_updated')
            def su(d):
                # only acknowledge *my own* settings change; never show a
                # notification when another client changes their settings
                if d.get('username') and d.get('username') != self.my_username:
                    return
                self._ui(lambda: self.notify(
                    "Settings updated", "Preferences saved on the server",
                    kind='settings'))

            @sio.on('server_broadcast')
            def sb(d):
                self._ui(lambda: self._on_server_direct(d.get('message', '')))

            @sio.on('server_dm')
            def sdm(d):
                self._ui(lambda: self._on_server_direct(d.get('message', '')))

            @sio.on('server_config')
            def scfg(d):
                self._ui(lambda: self._on_server_config(d))

            @sio.on('connected_clients_list')
            def ccl(d):
                self._ui(lambda: self._on_clients_list(d))

            @sio.on('groups_list')
            def gl(d):
                self._ui(lambda: [self._add_group(g) for g in d.get('groups', [])])

            @sio.on('group_created')
            def gc(d):
                self._ui(lambda: self._on_group_created(d))

            @sio.on('group_updated')
            def gu(d):
                self._ui(lambda: self._on_group_updated(d))

            @sio.on('group_removed')
            def grm(d):
                self._ui(lambda: self._on_group_removed(d))

            @sio.on('group_deleted')
            def gdel(d):
                self._ui(lambda: self._on_group_deleted(d))

            @sio.on('group_error')
            def ge(d):
                self._ui(lambda: self._on_group_error(d))

            @sio.on('blocked_list')
            def bl(d):
                self._ui(lambda: self._on_blocked_list(d))

            @sio.on('clients_changed')
            def cc(d):
                self._ui(lambda: self._refresh_clients())

            @sio.on('user_online')
            def uon(d):
                self._ui(lambda: self._on_user_online(d))

            @sio.on('user_offline')
            def uo(d):
                self._ui(lambda: self._on_user_offline(d))

            @sio.on('user_profile')
            def up(d):
                self._ui(lambda: self._on_user_profile(d))

            @sio.on('restore_state')
            def rs(d):
                self._ui(lambda: self._on_restore_state(d))

            @sio.on('message_pinned')
            def mp(d):
                self._ui(lambda: self._on_msg_pinned(d))

            @sio.on('message_deleted')
            def md(d):
                self._ui(lambda: self._on_msg_deleted(d))

            @sio.on('message_reacted')
            def mrx(d):
                self._ui(lambda: self._on_msg_reacted(d))

            @sio.on('message_starred')
            def mst(d):
                self._ui(lambda: self._on_msg_starred(d))

            @sio.on('chats_cleared')
            def mcl(d):
                self._ui(lambda: self._on_chats_cleared(d))

            @sio.on('chat_cleared')
            def chatcl(d):
                self._ui(lambda: self._on_chat_cleared(d))

            # ---- live call signalling ----
            @sio.on('incoming_call')
            def incoming_call(d):
                self._ui(lambda: self._on_incoming_call(d))

            @sio.on('call_accepted')
            def call_accepted(d):
                self._ui(lambda: self._on_call_accepted(d))

            @sio.on('call_rejected')
            def call_rejected(d):
                self._ui(lambda: self._on_call_rejected(d))

            @sio.on('call_ended')
            def call_ended(d):
                self._ui(lambda: self._on_call_ended(d))

            @sio.on('call_peer_left')
            def call_peer_left(d):
                self._ui(lambda: self._on_call_peer_left(d))

            @sio.on('call_video')
            def call_video(d):
                self._ui(lambda: self._on_call_video(d))

            @sio.on('call_upgraded')
            def call_upgraded(d):
                self._ui(lambda: self._on_call_upgraded(d))

            @sio.on('call_offline')
            def call_offline(d):
                self._ui(lambda: self._on_call_offline(d))

            @sio.on('call_media')
            def call_media(d):
                # high-frequency stream: hand straight to the call window
                w = getattr(self, '_call', None)
                if w is not None:
                    w.on_media(d)

            @sio.on('call_recorded')
            def call_recorded(d):
                self._ui(lambda: self._on_call_recorded(d))

            try:
                sio.connect(self.server_url)
                sio.emit('join', {'username': self.my_username,
                                  'avatar': self.my_pic})
                # ask for the live client list straight away instead of
                # waiting on the old 800/1500 ms timers
                sio.emit('get_connected_clients')
                # pull the persisted block list right away
                sio.emit('get_blocked')
                self._ui(lambda: self.notify(
                    "Connected", f"{self.my_username} \u2022 {self.server_url}", kind='info'))
                sio.wait()
            except Exception as e:
                msg = (str(e).strip() or e.__class__.__name__)[:90]
                self._ui(lambda: (
                    self.show_toast(f"Cannot connect: {self.server_url}"),
                    self.notify("Connection failed",
                                "Could not reach %s  (%s) - check the LAN address "
                                "shown on the server dashboard, and that both "
                                "laptops are on the same Wi-Fi."
                                % (self.server_url, msg),
                                kind='error')))

        threading.Thread(target=ct, daemon=True).start()
        # Light safety-net poll only (live updates arrive via events anyway);
        # the initial client list is requested the moment 'join' is sent.
        self.root.after(5000, self._poll_clients)

    def _on_user_online(self, d):
        name = d.get('username')
        if not name or name == self.my_username:
            return
        # reflect the change immediately, in place - no list re-render
        self._mark_peer_status(name, 'active', sid=d.get('sid'))
        self.notify("Client online", name, kind='client')

    def _on_user_offline(self, d):
        name = d.get('username')
        if not name or name == self.my_username:
            return
        self._mark_peer_status(name, 'offline')
        self.notify("Client offline", name, kind='offline')

    def _on_user_profile(self, d):
        """A contact changed their profile photo -> update just their row."""
        name = d.get('username')
        pic = d.get('avatar', '')
        if not name or name == self.my_username:
            return
        for u in getattr(self, '_peers', []):
            if u.get('name') == name:
                u['pic'] = pic
                self._set_row_avatar(u.get('id'), u.get('name'), u.get('color', ''),
                                     pic, u.get('status', 'active'))
        if self.current_chat_name == name:
            self._draw_avatar(self.ha, 40, 12, self.current_chat_name,
                              self.current_chat_color, pic)

    # ============================================================
    # SESSION RESTORE (same IP -> same screen it was left on)
    # ============================================================
    def _on_login_rejected(self, d):
        """The same name is already signed in from this IP on another session.

        The server refused our 'join'. We tell the user and keep retrying in
        the background until the other session logs out (then the join lands).
        """
        self._joined = False
        msg = (d.get('message')
               or ('%s is already logged in on another device.'
                   % self.my_username))
        self.show_toast(msg)
        self.notify("Already logged in",
                    msg + "\nOnly one session per name/IP is allowed.",
                    kind='warn', duration=8000)
        if not getattr(self, '_join_retry_on', False):
            self._join_retry_on = True
            try:
                self.root.after(5000, self._retry_join)
            except Exception:
                pass

    def _retry_join(self):
        """Re-attempt the 'join' every few seconds while another session holds
        our identity (name + IP). Stops the moment the server accepts us."""
        if getattr(self, '_joined', False):
            self._join_retry_on = False
            return
        try:
            if getattr(sio, 'connected', False):
                sio.emit('join', {'username': self.my_username,
                                  'avatar': self.my_pic})
        except Exception:
            pass
        try:
            self.root.after(5000, self._retry_join)
        except Exception:
            pass

    def _on_restore_state(self, d):
        """The server remembered this machine (keyed by IP). Bring it all back:
        name, profile photo, settings, contacts, last view and last open chat."""
        # a successful join clears any 'already logged in' wait state
        self._joined = True
        self._join_retry_on = False
        name = (d.get('username') or '').strip()
        settings = d.get('settings') or {}
        returning = bool(d.get('returning'))
        if name and returning:
            self.my_username = name
        pic = d.get('avatar') or ''
        restored_pic = False
        if pic and pic != self.my_pic:
            self.my_pic = pic
            restored_pic = True
        if d.get('color'):
            self.my_color = d.get('color')

        # name + avatar in the left sidebar
        try:
            self.me_lbl.configure(text=self.my_username[:12])
            self._render_my_avatar()
        except Exception:
            pass

        # contacts (middle list) — sid/status get refreshed from the live list
        contacts = d.get('contacts') or []
        for c in contacts:
            self._restore_contact(c)

        # saved preferences
        self._apply_saved_settings(settings)

        # last view + last open chat
        self._pending_chat_name = (d.get('chat') or '').strip()
        view = (d.get('view') or 'chats').strip() or 'chats'
        try:
            self.switch_view(view)
        except Exception:
            self.switch_view('chats')
        self._try_open_pending_chat()

        # the Calls tab is part of the session too
        try:
            self._load_call_history(d.get('calls'))
        except Exception:
            pass

        if returning:
            self.notify("Welcome back", f"{self.my_username} \u2022 session restored",
                        kind='info')
            if restored_pic:
                self.show_toast("Profile photo restored")
        elif contacts:
            self.notify("Restored", f"{len(contacts)} chats brought back", kind='info')

    def _apply_saved_settings(self, s):
        """Re-apply the preferences stored in the database."""
        if not isinstance(s, dict) or not s:
            return
        # theme
        t = s.get('theme')
        if t:
            try:
                self.apply_theme(t, save=False)
                self.tv.set(self.theme_name)
            except Exception:
                pass
        # profile colour
        if s.get('profile_color'):
            self.my_color = s['profile_color']
            try:
                self.pc.set(s['profile_color'])
            except Exception:
                pass
        # 12 / 24 hour clock
        tf = s.get('time_format')
        if tf:
            self.time_24h = (tf != '12-hour')
            try:
                self.timef_var.set('24-hour' if self.time_24h else '12-hour')
            except Exception:
                pass
            try:
                if self.current_chat_id is not None:
                    self.render_msgs({'messages': getattr(self, '_current_msgs', [])})
            except Exception:
                pass
        if s.get('avatar') and not self.my_pic:
            self.my_pic = s['avatar']
        # notification ringtone
        rt = s.get('ringtone')
        if rt:
            self.ringtone_label = rt
            path = s.get('ringtone_path') or ''
            if rt.startswith('Custom:') and path and os.path.exists(path):
                self.custom_ringtone_path = path
                self.ringtone.set_file(path)
            elif rt != 'None':
                self.ringtone.set_file(self.ringtone.set_label(rt))
        try:
            nv = int(s.get('notification_volume', self.ringtone.volume))
            self.ringtone.set_volume(nv)
        except Exception:
            pass
        # call ringtone
        ct = s.get('call_ringtone')
        if ct:
            self.call_ringtone_label = ct
            path = s.get('call_ringtone_path') or ''
            if ct.startswith('Custom:') and path and os.path.exists(path):
                self.custom_call_ringtone_path = path
                self.call_ringtone.set_file(path)
            elif ct != 'None':
                self.call_ringtone.set_file(self.call_ringtone.set_label(ct))
        try:
            cv = int(s.get('call_volume', self.call_ringtone.volume))
            self.call_ringtone.set_volume(cv)
        except Exception:
            pass

    def _restore_contact(self, c):
        """Rebuild one stored contact row inside the middle list."""
        name = c.get('peer') or c.get('name')
        if not name or name == self.my_username:
            return
        is_srv = (name == 'Server')
        stored_msg = c.get('last_msg') or ''
        peers = getattr(self, '_peers', [])
        for u in peers:
            if u.get('name') == name:
                u['pic'] = c.get('peer_pic', u.get('pic', ''))
                u['lastMsg'] = stored_msg or u.get('lastMsg', '')
                u['unread'] = int(c.get('unread', 0) or 0)
                u['pinned'] = bool(int(c.get('pinned', 0) or 0))
                u['pin_ts'] = float(c.get('pin_ts') or 0)
                u['_act'] = float(c.get('last_ts') or u.get('_act', 0) or 0)
                if is_srv:
                    # the dashboard chat only comes back if it ever messaged us
                    u['is_server'] = True
                    u['hidden'] = not bool(stored_msg)
                self.refresh_middle_list()
                return
        ptype = c.get('peer_type') or 'single'
        entry = {
            'id': self._next_peer_id(),
            'name': name,
            'sid': None,
            'avatar': (c.get('peer_avatar') or self._initials(name)).upper(),
            'pic': c.get('peer_pic', ''),
            'color': c.get('peer_color') or '#2c2c2c',
            'status': 'active' if is_srv else 'offline',
            'lastMsg': stored_msg or ('Tap to start chatting' if not is_srv else ''),
            'time': c.get('last_time') or '',
            'unread': int(c.get('unread', 0) or 0),
            'type': ptype,
            'gid': None,
            'members': [],
            'pinned': bool(int(c.get('pinned', 0) or 0)),
            'pin_ts': float(c.get('pin_ts') or 0),
            '_act': float(c.get('last_ts') or 0),
        }
        if is_srv:
            entry['is_server'] = True
            entry['hidden'] = not bool(stored_msg)
        peers.append(entry)
        self.refresh_middle_list()

    def _next_peer_id(self):
        peers = getattr(self, '_peers', [])
        nid = max([u.get('id', 0) for u in peers] + [0]) + 1
        self._peer_seq = max(getattr(self, '_peer_seq', 0), nid)
        return self._peer_seq

    def _ensure_server_peer(self):
        """The dashboard contact - kept hidden until it actually messages us."""
        peers = getattr(self, '_peers', [])
        for u in peers:
            if u.get('is_server') or u.get('name') == 'Server':
                u['is_server'] = True
                u['status'] = 'active'
                u['type'] = 'single'
                if 'hidden' not in u:
                    u['hidden'] = True
                return u
        nid = self._next_peer_id()
        u = {
            'id': nid, 'name': 'Server', 'sid': None, 'avatar': 'SV',
            'pic': '', 'color': '#00806a', 'status': 'active',
            'lastMsg': '', 'time': '',
            'unread': 0, 'type': 'single', 'is_server': True,
            'hidden': True,
        }
        peers.append(u)
        self._peers = peers
        try:
            self.refresh_middle_list()
        except Exception:
            pass
        return u

    def _reveal_server_peer(self):
        """Show the 'Server' chat now that it has sent us a message."""
        u = self._ensure_server_peer()
        if u is not None and u.get('hidden'):
            u['hidden'] = False
            try:
                self.refresh_middle_list()
            except Exception:
                pass
        return u

    def _on_server_config(self, d):
        """The server changed a limit (e.g. max clients) -> reflect it here."""
        try:
            mx = int(d.get('max_clients') or 0)
        except Exception:
            mx = 0
        if mx and mx != getattr(self, 'server_max', None):
            self.server_max = mx
            self.notify("Server limit changed",
                        f"Max clients ab {mx} hai", kind='settings')
        elif mx:
            self.server_max = mx
        self.update_client_count(max(0, getattr(self, '_client_total', 0)))
        # live-refresh the Settings screen if it is open
        if self.current_view == 'settings':
            try:
                self.show_settings_inline()
            except Exception:
                pass

    def _on_server_direct(self, text):
        """Fallback: a raw server broadcast/DM -> show it as a chat from 'Server'."""
        if not text:
            return
        u = self._reveal_server_peer()
        u['hidden'] = False
        ts = datetime.now().strftime("%H:%M")
        u['lastMsg'] = text
        u['time'] = ts
        if (self.current_view == 'chats' and self.current_chat_type == 'single'
                and self.current_chat_name == 'Server'):
            self.add_msg({'text': text, 'type': 'received', 'time': ts})
            self._update_chat_preview(u['id'], text, ts)
            self._touch_chat(u['id'])
        else:
            u['unread'] = u.get('unread', 0) + 1
            # a fresh server message jumps the Server chat to the top
            self._touch_chat(u['id'])
        self.notify("Server", text, kind='message')
        if self.ringtone.path:
            self.ringtone.play()

    def _open_chat_by_name(self, name):
        for u in getattr(self, '_peers', []):
            if u.get('name') == name:
                self.open_chat(u)
                return True
        return False

    def _try_open_pending_chat(self):
        name = getattr(self, '_pending_chat_name', '')
        if not name:
            return
        if self._open_chat_by_name(name):
            self._pending_chat_name = ''

    def _save_ui_state(self):
        """Persist where we are (view + open chat + contacts) for the next login."""
        if not sio.connected:
            return
        try:
            peers = []
            for u in getattr(self, '_peers', []):
                peers.append({'name': u.get('name'), 'type': u.get('type', 'single'),
                              'avatar': u.get('avatar', ''), 'color': u.get('color', ''),
                              'pic': u.get('pic', ''), 'lastMsg': u.get('lastMsg', ''),
                              'time': u.get('time', ''), 'unread': u.get('unread', 0),
                              'pinned': 1 if u.get('pinned') else 0,
                              'pin_ts': float(u.get('pin_ts') or 0),
                              'last_ts': float(u.get('_act') or 0)})
            view = getattr(self, 'current_view', 'chats')
            if view not in ('chats', 'calls', 'settings'):
                view = 'chats'
            sio.emit('save_ui_state', {
                'view': view,
                'chat': self.current_chat_name or getattr(self, '_pending_chat_name', '') or '',
                'contacts': peers,
            })
        except Exception:
            pass

    def _refresh_clients(self):
        if sio.connected:
            sio.emit('get_connected_clients')

    def _on_clients_list(self, d):
        """Track every connected client so we can add them by IP and reach them."""
        clients = d.get('clients', [])
        self.clients = clients
        self.my_sid = d.get('you') or self.my_sid
        total = d.get('total', len(clients))
        # the server tells us its limit so the client shows the same number
        mx = d.get('max')
        if mx:
            try:
                self.server_max = int(mx)
            except Exception:
                pass
        self.update_client_count(total)

        # keep the stored 'Server' contact in sync, but do NOT show it until the
        # server actually sends us something (see _reveal_server_peer)
        srv = self._ensure_server_peer()
        if srv is not None and not srv.get('lastMsg'):
            srv['hidden'] = True

        # refresh the live sid / online status of contacts in place (no rebuild)
        by_name = {}
        for c in clients:
            if c.get('sid') != self.my_sid:
                by_name[c.get('username')] = c
        for u in getattr(self, '_peers', []):
            if u.get('is_server'):
                continue          # never mark the server as offline
            c = by_name.get(u.get('name'))
            if c:
                new_sid = c.get('sid')
                newpic = c.get('avatar') or ''
                if (u.get('sid') != new_sid or u.get('status') != 'active'
                        or u.get('pic', '') != newpic):
                    u['sid'] = new_sid
                    u['status'] = 'active'
                    u['pic'] = newpic
                    self._update_row_inplace(u)
                    if self.current_chat_name == u.get('name'):
                        self.current_status = 'active'
                        self._apply_header_status('active')
            elif u.get('status') == 'active':
                u['status'] = 'offline'
                self._update_row_inplace(u)
                if self.current_chat_name == u.get('name'):
                    self.current_status = 'offline'
                    self._apply_header_status('offline')
        self._client_total = total
        # a restored chat may only become reachable once the live list arrives
        self._try_open_pending_chat()

    def _poll_clients(self):
        if sio.connected:
            sio.emit('get_connected_clients')
        self.root.after(5000, self._poll_clients)

    def _peer_candidates(self):
        """Other connected clients (everyone except me)."""
        me = self.my_sid
        return [c for c in getattr(self, 'clients', []) if c.get('sid') != me]

    def _resolve_ip(self, ip):
        """Find the connected client that owns the given IPv4 address."""
        for c in self._peer_candidates():
            if (c.get('ip') or '').strip() == ip:
                return c
        return None

    # ============================================================
    # BLOCK LIST  (persisted on the server in the `blocked` table)
    # ============================================================
    def _on_blocked_list(self, d):
        """Server sent the authoritative block list - mirror it locally."""
        items = (d or {}).get('blocked') or []
        self.blocked_meta = [{'peer': b.get('peer') or '',
                              'blocked_at': b.get('blocked_at') or ''}
                             for b in items if b.get('peer')]
        self.blocked = {b['peer'] for b in self.blocked_meta}
        self.refresh_middle_list()
        if getattr(self, 'current_view', 'chats') == 'blocked':
            self.show_blocked_inline()

    def _on_group_deleted(self, d):
        """The admin deleted a group I am in -> drop it everywhere."""
        gid = (d or {}).get('gid')
        if not gid:
            return
        self._remove_group_local(gid)
        if (d or {}).get('by') and d.get('by') != self.my_username:
            self.notify("Group deleted",
                        "\u201c%s\u201d was deleted by %s"
                        % (d.get('name') or 'A group', d.get('by')),
                        kind='info')
        else:
            self.show_toast("Group deleted")

    def _on_group_updated(self, g):
        """The admin added / removed somebody - refresh our copy."""
        self._add_group(g)

    def _on_group_removed(self, d):
        """I was removed from a group -> drop it from my chat list."""
        gid = d.get('gid')
        member = d.get('member')
        if member and member != self.my_username:
            return
        try:
            self._peers = [p for p in getattr(self, '_peers', [])
                           if p.get('gid') != gid]
        except Exception:
            pass
        self.refresh_middle_list()
        self._save_ui_state()
        self.notify("Group", "You were removed from %s"
                    % (d.get('name') or 'the group'), kind='info')

    def _on_group_error(self, d):
        self.notify("Group", d.get('message') or "Group action failed",
                    kind='info')

    def _on_history(self, d):
        """Full history for the open chat -> keep a local copy for in-chat search.

        Merge rather than replace: a message we just sent may not be inside the
        snapshot the server took (race), so keep local entries it doesn't have.
        """
        hist = list(d.get('messages', []))
        known = {m.get('mid') for m in hist if m.get('mid')}
        for m in getattr(self, '_current_msgs', []):
            if m.get('mid') and m.get('mid') not in known:
                hist.append(m)
        self._current_msgs = hist
        self.render_msgs({'messages': self._current_msgs})

    def _on_msg_reacted(self, d):
        rx = d.get('reactions') or {}
        by = d.get('by') or ''
        try:
            self._apply_reactions(d.get('mid'), rx)
        except Exception:
            pass
        # surface the incoming reaction as a notification (like the real app)
        if by and by != self.my_username and rx:
            emoji = ''
            for e, users in rx.items():
                if by in (users or []):
                    emoji = e
                    break
            if emoji:
                self.notify(f"{by} reacted {emoji}", "", kind='message')

    def _on_msg_starred(self, d):
        mid = d.get('mid')
        lst = d.get('starred_for') or []
        for m in getattr(self, '_current_msgs', []):
            if m.get('mid') == mid:
                m['starred_for'] = lst
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})

    def _on_msg_pinned(self, d):
        mid = d.get('mid')
        pin = d.get('pin')
        for m in getattr(self, '_current_msgs', []):
            if m.get('mid') == mid:
                m['pinned'] = pin
        if pin:
            self.pinned[self.current_chat_id] = mid
        elif self.pinned.get(self.current_chat_id) == mid:
            self.pinned.pop(self.current_chat_id, None)
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})

    def _on_msg_deleted(self, d):
        mid = d.get('mid')
        scope = d.get('scope')
        if scope == 'me' and d.get('me') != self.my_username:
            return
        if scope == 'all':
            for m in getattr(self, '_current_msgs', []):
                if m.get('mid') == mid:
                    m['deleted'] = True
                    m['text'] = ''
        else:
            self._current_msgs = [m for m in getattr(self, '_current_msgs', [])
                                  if m.get('mid') != mid]
        self.render_msgs({'messages': getattr(self, '_current_msgs', [])})

    # ---- real client-to-client messaging ----
    def _on_sent(self, d):
        """Server acknowledged our message."""
        mid = d.get('mid')
        final = d.get('status', 'sent')
        for m in getattr(self, '_current_msgs', []):
            if m.get('mid') == mid:
                # never downgrade a message that is already undelivered/blocked
                if m.get('status') not in ('undelivered', 'blocked', 'read'):
                    m['status'] = final
                final = m.get('status', final)
                break
        self._set_tick(mid, final)

    def _on_delivered(self, d):
        """The other client received the message -> double tick (grey)."""
        mid = d.get('mid')
        for m in getattr(self, '_current_msgs', []):
            if m.get('mid') == mid and m.get('status') not in ('read', 'blocked'):
                m['status'] = 'delivered'
                break
        self._set_tick(mid, 'delivered')

    def _on_undelivered(self, d):
        """Server could not hand the message over (peer offline or blocked).

        Marks the bubble so the sender sees it was not delivered: a single
        amber tick while the peer is offline (it will be stored and delivered
        when they return) and a red cross when the chat is blocked.
        """
        mid = d.get('mid')
        blocked = (d.get('reason') == 'blocked')
        status = 'blocked' if blocked else 'undelivered'
        for m in getattr(self, '_current_msgs', []):
            if m.get('mid') == mid:
                if m.get('status') != 'read':
                    m['status'] = status
                status = m.get('status', status)
                break
        self._set_tick(mid, status)

    def _on_read(self, d):
        """The other client opened the chat -> all our ticks turn green."""
        for m in getattr(self, '_current_msgs', []):
            if m.get('type') == 'sent' and m.get('status') != 'read':
                m['status'] = 'read'
                self._set_tick(m.get('mid'), 'read')

    def _on_incoming(self, d):
        """A message arrived from another client (1-to-1 or group)."""
        text = d.get('text', '')
        ts = d.get('time', '')
        gid = d.get('gid')
        is_file = (d.get('kind') or 'text') != 'text'
        # chat-list preview text for attachments ("Document: report.docx")
        last_preview = self._file_preview_label(d) if is_file else text

        # never accept a message from somebody I blocked
        if not gid:
            _sender = str(d.get('peer') or d.get('sender') or '')
            if _sender in getattr(self, 'blocked', set()):
                self._save_ui_state()
                return

        if gid:
            # ---- group message ----
            gname = d.get('peer') or 'Group'
            u = None
            for p in getattr(self, '_peers', []):
                if p.get('gid') == gid:
                    u = p
                    break
            if u is None:
                self._add_group({'id': gid, 'name': gname, 'members': []})
                for p in getattr(self, '_peers', []):
                    if p.get('gid') == gid:
                        u = p
                        break
            if u is not None:
                u['lastMsg'] = last_preview
                u['time'] = ts
            is_open = (u is not None and self.current_chat_gid == gid)
        else:
            peer = d.get('peer') or d.get('sender') or 'Unknown'
            # make sure the sender exists as a contact, so replying has a target
            u = None
            for p in getattr(self, '_peers', []):
                if p.get('name') == peer:
                    u = p
                    break
            if u is None and peer == 'Server':
                u = self._reveal_server_peer()
            elif u is not None and u.get('is_server'):
                u['hidden'] = False
            if u is None:
                self._add_peer(d.get('from_ip') or '?',
                               {'username': peer, 'sid': d.get('from_sid'),
                                'avatar': d.get('from_avatar', '')}, silent=True)
                for p in getattr(self, '_peers', []):
                    if p.get('name') == peer:
                        u = p
                        break
            if u is not None:
                u['lastMsg'] = last_preview
                u['time'] = ts
                u['sid'] = d.get('from_sid') or u.get('sid')
                if d.get('from_avatar'):
                    u['pic'] = d.get('from_avatar')
            is_open = (u is not None and self.current_chat_name == peer)

        if u is not None and is_open:
            self.add_msg({'mid': d.get('mid'), 'text': text, 'type': 'received',
                          'time': ts, 'sender': d.get('sender'),
                          'kind': d.get('kind', 'text'),
                          'file_name': d.get('file_name', ''),
                          'file_kind': d.get('file_kind', ''),
                          'file_mime': d.get('file_mime', ''),
                          'file_size': d.get('file_size', 0),
                          'file_dur': d.get('file_dur', 0),
                          'file_data': d.get('file_data', ''),
                          'day': d.get('day', ''),
                          'forwarded': d.get('forwarded', False),
                          'reply_sender': d.get('reply_sender', ''),
                          'reply_text': d.get('reply_text', '')})
            self._update_chat_preview(u['id'], last_preview, ts)
            # newest activity -> this chat moves to the top of the list
            self._touch_chat(u['id'])
            if not gid:
                # we are looking at this chat -> tell the sender it has been read
                sio.emit('mark_read', {'me': self.my_username, 'peer': u['name']})
        else:
            if u is not None:
                u['unread'] = u.get('unread', 0) + 1
                # newest message -> jump this chat to the top (pinned stay above)
                self._touch_chat(u['id'])

        # ---- modern left-side notification + ringtone (skipped when muted) ----
        sender = d.get('sender') or ''
        note = last_preview if is_file else text
        muted = (u is not None and u.get('id') in getattr(self, 'muted_chats', set()))
        if not muted:
            if gid:
                self.notify(gname, f"{sender}: {note}" if sender else note, kind='message')
            else:
                self.notify(peer, note, kind='message')
            if self.ringtone.path:
                self.ringtone.play()
            else:
                try:
                    self.root.bell()
                except Exception:
                    pass
        # keep the stored session fresh (new contact / preview / unread count)
        self._save_ui_state()

    # ============================================================
    # ACTIONS
    # ============================================================
    def _local_ipv4(self):
        """Best-effort detection of this machine's LAN IPv4 address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "unavailable"

    @staticmethod
    def _server_available(ip, port=5000, timeout=1.2):
        """Quick TCP probe to see whether a chat server is reachable at ip:port."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            return s.connect_ex((ip, port)) == 0
        except Exception:
            return False
        finally:
            try:
                s.close()
            except Exception:
                pass

    # ============================================================
    # GROUPS
    # ============================================================
    def _on_group_created(self, g):
        self._add_group(g)
        members = g.get('members') or []
        creator = g.get('creator') or ''
        creator_ip = g.get('creator_ip') or ''
        who = ("Created by %s%s" % (creator, (" (%s)" % creator_ip) if creator_ip else "")) \
            if creator else "%d members" % len(members)
        self.notify("Group created",
                    f"{g.get('name', 'Group')}  \u2022  {who}", kind='group')

    def _on_chats_cleared(self, d):
        if (d or {}).get('me') and d.get('me') != self.my_username:
            return
        if getattr(self, '_clear_pending', False):
            return
        self._wipe_chats()
        self.show_toast("All chats deleted")

    def _on_chat_cleared(self, d):
        """Server confirmed the clear - make sure the open view matches."""
        peer = (d or {}).get('peer') or ''
        gid = (d or {}).get('group') or ''
        is_current = (self.current_chat_id is not None and
                      ((gid and gid == self.current_chat_gid) or
                       (peer and peer == self.current_chat_name)))
        if is_current:
            self._current_msgs = []
            try:
                self.render_msgs({'messages': []})
            except Exception:
                pass
