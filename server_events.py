# server_events.py — every Socket.IO event handler (@socketio.on) plus
# the small helpers they share.
from server_core import *




# ===== SOCKET EVENTS =====
@socketio.on('connect')
def handle_connect():
    if len(connected_clients) >= max_clients():
        emit('server_full', {'message': 'Server is full. Max %d clients allowed.'
                             % max_clients()})
        return False
    print(f"Client connected: {request.sid}")
    emit('connected', {'sid': request.sid, 'max_clients': max_clients()})


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in connected_clients:
        username = connected_clients[sid]['username']
        print(f"Client disconnected: {username}")
        del connected_clients[sid]
        _end_calls_for_sid(sid, username)
        record_activity('leave', username, f"{username} disconnected",
                        "transport closed")
        emit('user_offline', {'username': username}, broadcast=True)
        emit('clients_changed', {'total': len(connected_clients)}, broadcast=True)


@socketio.on('leave')
def handle_leave(data=None):
    """Clean, immediate removal when a client closes the app."""
    sid = request.sid
    if sid in connected_clients:
        username = connected_clients[sid]['username']
        del connected_clients[sid]
        _end_calls_for_sid(sid, username)
        print(f"Client left: {username}")
        record_activity('leave', username, f"{username} left the chat",
                        "client closed")
        emit('user_offline', {'username': username}, broadcast=True)
        emit('clients_changed', {'total': len(connected_clients)}, broadcast=True)


@socketio.on('join')
def handle_join(data):
    sid = request.sid
    if len(connected_clients) >= max_clients() and sid not in connected_clients:
        emit('server_full', {'message': 'Server is full.'})
        return
    ip = request.remote_addr or ''
    typed = (data.get('username') or '').strip() or f'User_{sid[:4]}'
    stored = db_get_user(ip, typed)
    # Same user (name) from the same IP  ->  bring the whole session back.
    returning = stored is not None
    username = typed
    # Same device reconnecting (same name + same IP): restore its session instead
    # of creating a duplicate or blocking.  Evict the stale sid so there is only
    # one live session for this (name, IP).
    for s, c in list(connected_clients.items()):
        if s != sid and c.get('username') == username and c.get('ip') == ip:
            _end_calls_for_sid(s, username)
            connected_clients.pop(s, None)
            try:
                socketio.disconnect(s)
            except Exception:
                pass
            print(f"Reconnect: restored session for {username}@{ip} "
                  f"(evicted stale sid {s})")
            break
    avatar = data.get('avatar') or (stored or {}).get('avatar', '') or ''
    color = (stored or {}).get('color', '#25d366')
    connected_clients[sid] = {
        'username': username,
        'sid': sid,
        'ip': ip,
        'avatar': avatar,
        'color': color,
        'connected_at': datetime.now().strftime("%H:%M:%S")
    }
    if username not in user_settings:
        user_settings[username] = {
            'theme': 'dark',
            'notification_volume': 100,
            'system_volume': 100,
            'ringtone': 'Classic',
            'ringtone_path': '',
            'call_ringtone': 'Ring Classic',
            'call_ringtone_path': '',
            'call_volume': 100,
            'profile_color': color,
            'avatar': avatar,
        }
    contacts = db_get_contacts(username)
    # ---- hand this client its previous screen back FIRST ----
    # restore_state goes out before any disk write below, so the returning
    # user's name / avatar / contacts / last open chat come back immediately
    # even when 20 clients hit "Connect" at the same instant.
    emit('restore_state', {
        'ip': ip,
        'username': username,
        'returning': returning,
        'avatar': avatar,
        'color': color,
        'settings': user_settings.get(username, {}),
        'view': (stored or {}).get('last_view', 'chats'),
        'chat': (stored or {}).get('last_chat', ''),
        'contacts': contacts,
        'calls': call_history.get(username) or db_get_calls(username),
    })
    # server-wide limits + the live client list (needed by "Add by IP")
    emit('server_config', {'max_clients': max_clients(), 'port': PORT,
                           'server_name': 'Server'})
    emit('user_list', {
        'users': list(connected_clients.values()),
        'total_clients': len(connected_clients)
    })
    emit('get_settings', {'settings': user_settings[username]})
    emit('user_online', {'username': username, 'sid': sid, 'total': len(connected_clients)}, broadcast=True)
    print(f"[restore] {username} @ {ip} -> view={((stored or {}).get('last_view', 'chats'))!r} "
          f"chat={((stored or {}).get('last_chat', ''))!r} "
          f"contacts={len(contacts)} returning={returning}")
    # ---- persistence + bookkeeping happen after the client is restored ----
    db_save_user(ip, username, avatar=avatar, color=color)
    record_activity('join', username,
                    f"{username} connected from {ip}",
                    f"{'session restored' if returning else 'new session'} | "
                    f"clients: {len(connected_clients)}")
    # deliver any messages that were waiting for this client while it was offline
    for key, msgs in conversations.items():
        if username not in key:
            continue
        other = key[0] if key[1] == username else key[1]
        for m in msgs:
            if m.get('peer') == username and m.get('status') == 'sent':
                m['status'] = 'delivered'
                db_set_status(m.get('mid'), 'delivered')
                for s2, c2 in connected_clients.items():
                    if c2['username'] == other:
                        socketio.emit('message_delivered', {'mid': m.get('mid'), 'peer': username}, to=s2)
    # re-send any groups this client belongs to
    my_groups = [g for g in groups.values() if username in g['members']]
    if my_groups:
        emit('groups_list', {'groups': my_groups})
    # restore the persisted block list
    emit('blocked_list', {'blocked': db_get_blocked(username)})
    # tell everyone the client list changed so their middle panel refreshes
    emit('clients_changed', {'total': len(connected_clients)}, broadcast=True)
    print(f"User joined: {username} | Total: {len(connected_clients)}")


@socketio.on('get_messages')
def handle_get_messages(data):
    """Return the conversation history (1-to-1 or group)."""
    me = data.get('me') or connected_clients.get(request.sid, {}).get('username', '')
    gid = data.get('group')
    if gid:
        hist = []
        for m in group_messages.get(gid, []):
            if me in _deleted_for(m):
                continue
            item = dict(m)
            item['type'] = 'sent' if m.get('sender') == me else 'received'
            hist.append(item)
        emit('messages_history', {'gid': gid,
                                  'peer': groups.get(gid, {}).get('name', 'Group'),
                                  'messages': hist})
        return
    peer = str(data.get('peer') or data.get('room_id') or '')
    history = []
    for m in conversations.get(conv_key(me, peer), []):
        if me in _deleted_for(m):
            continue
        item = dict(m)
        item['type'] = 'sent' if m.get('sender') == me else 'received'
        history.append(item)
    emit('messages_history', {'peer': peer, 'messages': history})


@socketio.on('create_group')
def handle_create_group(data):
    """Create a group with the selected clients and tell its members."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('creator', '')
    my_ip = connected_clients.get(request.sid, {}).get('ip') or request.remote_addr or ''
    name = str(data.get('name') or 'New Group').strip() or 'New Group'
    members = [m for m in (data.get('members') or []) if m and m != me]
    gid = uuid.uuid4().hex[:8]
    group = {'id': gid, 'name': name, 'members': [me] + members,
             'creator': me, 'creator_ip': my_ip, 'avatar': ''}
    groups[gid] = group
    group_messages.setdefault(gid, [])
    db_add_group(group)
    # the group becomes a contact (a chat) for every member
    for member in group['members']:
        db_upsert_contact(member, name, 'group', 'Group created')
    for s, c in connected_clients.items():
        if c['username'] in group['members']:
            socketio.emit('group_created', group, to=s)
    record_activity('group', me,
                    f"{me} created group \u201c{name}\u201d",
                    f"{len(group['members'])} members: " + ", ".join(group['members']))
    print(f"Group created: {name} ({gid}) creator={me}@{my_ip} "
          f"members={group['members']}")


@socketio.on('group_add_member')
def handle_group_add_member(data):
    """Only the group creator (admin) can add another member later."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('from', '')
    gid = str(data.get('gid') or '')
    member = str(data.get('member') or '').strip()
    g = groups.get(gid)
    if not g or not member:
        return
    if g.get('creator') != me:
        emit('group_error', {'gid': gid, 'message': 'Only the group admin can add members'})
        return
    if member not in g['members']:
        g['members'].append(member)
        db_add_group_member(gid, member)
    db_upsert_contact(member, g['name'], 'group', 'Added to group')
    # keep every member's member-list in sync
    for s, c in connected_clients.items():
        if c['username'] in g['members']:
            socketio.emit('group_updated', g, to=s)
    record_activity('group', me, f"{me} added {member} to \u201c{g['name']}\u201d")
    print(f"Group add: {member} -> {g['name']} ({gid}) by {me}")


@socketio.on('group_remove_member')
def handle_group_remove_member(data):
    """Only the group creator (admin) can remove a member."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('from', '')
    gid = str(data.get('gid') or '')
    member = str(data.get('member') or '').strip()
    g = groups.get(gid)
    if not g or not member:
        return
    if g.get('creator') != me:
        emit('group_error', {'gid': gid, 'message': 'Only the group admin can remove members'})
        return
    if member == g.get('creator'):
        emit('group_error', {'gid': gid, 'message': 'The admin cannot be removed'})
        return
    if member in g['members']:
        g['members'].remove(member)
        db_remove_group_member(gid, member)
    db_exec("DELETE FROM contacts WHERE owner=? AND peer=?", (member, g['name']))
    # remaining members get the new member list ...
    for s, c in list(connected_clients.items()):
        if c['username'] in g['members']:
            socketio.emit('group_updated', g, to=s)
    # ... and the removed member is told to drop the group
    gone = _sid_of(member)
    if gone:
        socketio.emit('group_removed', {'gid': gid, 'name': g['name'],
                                        'member': member}, to=gone)
    record_activity('group', me, f"{me} removed {member} from \u201c{g['name']}\u201d")
    print(f"Group remove: {member} <- {g['name']} ({gid}) by {me}")


@socketio.on('group_rename')
def handle_group_rename(data):
    """Admin changes the group name -> every member's list updates."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('from', '')
    gid = str(data.get('gid') or '')
    new_name = str(data.get('name') or '').strip()
    g = groups.get(gid)
    if not g or not new_name:
        return
    if g.get('creator') != me:
        emit('group_error', {'gid': gid, 'message': 'Only the group admin can rename the group'})
        return
    old_name = g.get('name') or ''
    g['name'] = new_name
    db_set_group_name(gid, new_name)
    db_rename_group_contacts(old_name, new_name)
    for s, c in connected_clients.items():
        if c['username'] in g['members']:
            socketio.emit('group_updated', g, to=s)
    record_activity('group', me, f"{me} renamed \u201c{old_name}\u201d \u2192 \u201c{new_name}\u201d")
    print(f"Group rename: {old_name} -> {new_name} ({gid}) by {me}")


@socketio.on('group_set_pic')
def handle_group_set_pic(data):
    """Admin changes the group profile photo -> push it to every member."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('from', '')
    gid = str(data.get('gid') or '')
    pic = data.get('pic') or ''
    g = groups.get(gid)
    if not g:
        return
    if g.get('creator') != me:
        emit('group_error', {'gid': gid, 'message': 'Only the group admin can change the group photo'})
        return
    g['avatar'] = pic
    db_set_group_avatar(gid, pic)
    for member in g['members']:
        db_exec("UPDATE contacts SET peer_pic=? WHERE owner=? AND peer_type='group' AND peer=?",
                (pic, member, g['name']))
    for s, c in connected_clients.items():
        if c['username'] in g['members']:
            socketio.emit('group_updated', g, to=s)
    record_activity('group', me, f"{me} changed the photo of \u201c{g['name']}\u201d")
    print(f"Group photo set: {g['name']} ({gid}) by {me}")


@socketio.on('group_delete')
def handle_group_delete(data):
    """Admin deletes the group -> it disappears for every member."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('from', '')
    gid = str(data.get('gid') or '')
    g = groups.get(gid)
    if not g:
        return
    if g.get('creator') != me:
        emit('group_error', {'gid': gid, 'message': 'Only the group admin can delete the group'})
        return
    name = g.get('name') or ''
    members = list(g.get('members') or [])
    # wipe it from memory + the database
    groups.pop(gid, None)
    group_messages.pop(gid, None)
    db_delete_group(gid, name)
    for member in members:
        s = _sid_of(member)
        if s:
            socketio.emit('group_deleted', {'gid': gid, 'name': name, 'by': me}, to=s)
    record_activity('group', me, f"{me} deleted group \u201c{name}\u201d")
    print(f"Group deleted: {name} ({gid}) by {me}")


@socketio.on('send_message')
def handle_send_message(data):
    """Route a chat message from this client to another client or a group."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('sender', 'User')
    text = data.get('text', '')
    time_str = datetime.now().strftime("%H:%M")
    mid = str(data.get('mid') or uuid.uuid4().hex[:12])

    # ---- group message ----
    to_group = data.get('to_group')
    if to_group and to_group in groups:
        g = groups[to_group]
        msg = {"mid": mid, "text": text, "sender": me, "time": time_str,
               "status": "delivered", "peer": g['name'], "gid": to_group}
        msg.update(file_fields(data))
        msg.update(msg_meta_fields(data))
        pv = preview_text(text, data)
        group_messages.setdefault(to_group, []).append(msg)
        db_add_message(msg)
        # members who blocked me simply never receive it
        blocked_me = {m for m in g['members'] if db_is_blocked(m, me)}
        for member in g['members']:
            if member in blocked_me and member != me:
                continue
            db_upsert_contact(member, g['name'], 'group', pv,
                              unread_inc=(member != me))
        for s, c in connected_clients.items():
            if c['username'] in g['members'] and s != request.sid \
                    and c['username'] not in blocked_me:
                inc = dict(msg)
                inc['type'] = 'received'
                socketio.emit('new_message', inc, to=s)
        ack = dict(msg)
        ack['type'] = 'sent'
        emit('message_sent', ack)
        record_activity('message', me,
                        f"{me} \u2192 {g['name']} (group)",
                        pv[:120])
        print(f"Group msg {me} -> {g['name']}: {text[:40]}")
        return

    to_name = str(data.get('to_name') or data.get('room_id') or '')
    to_sid = data.get('to_sid')

    # status starts as 'sent' (single tick). It becomes 'delivered' when the
    # other client is online, and 'read' once they open the chat.
    msg = {"mid": mid, "text": text, "sender": me, "time": time_str,
           "status": "sent", "peer": to_name}
    msg.update(file_fields(data))
    msg.update(msg_meta_fields(data))
    pv = preview_text(text, data)

    # a blocked pair never exchanges messages (either direction)
    if to_name and (db_is_blocked(to_name, me) or db_is_blocked(me, to_name)):
        ack = dict(msg)
        ack['type'] = 'sent'
        emit('message_sent', ack)
        emit('message_undelivered', {'mid': mid, 'peer': to_name,
                                     'reason': 'blocked'})
        record_activity('message', me, f"{me} \u2192 {to_name}", 'blocked')
        print(f"Message BLOCKED {me} -> {to_name}")
        return

    conversations.setdefault(conv_key(me, to_name), []).append(msg)
    db_add_message(msg)
    db_upsert_contact(me, to_name, 'single', pv, color='#2c2c2c')

    # resolve the receiver's live sid (fall back to matching the profile name)
    target = to_sid if to_sid in connected_clients else None
    if target is None:
        for s, c in connected_clients.items():
            if c['username'] == to_name and s != request.sid:
                target = s
                break

    if target:
        msg['status'] = 'delivered'
        db_set_status(mid, 'delivered')
        db_upsert_contact(to_name, me, 'single', pv, unread_inc=True,
                          color='#2c2c2c')
        incoming = dict(msg)
        incoming['type'] = 'received'
        incoming['peer'] = me
        incoming['from_sid'] = request.sid
        incoming['from_ip'] = connected_clients.get(request.sid, {}).get('ip', '')
        incoming['from_avatar'] = connected_clients.get(request.sid, {}).get('avatar', '')
        socketio.emit('new_message', incoming, to=target)
        # tell the sender the message reached the other client -> double tick
        emit('message_delivered', {'mid': mid, 'peer': to_name})
        socketio.emit('clients_changed', {'total': len(connected_clients)}, to=target)
    else:
        # other client is offline -> keep the single tick, flag it as pending
        emit('message_undelivered', {'mid': mid, 'peer': to_name,
                                     'reason': 'offline'})

    ack = dict(msg)
    ack['type'] = 'sent'
    emit('message_sent', ack)
    record_activity('message', me,
                    f"{me} \u2192 {to_name}",
                    f"[{msg['status']}] {pv[:120]}")
    print(f"Message {me} -> {to_name} [{msg['status']}]: {text[:40]}")


@socketio.on('mark_read')
def handle_mark_read(data):
    """The other client opened/read our chat -> turn our ticks green."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me')
    peer = str(data.get('peer') or '')
    if not me or not peer:
        return
    for m in conversations.get(conv_key(me, peer), []):
        if m.get('peer') == me and m.get('status') != 'read':
            m['status'] = 'read'
            db_set_status(m.get('mid'), 'read')
    db_clear_unread(me, peer)
    record_activity('read', me, f"{me} read the chat with {peer}", "")
    for s, c in connected_clients.items():
        if c['username'] == peer and s != request.sid:
            socketio.emit('messages_read', {'peer': me}, to=s)


@socketio.on('pin_message')
def handle_pin_message(data):
    """Pin / unpin a message for everyone in the conversation."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me')
    mid = str(data.get('mid') or '')
    pin = 1 if data.get('pin') else 0
    gid = data.get('group') or ''
    peer = str(data.get('peer') or '')
    if not mid:
        return
    db_exec("UPDATE messages SET pinned=? WHERE mid=?", (pin, mid))
    targets = []
    if gid and gid in groups:
        for m in group_messages.get(gid, []):
            if m.get('mid') == mid:
                m['pinned'] = bool(pin)
        targets = [s for s, c in connected_clients.items()
                   if c['username'] in groups[gid]['members']]
        evt = {'mid': mid, 'pin': bool(pin), 'gid': gid}
    else:
        for m in conversations.get(conv_key(me, peer), []):
            if m.get('mid') == mid:
                m['pinned'] = bool(pin)
        targets = [s for s, c in connected_clients.items()
                   if c['username'] in (me, peer)]
        evt = {'mid': mid, 'pin': bool(pin), 'peer': peer}
    for s in targets:
        socketio.emit('message_pinned', evt, to=s)
    record_activity('pin', me or '', f"{me} {'pinned' if pin else 'unpinned'} a message", mid)


@socketio.on('delete_message')
def handle_delete_message(data):
    """Delete a message for me (per-user) or for everyone."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me')
    mid = str(data.get('mid') or '')
    scope = data.get('scope') or 'me'
    gid = data.get('group') or ''
    peer = str(data.get('peer') or '')
    if not mid:
        return
    if scope == 'all':
        db_exec("UPDATE messages SET deleted=1, text='', file_data='', file_name='' "
                "WHERE mid=?", (mid,))
        if gid and gid in groups:
            for m in group_messages.get(gid, []):
                if m.get('mid') == mid:
                    m['deleted'] = True
                    m['text'] = ''
                    m['file_data'] = ''
            targets = [s for s, c in connected_clients.items()
                       if c['username'] in groups[gid]['members']]
            evt = {'mid': mid, 'scope': 'all', 'gid': gid}
        else:
            for m in conversations.get(conv_key(me, peer), []):
                if m.get('mid') == mid:
                    m['deleted'] = True
                    m['text'] = ''
                    m['file_data'] = ''
            targets = [s for s, c in connected_clients.items()
                       if c['username'] in (me, peer)]
            evt = {'mid': mid, 'scope': 'all', 'peer': peer}
        for s in targets:
            socketio.emit('message_deleted', evt, to=s)
    else:
        rows = db_query("SELECT deleted_for FROM messages WHERE mid=?", (mid,))
        cur = []
        if rows:
            try:
                cur = json.loads(rows[0].get('deleted_for') or '[]')
            except Exception:
                cur = []
        if me and me not in cur:
            cur.append(me)
        db_exec("UPDATE messages SET deleted_for=? WHERE mid=?", (json.dumps(cur), mid))
        # keep the in-memory copies in sync
        for m in (group_messages.get(gid, []) if gid else
                  conversations.get(conv_key(me, peer), [])):
            if m.get('mid') == mid:
                m['deleted_for'] = cur
        # only this user's own sessions need to drop it
        for s, c in connected_clients.items():
            if c['username'] == me:
                socketio.emit('message_deleted',
                              {'mid': mid, 'scope': 'me', 'me': me}, to=s)
    record_activity('delete', me or '',
                    f"{me} deleted a message ({scope})", mid)


def _msg_targets(me, peer, gid):
    """Everyone that should hear about a change to this conversation."""
    if gid and gid in groups:
        return [s for s, c in connected_clients.items()
                if c['username'] in groups[gid]['members']]
    return [s for s, c in connected_clients.items() if c['username'] in (me, peer)]


def _msg_containers(me, peer, gid):
    """The in-memory message lists holding this conversation."""
    if gid and gid in groups:
        return group_messages.get(gid, [])
    return conversations.get(conv_key(me, peer), [])


@socketio.on('react_message')
def handle_react_message(data):
    """Add / change / remove an emoji reaction on a message (for everyone)."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me')
    mid = str(data.get('mid') or '')
    emoji = str(data.get('emoji') or '')
    gid = data.get('group') or ''
    peer = str(data.get('peer') or '')
    if not mid:
        return
    rows = db_query("SELECT reactions FROM messages WHERE mid=?", (mid,))
    rx = {}
    if rows:
        rx = _json_field(rows[0], 'reactions', {})
        if not isinstance(rx, dict):
            rx = {}
    # one reaction per user: drop the user from every other emoji first
    for k in list(rx.keys()):
        rx[k] = [u for u in rx.get(k, []) if u != me]
        if not rx[k]:
            rx.pop(k, None)
    if emoji and me not in rx.get(emoji, []):
        rx.setdefault(emoji, []).append(me)
    db_exec("UPDATE messages SET reactions=? WHERE mid=?", (json.dumps(rx), mid))
    for m in _msg_containers(me, peer, gid):
        if m.get('mid') == mid:
            m['reactions'] = rx
    evt = {'mid': mid, 'reactions': rx, 'by': me}
    if gid:
        evt['gid'] = gid
    else:
        evt['peer'] = peer
    for s in _msg_targets(me, peer, gid):
        socketio.emit('message_reacted', evt, to=s)
    record_activity('react', me or '',
                    f"{me} {'removed a reaction' if not emoji else 'reacted ' + emoji}", mid)


@socketio.on('star_message')
def handle_star_message(data):
    """Star / unstar a message for the current user only."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me')
    mid = str(data.get('mid') or '')
    gid = data.get('group') or ''
    peer = str(data.get('peer') or '')
    if not mid or not me:
        return
    star = bool(data.get('star'))
    rows = db_query("SELECT starred_for FROM messages WHERE mid=?", (mid,))
    cur = _json_field(rows[0], 'starred_for', []) if rows else []
    if not isinstance(cur, list):
        cur = []
    if star and me not in cur:
        cur.append(me)
    elif not star:
        cur = [u for u in cur if u != me]
    db_exec("UPDATE messages SET starred_for=? WHERE mid=?", (json.dumps(cur), mid))
    for m in _msg_containers(me, peer, gid):
        if m.get('mid') == mid:
            m['starred_for'] = cur
    evt = {'mid': mid, 'starred_for': cur, 'star': star}
    if gid:
        evt['gid'] = gid
    else:
        evt['peer'] = peer
    for s, c in connected_clients.items():
        if c['username'] == me:          # star is private to this user
            socketio.emit('message_starred', evt, to=s)
    record_activity('star', me, f"{me} {'starred' if star else 'unstarred'} a message", mid)


@socketio.on('record_call')
def handle_record_call(data):
    """Persist one call (outcome + duration) into the database."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me')
    if not me:
        return
    now = datetime.now()
    entry = {
        'owner': me,
        'peer': str(data.get('name') or data.get('peer') or ''),
        'peer_avatar': str(data.get('avatar') or ''),
        'peer_color': str(data.get('color') or '#2c2c2c'),
        'kind': 'video' if data.get('kind') == 'video' else 'voice',
        'outcome': str(data.get('outcome') or ''),
        'dur': int(data.get('dur') or 0),
        'time': str(data.get('time') or now.strftime("%H:%M")),
        'day': str(data.get('day') or now.strftime("%Y-%m-%d")),
        'created': now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    db_add_call(entry)
    lst = call_history.setdefault(me, [])
    lst.insert(0, {k: v for k, v in entry.items() if k != 'owner'})
    del lst[300:]
    payload = {k: v for k, v in entry.items() if k != 'owner'}
    # sync the Calls tab across every session of this user (e.g. two devices)
    for s, c in connected_clients.items():
        if c.get('username') == me:
            socketio.emit('call_recorded', payload, to=s)
    record_activity('call', me,
                    "%s %s call with %s" % (me, entry['kind'], entry['peer']),
                    entry['outcome'])
    print(f"Call {entry['kind']} {me} <-> {entry['peer']} [{entry['outcome']}]")


@socketio.on('clear_all_chats')
def handle_clear_all_chats(data):
    """'Delete all chats': forget every 1-to-1 contact + hide its history.

    The history is hidden for THIS user only (`deleted_for`), so the other
    profile keeps its own copy. Group chats are left untouched because they
    belong to every member.
    """
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me')
    if not me:
        return
    peers = [r.get('peer') for r in db_get_contacts(me) if r.get('peer')]
    db_exec("DELETE FROM contacts WHERE owner=?", (me,))
    for p in peers:
        # `deleted_for` hides the history for me only - the other profile keeps
        # its own copy, so the shared in-memory conversation is NEVER dropped
        for m in conversations.get(conv_key(me, p), []):
            cur = m.get('deleted_for')
            if not isinstance(cur, list):
                cur = []
            if me not in cur:
                cur.append(me)
            m['deleted_for'] = cur
            db_exec("UPDATE messages SET deleted_for=? WHERE mid=?",
                    (json.dumps(cur), m.get('mid')))
        # rows that were never loaded into memory are covered as well
        for r in db_query("""SELECT mid, deleted_for FROM messages
                             WHERE (sender=? AND peer=?) OR (sender=? AND peer=?)""",
                          (me, p, p, me)):
            cur = _deleted_for(r)
            if me not in cur:
                cur.append(me)
                db_exec("UPDATE messages SET deleted_for=? WHERE mid=?",
                        (json.dumps(cur), r.get('mid')))
    emit('chats_cleared', {'me': me, 'count': len(peers)})
    record_activity('clear', me, f"{me} deleted all chats ({len(peers)})")
    print(f"Clear all chats: {me} ({len(peers)} contacts)")


@socketio.on('clear_chat')
def handle_clear_chat(data):
    """'Delete chat' (inside a conversation): hide just this history for me."""
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me')
    if not me:
        return
    gid = str(data.get('group') or '')
    peer = str(data.get('peer') or '')
    if gid:
        msgs = group_messages.get(gid, [])
    elif peer:
        msgs = conversations.get(conv_key(me, peer), [])
    else:
        return
    for m in msgs:
        cur = m.get('deleted_for')
        if not isinstance(cur, list):
            cur = []
        if me not in cur:
            cur.append(me)
        m['deleted_for'] = cur
        db_exec("UPDATE messages SET deleted_for=? WHERE mid=?",
                (json.dumps(cur), m.get('mid')))
    emit('chat_cleared', {'peer': peer, 'group': gid})
    record_activity('clear', me, "deleted the chat with \u201c%s\u201d"
                    % (gid or peer or '?'))
    print(f"Clear chat: {me} / {gid or peer}")


@socketio.on('save_ui_state')
def handle_save_ui_state(data):
    """Remember where the client was (view + open chat) and its contact list."""
    sid = request.sid
    me = connected_clients.get(sid, {}).get('username')
    if not me:
        return
    ip = connected_clients.get(sid, {}).get('ip') or request.remote_addr or ''
    view = str(data.get('view') or 'chats')
    chat = str(data.get('chat') or '')
    db_save_user(ip, me, last_view=view, last_chat=chat)
    # ---- audit: which screen the user moved to / which chat they opened ----
    prev_ui = connected_clients.get(sid, {}).get('ui') or {'view': 'chats', 'chat': ''}
    connected_clients.setdefault(sid, {})['ui'] = {'view': view, 'chat': chat}
    if prev_ui.get('view') != view:
        record_activity('view', me, f"{me} switched to \u201c{view}\u201d",
                        f"screen: {prev_ui.get('view')} \u2192 {view}")
    elif chat and prev_ui.get('chat') != chat:
        record_activity('view', me, f"{me} opened the chat with \u201c{chat}\u201d",
                        "active conversation")
    contacts = data.get('contacts')
    if isinstance(contacts, list):
        for c in contacts:
            if isinstance(c, dict) and c.get('name'):
                db_add_contact(me, c)
        # drop contacts the client no longer has
        names = [c.get('name') for c in contacts if isinstance(c, dict) and c.get('name')]
        if names:
            for row in db_get_contacts(me):
                if row['peer'] not in names:
                    db_exec("DELETE FROM contacts WHERE owner=? AND peer=?",
                            (me, row['peer']))


@socketio.on('add_contact')
def handle_add_contact(data):
    """A client manually added somebody by IP -> remember the contact."""
    me = connected_clients.get(request.sid, {}).get('username')
    c = data.get('contact') if isinstance(data.get('contact'), dict) else data
    if me and isinstance(c, dict) and c.get('name'):
        db_add_contact(me, c)
        record_activity('contact', me,
                        f"{me} added \u201c{c['name']}\u201d "
                        f"({'group' if c.get('type') == 'group' else 'client'})",
                        f"type={c.get('type', 'single')}")


# ============================================================
#  BLOCK LIST  (persisted in the `blocked` table)
# ============================================================
@socketio.on('block_user')
def handle_block_user(data):
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me', '')
    peer = str(data.get('peer') or '').strip()
    if not me or not peer:
        return
    db_block(me, peer)
    emit('blocked_list', {'blocked': db_get_blocked(me)})
    record_activity('block', me, f"{me} blocked {peer}")
    print(f"Blocked: {me} -> {peer}")


@socketio.on('unblock_user')
def handle_unblock_user(data):
    me = connected_clients.get(request.sid, {}).get('username') or data.get('me', '')
    peer = str(data.get('peer') or '').strip()
    if not me or not peer:
        return
    db_unblock(me, peer)
    emit('blocked_list', {'blocked': db_get_blocked(me)})
    record_activity('block', me, f"{me} unblocked {peer}")
    print(f"Unblocked: {me} -> {peer}")


@socketio.on('get_blocked')
def handle_get_blocked(data=None):
    me = connected_clients.get(request.sid, {}).get('username') or \
        (data or {}).get('me', '')
    if not me:
        return
    emit('blocked_list', {'blocked': db_get_blocked(me)})


@socketio.on('pin_chat')
def handle_pin_chat(data):
    """Pin / unpin a chat so it stays on top (persisted per owner)."""
    me = connected_clients.get(request.sid, {}).get('username') or \
        (data or {}).get('me', '')
    peer = str((data or {}).get('peer') or '').strip()
    if me and peer:
        db_set_pinned(me, peer, bool((data or {}).get('pinned')),
                      (data or {}).get('pin_ts'))


@socketio.on('add_server')
def handle_add_server(data):
    server_name = data.get('server_name', 'New Server')
    server_id = str(uuid.uuid4())[:8]
    server_info = {
        "id": server_id,
        "name": server_name,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "added_by": data.get('added_by', 'Unknown')
    }
    servers.append(server_info)
    print(f"Server added: {server_info}")
    record_activity('server', server_info.get('added_by', 'Unknown'),
                    f"{server_info.get('added_by', 'Unknown')} added a server",
                    f"{server_name} ({server_id})")
    emit('server_added', {'success': True, 'server': server_info,
                          'message': 'Server added on server side'})
    emit('servers_list', {'servers': servers}, broadcast=True)


@socketio.on('get_servers')
def handle_get_servers():
    emit('servers_list', {'servers': servers})


@socketio.on('update_settings')
def handle_update_settings(data):
    username = data.get('username')
    prev = data.get('prev_username')
    settings = data.get('settings') if isinstance(data.get('settings'), dict) else {
        k: v for k, v in data.items() if k not in ('username', 'prev_username')
    }
    if not username:
        return
    sid = request.sid
    ip = connected_clients.get(sid, {}).get('ip') or request.remote_addr or ''
    if prev and prev != username:
        db_rename_user(ip, prev, username)
        _rename_in_memory(prev, username)
        if prev in user_settings:
            user_settings[username] = user_settings.pop(prev)
        record_activity('settings', username,
                        f"{prev} renamed to \u201c{username}\u201d",
                        "display name changed")
    old_settings = user_settings.get(username) or {}
    diff = _settings_diff(old_settings, settings)
    user_settings[username] = settings
    # persist the preferences (and the display name) for this (ip, name)
    db_save_user(ip, username, settings=settings,
                 color=settings.get('profile_color'),
                 avatar=settings.get('avatar'))
    if sid in connected_clients:
        connected_clients[sid]['username'] = username
    if diff:
        record_activity('settings', username,
                        f"{username} changed settings", diff)
    # private ack: only the client that changed its settings gets this back
    # (other clients must NOT be notified about someone else's settings).
    emit('settings_updated', {'username': username, 'settings': settings})
    print(f"Settings updated for {username}: {settings}")


_SETTING_LABELS = {
    'theme': 'Theme', 'ringtone': 'Ringtone', 'ringtone_path': 'Ringtone file',
    'notification_volume': 'Notification volume', 'system_volume': 'System volume',
    'call_ringtone': 'Call ringtone', 'call_ringtone_path': 'Call ringtone file',
    'call_volume': 'Call volume', 'profile_color': 'Avatar colour',
    'notifications': 'Notifications', 'call_sound': 'Sound',
}


def _settings_diff(old, new):
    """Human readable changelog: 'Theme: Dark -> Light; Ringtone: Chime -> Ping'."""
    out = []
    for k, v in (new or {}).items():
        if k in ('username', 'prev_username', 'avatar'):
            continue
        ov = (old or {}).get(k)
        if ov != v:
            if k.endswith('_path'):
                out.append(f"{_SETTING_LABELS.get(k, k)}: changed")
            else:
                out.append(f"{_SETTING_LABELS.get(k, k)}: {ov} \u2192 {v}")
    return "; ".join(out[:6])


def _rename_in_memory(old, new):
    """Keep the live caches consistent when a client renames itself."""
    for key in list(conversations.keys()):
        if old in key:
            msgs = conversations.pop(key)
            newkey = tuple(sorted([new if x == old else x for x in key]))
            conversations.setdefault(newkey, []).extend(msgs)
            for m in msgs:
                if m.get('sender') == old:
                    m['sender'] = new
                if m.get('peer') == old:
                    m['peer'] = new
    for g in groups.values():
        g['members'] = [new if m == old else m for m in g['members']]
    for s, c in connected_clients.items():
        if c.get('username') == old:
            c['username'] = new



@socketio.on('update_profile')
def handle_update_profile(data):
    """A client changed its profile photo -> tell everybody."""
    sid = request.sid
    username = data.get('username') or connected_clients.get(sid, {}).get('username')
    avatar = data.get('avatar', '')
    if sid in connected_clients:
        connected_clients[sid]['avatar'] = avatar
    if username:
        for s, c in connected_clients.items():
            if c['username'] == username:
                c['avatar'] = avatar
        ip = connected_clients.get(sid, {}).get('ip') or request.remote_addr or ''
        db_save_user(ip, username, avatar=avatar)
        # propagate the new picture into every stored contact row
        for row in db_query("SELECT owner, peer FROM contacts WHERE peer=?", (username,)):
            db_exec("UPDATE contacts SET peer_pic=? WHERE owner=? AND peer=?",
                    (avatar, row['owner'], row['peer']))
    emit('user_profile', {'username': username, 'avatar': avatar, 'sid': sid},
         broadcast=True)
    emit('clients_changed', {'total': len(connected_clients)}, broadcast=True)
    record_activity('profile', username,
                    f"{username} {'updated' if avatar else 'removed'} the profile photo",
                    "avatar changed")
    print(f"Profile photo updated for {username}")


@socketio.on('get_connected_clients')
def handle_get_connected_clients():
    emit('connected_clients_list', {
        'clients': list(connected_clients.values()),
        'total': len(connected_clients),
        'max': max_clients(),
        'you': request.sid
    })


# ============================================================
#  CALLS  -  signalling + media relay (voice / video)
# ============================================================
def _sid_of(username, exclude=None):
    """The live sid of a connected client by username (else None)."""
    for s, c in connected_clients.items():
        if c.get('username') == username and s != exclude:
            return s
    return None


def _participants(call):
    """Every sid taking part (the caller + everyone who accepted)."""
    parts = call.get('participants')
    if parts is None:
        parts = set()
        for s in (call.get('caller_sid'), call.get('callee_sid')):
            if s:
                parts.add(s)
        call['participants'] = parts
    return parts


def _others(call, sid=None):
    """Every sid in the call except `sid` (used for the media fan-out)."""
    return [s for s in _participants(call) if s and s != sid]


def _leave_call(call_id, call, sid, username, reason=''):
    """Drop one participant; end the call once it cannot carry on.

    A group call stays alive for the people left (they get 'call_peer_left');
    a 1:1 call ends the moment the other side goes away.
    """
    _participants(call).discard(sid)
    rest = _others(call)
    if len(rest) >= 2:
        for s in rest:
            socketio.emit('call_peer_left', {'call_id': call_id, 'by': username,
                                             'reason': reason,
                                             'count': len(rest)}, to=s)
        return
    active_calls.pop(call_id, None)
    for s in rest:
        socketio.emit('call_ended', {'call_id': call_id, 'by': username,
                                     'reason': reason}, to=s)


def _end_calls_for_sid(sid, username=''):
    """When a client drops, tell the rest of the call it lost a participant."""
    for cid in list(active_calls.keys()):
        call = active_calls.get(cid)
        if not call:
            continue
        if sid in _participants(call) or sid in (call.get('caller_sid'),
                                                 call.get('callee_sid')):
            _leave_call(cid, call, sid, username, 'disconnected')


@socketio.on('start_call')
def handle_start_call(data):
    me = connected_clients.get(request.sid, {}).get('username') or data.get('from', 'User')
    to = str(data.get('to') or '')
    kind = data.get('kind') or 'voice'
    call_id = str(data.get('call_id') or uuid.uuid4().hex[:10])
    gid = str(data.get('group') or '')
    my_pic = connected_clients.get(request.sid, {}).get('avatar', '')
    call = {'caller': me, 'callee': to, 'kind': kind, 'group': gid,
            'group_name': '', 'caller_sid': request.sid, 'callee_sid': None,
            'participants': {request.sid}}

    if gid:                                   # ---- group call ----
        g = groups.get(gid) or {}
        gname = g.get('name') or to or 'Group'
        call['group_name'] = gname
        # Whoever STARTS the call can hang it up for everyone; any other
        # member who presses End simply leaves and the call carries on for
        # the members that are still connected.
        call['initiator'] = request.sid
        targets = [s for s in (_sid_of(m, exclude=request.sid)
                               for m in (g.get('members') or [])) if s]
        active_calls[call_id] = call
        record_activity('call', me,
                        f"{me} started a {kind} group call in {gname}",
                        'ringing' if targets else 'nobody online')
        for s in targets:
            socketio.emit('incoming_call', {
                'call_id': call_id, 'from': me, 'from_sid': request.sid,
                'kind': kind, 'avatar': my_pic, 'group': gid,
                'group_name': gname, 'group_avatar': g.get('avatar', '')}, to=s)
        if not targets:
            # still show "Calling…" on the caller; the client times out itself
            emit('call_offline', {'call_id': call_id, 'to': gname, 'group': gid})
        print(f"Group call {me} -> {gname} ({kind}) id={call_id} "
              f"members_online={len(targets)}")
        return

    target = data.get('to_sid') if data.get('to_sid') in connected_clients else None
    if target is None:
        target = _sid_of(to, exclude=request.sid)
    call['callee_sid'] = target
    if target:
        _participants(call).add(target)       # so early video reaches the callee
    active_calls[call_id] = call
    record_activity('call', me, f"{me} \u2192 {to} ({kind} call)",
                    'ringing' if target else 'callee offline')
    if target:
        socketio.emit('incoming_call', {
            'call_id': call_id, 'from': me, 'from_sid': request.sid,
            'kind': kind, 'avatar': my_pic,
        }, to=target)
    else:
        # still show "Calling…" on the caller; the client times out on its own
        emit('call_offline', {'call_id': call_id, 'to': to})
    print(f"Call {me} -> {to} ({kind}) id={call_id} online={bool(target)}")


@socketio.on('call_accept')
def handle_call_accept(data):
    call_id = data.get('call_id')
    call = active_calls.get(call_id)
    if not call:
        return
    me = connected_clients.get(request.sid, {}).get('username') or data.get('from', '')
    _participants(call).add(request.sid)
    if not call.get('group'):
        call['callee_sid'] = request.sid
    n = len(_others(call, None))
    # everyone (the caller included) learns the new participant count
    for s in _others(call, None):
        socketio.emit('call_accepted', {'call_id': call_id, 'by': me,
                                        'count': n}, to=s)
    record_activity('call', me,
                    f"{me} joined {call.get('caller')}'s "
                    + ("group call" if call.get('group') else "call"),
                    call.get('kind', 'voice'))
    print(f"Call accepted: {call_id} by {me} (participants={n})")


@socketio.on('call_reject')
def handle_call_reject(data):
    call_id = data.get('call_id')
    call = active_calls.get(call_id)
    if not call:
        return
    me = connected_clients.get(request.sid, {}).get('username') or data.get('from', '')
    _participants(call).discard(request.sid)
    if call.get('group'):
        # one invitee said no - the group call carries on without them
        for s in _others(call, request.sid):
            socketio.emit('call_rejected', {'call_id': call_id, 'by': me,
                                            'group': call.get('group')}, to=s)
        record_activity('call', me, f"{me} declined a group call", 'declined')
        print(f"Group invite declined: {call_id} by {me}")
        return
    active_calls.pop(call_id, None)
    for s in _others(call, request.sid):
        socketio.emit('call_rejected', {'call_id': call_id, 'by': me}, to=s)
    record_activity('call', me, f"{me} declined {call.get('caller')}'s call",
                    'declined')
    print(f"Call rejected: {call_id} by {me}")


@socketio.on('call_end')
def handle_call_end(data):
    call_id = data.get('call_id')
    call = active_calls.get(call_id)
    if not call:
        return
    by = connected_clients.get(request.sid, {}).get('username') or data.get('from', '')
    # In a group call, whoever STARTED it hangs it up for everyone when they
    # press End. Any other member simply LEAVES: the call stays alive for the
    # people left and only finishes when fewer than two remain.
    if call.get('group') and call.get('initiator') == request.sid:
        active_calls.pop(call_id, None)
        _participants(call).discard(request.sid)
        for s in _others(call):
            socketio.emit('call_ended', {'call_id': call_id, 'by': by,
                                         'reason': 'caller-ended'}, to=s)
        print(f"Group call {call_id} ended by its initiator {by}")
        return
    _leave_call(call_id, call, request.sid, by)
    print(f"Call ended: {call_id} by {by} (left={len(_participants(call))})")


@socketio.on('call_media')
def handle_call_media(data):
    """Relay one audio/video packet to every OTHER participant."""
    call = active_calls.get(data.get('call_id'))
    if not call:
        return
    parts = _participants(call)
    if request.sid not in parts:
        return
    for s in parts:
        if s != request.sid:
            socketio.emit('call_media', data, to=s)


@socketio.on('call_upgrade')
def handle_call_upgrade(data):
    """A voice call is being switched to video -> tell everyone else."""
    call = active_calls.get(data.get('call_id'))
    if not call:
        return
    call['kind'] = data.get('kind') or 'video'
    for s in _others(call, request.sid):
        socketio.emit('call_upgraded', {'call_id': data.get('call_id'),
                                        'kind': call['kind'],
                                        'by': data.get('from')
                                        or call.get('caller')}, to=s)


@socketio.on('call_video')
def handle_call_video(data):
    """Somebody switched their camera on/off -> let the others know."""
    call = active_calls.get(data.get('call_id'))
    if not call:
        return
    for s in _others(call, request.sid):
        socketio.emit('call_video', data, to=s)

__all__ = [
    "_SETTING_LABELS",
    "_end_calls_for_sid",
    "_leave_call",
    "_msg_containers",
    "_msg_targets",
    "_others",
    "_participants",
    "_rename_in_memory",
    "_settings_diff",
    "_sid_of",
    "handle_add_contact",
    "handle_add_server",
    "handle_block_user",
    "handle_call_accept",
    "handle_call_end",
    "handle_call_media",
    "handle_call_reject",
    "handle_call_upgrade",
    "handle_call_video",
    "handle_clear_all_chats",
    "handle_clear_chat",
    "handle_connect",
    "handle_create_group",
    "handle_delete_message",
    "handle_disconnect",
    "handle_get_blocked",
    "handle_get_connected_clients",
    "handle_get_messages",
    "handle_get_servers",
    "handle_group_add_member",
    "handle_group_delete",
    "handle_group_remove_member",
    "handle_group_rename",
    "handle_group_set_pic",
    "handle_join",
    "handle_leave",
    "handle_mark_read",
    "handle_pin_chat",
    "handle_pin_message",
    "handle_react_message",
    "handle_record_call",
    "handle_save_ui_state",
    "handle_send_message",
    "handle_star_message",
    "handle_start_call",
    "handle_unblock_user",
    "handle_update_profile",
    "handle_update_settings",
]
