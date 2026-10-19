# server_db.py — SQLite persistence layer: schema, queries and the
# helpers that turn rows into the dicts the server keeps in memory.
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import tkinter.font as tkfont
import threading
import uuid
import os
import io
import json
import base64
import sqlite3
import collections
import socket
from flask import Flask, request
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from datetime import datetime

try:
    from PIL import Image, ImageTk
    SRV_PIL_OK = True
except Exception:
    Image = ImageTk = None
    SRV_PIL_OK = False




# ============================================================
# SQLITE PERSISTENCE
# ============================================================
# Everything the server used to keep only in RAM is mirrored to chat.db, so a
# client that reconnects from the SAME IP gets its name, settings, profile
# photo, contacts and the full chat history back exactly where it left off.
DB_PATH = (os.environ.get('CHAT_DB')
           or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chat.db'))
_db_lock = threading.Lock()


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # WAL + NORMAL keeps commits fast and lets readers run while a write is in
    # flight, so a burst of clients joining at once doesn't queue on fsync.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
    except Exception:
        pass
    return conn


def db_exec(sql, params=()):
    """Run a write statement (thread-safe)."""
    with _db_lock:
        conn = _db()
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()


def db_query(sql, params=()):
    """Run a read statement and return a list of dicts (thread-safe)."""
    with _db_lock:
        conn = _db()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()


def db_init():
    with _db_lock:
        conn = _db()
        try:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                ip        TEXT NOT NULL,
                username  TEXT NOT NULL,
                avatar    TEXT DEFAULT '',
                color     TEXT DEFAULT '#25d366',
                settings  TEXT DEFAULT '{}',
                last_view TEXT DEFAULT 'chats',
                last_chat TEXT DEFAULT '',
                last_seen TEXT DEFAULT '',
                PRIMARY KEY (ip, username)
            );
            CREATE TABLE IF NOT EXISTS contacts (
                owner       TEXT NOT NULL,
                peer        TEXT NOT NULL,
                peer_type   TEXT DEFAULT 'single',
                peer_avatar TEXT DEFAULT '',
                peer_color  TEXT DEFAULT '#2c2c2c',
                peer_pic    TEXT DEFAULT '',
                last_msg    TEXT DEFAULT '',
                last_time   TEXT DEFAULT '',
                unread      INTEGER DEFAULT 0,
                added_at    TEXT DEFAULT '',
                pinned      INTEGER DEFAULT 0,
                last_ts     REAL DEFAULT 0,
                pin_ts      REAL DEFAULT 0,
                PRIMARY KEY (owner, peer)
            );
            CREATE TABLE IF NOT EXISTS blocked (
                owner      TEXT NOT NULL,
                peer       TEXT NOT NULL,
                blocked_at TEXT DEFAULT '',
                PRIMARY KEY (owner, peer)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                conv   TEXT NOT NULL,
                mid    TEXT,
                sender TEXT,
                text   TEXT,
                time   TEXT,
                status TEXT,
                peer   TEXT,
                gid    TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv);
            CREATE TABLE IF NOT EXISTS groups (
                gid        TEXT PRIMARY KEY,
                name       TEXT,
                creator    TEXT,
                creator_ip TEXT DEFAULT '',
                avatar     TEXT DEFAULT '',
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS group_members (
                gid    TEXT NOT NULL,
                member TEXT NOT NULL,
                PRIMARY KEY (gid, member)
            );
            CREATE TABLE IF NOT EXISTS activity (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      TEXT,
                kind    TEXT,
                actor   TEXT,
                summary TEXT,
                detail  TEXT
            );
            CREATE TABLE IF NOT EXISTS call_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                owner       TEXT NOT NULL,
                peer        TEXT DEFAULT '',
                peer_avatar TEXT DEFAULT '',
                peer_color  TEXT DEFAULT '#2c2c2c',
                kind        TEXT DEFAULT 'voice',
                outcome     TEXT DEFAULT '',
                dur         INTEGER DEFAULT 0,
                time        TEXT DEFAULT '',
                day         TEXT DEFAULT '',
                created     TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_call_owner ON call_log(owner);
            """)
            # ---- migration: file-transfer columns on `messages` -------------
            # (older chat.db files do not have them -> add them in place)
            have = {r['name'] for r in
                    conn.execute("PRAGMA table_info(messages)").fetchall()}
            for col, decl in (('kind',      "TEXT DEFAULT 'text'"),
                              ('file_name', "TEXT DEFAULT ''"),
                              ('file_kind', "TEXT DEFAULT ''"),
                              ('file_mime', "TEXT DEFAULT ''"),
                              ('file_size', "INTEGER DEFAULT 0"),
                              ('file_data', "TEXT DEFAULT ''"),
                              ('file_dur',  "INTEGER DEFAULT 0"),
                              ('day',       "TEXT DEFAULT ''"),
                              ('reply_to',  "TEXT DEFAULT ''"),
                              ('reply_text', "TEXT DEFAULT ''"),
                              ('reply_sender', "TEXT DEFAULT ''"),
                              ('forwarded', "INTEGER DEFAULT 0"),
                              ('pinned',    "INTEGER DEFAULT 0"),
                              ('deleted',   "INTEGER DEFAULT 0"),
                              ('deleted_for', "TEXT DEFAULT '[]'"),
                              ('reactions', "TEXT DEFAULT '{}'"),
                              ('starred_for', "TEXT DEFAULT '[]'")):
                if col not in have:
                    conn.execute("ALTER TABLE messages ADD COLUMN %s %s" % (col, decl))
            # ---- migration: pin flag on contacts, creator_ip on groups --------
            chave = {r['name'] for r in
                     conn.execute("PRAGMA table_info(contacts)").fetchall()}
            for col, decl in (('pinned', "INTEGER DEFAULT 0"),
                              ('last_ts', "REAL DEFAULT 0"),
                              ('pin_ts', "REAL DEFAULT 0")):
                if col not in chave:
                    conn.execute("ALTER TABLE contacts ADD COLUMN %s %s" % (col, decl))
            ghave = {r['name'] for r in
                     conn.execute("PRAGMA table_info(groups)").fetchall()}
            for col, decl in (('creator_ip', "TEXT DEFAULT ''"),
                              ('avatar', "TEXT DEFAULT ''")):
                if col not in ghave:
                    conn.execute("ALTER TABLE groups ADD COLUMN %s %s" % (col, decl))
            # one-time backfill so chats that existed before `last_ts` still sort
            # sensibly (older rows get their original added-at time)
            try:
                conn.execute("UPDATE contacts SET last_ts = CAST(strftime('%s', added_at) AS REAL) "
                             "WHERE (last_ts IS NULL OR last_ts = 0) AND added_at != ''")
            except Exception:
                pass
            conn.commit()
        finally:
            conn.close()


def _conv_of(msg):
    """Stable TEXT key for a message row: 'g:<gid>' or a JSON [a, b] pair."""
    gid = msg.get('gid') or ''
    if gid:
        return 'g:' + gid
    return json.dumps(sorted([msg.get('sender', ''), msg.get('peer', '')]))


def db_add_message(msg):
    db_exec("""INSERT INTO messages (conv, mid, sender, text, time, status, peer, gid,
                                     kind, file_name, file_kind, file_mime, file_size,
                                     file_data, file_dur, day, reply_to, reply_text,
                                     reply_sender, forwarded, pinned, deleted, deleted_for)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_conv_of(msg), msg.get('mid'), msg.get('sender'), msg.get('text'),
             msg.get('time'), msg.get('status'), msg.get('peer'), msg.get('gid') or '',
             msg.get('kind') or 'text', msg.get('file_name') or '',
             msg.get('file_kind') or '', msg.get('file_mime') or '',
             int(msg.get('file_size') or 0), msg.get('file_data') or '',
             int(msg.get('file_dur') or 0), msg.get('day') or '',
             msg.get('reply_to') or '', msg.get('reply_text') or '',
             msg.get('reply_sender') or '', 1 if msg.get('forwarded') else 0,
             1 if msg.get('pinned') else 0, 1 if msg.get('deleted') else 0,
             json.dumps(msg.get('deleted_for') or [])))


# ---- file-transfer helpers -------------------------------------------------
FILE_ICON = {'image': 'Photo', 'video': 'Video', 'audio': 'Audio', 'file': 'Document'}


def human_size(n):
    """1234567 -> '1.2 MB' (used by the dashboard transcript)."""
    try:
        n = float(n)
    except Exception:
        return '0 B'
    if n < 1024:
        return '%d B' % int(n)
    for unit in ('KB', 'MB', 'GB'):
        n /= 1024.0
        if n < 1024 or unit == 'GB':
            return '%.1f %s' % (n, unit)
    return '%.1f GB' % n


def file_fields(data):
    """Pick the file-transfer fields out of an incoming message payload."""
    kind = str(data.get('kind') or 'text')
    if kind == 'text':
        return {}
    return {'kind': kind,
            'file_name': str(data.get('file_name') or ''),
            'file_kind': str(data.get('file_kind') or 'file'),
            'file_mime': str(data.get('file_mime') or ''),
            'file_size': int(data.get('file_size') or 0),
            'file_dur': int(data.get('file_dur') or 0),
            'file_data': data.get('file_data') or ''}


def msg_meta_fields(data):
    """Reply / forward metadata that rides along with any message."""
    return {'day': datetime.now().strftime("%Y-%m-%d"),
            'reply_to': str(data.get('reply_to') or ''),
            'reply_text': str(data.get('reply_text') or '')[:160],
            'reply_sender': str(data.get('reply_sender') or ''),
            'forwarded': 1 if data.get('forwarded') else 0}


def _deleted_for(m):
    """List of usernames that deleted this message for themselves only."""
    v = m.get('deleted_for')
    if isinstance(v, list):
        return v
    try:
        return json.loads(v or '[]')
    except Exception:
        return []


def _json_field(m, key, default):
    """Read a JSON-encoded TEXT column back into a Python object."""
    v = m.get(key)
    if isinstance(v, (dict, list)):
        return v
    try:
        out = json.loads(v or '')
        return out if isinstance(out, type(default)) else default
    except Exception:
        return default


def _reactions_of(m):
    """{emoji: [usernames]} for a message row."""
    r = _json_field(m, 'reactions', {})
    return r if isinstance(r, dict) else {}


def _starred_for(m):
    """Usernames that starred this message."""
    return _json_field(m, 'starred_for', [])


def preview_text(text, data):
    """Short chat-list preview: 'Photo: caption' / 'Document: file.pdf'."""
    if str(data.get('kind') or 'text') == 'text':
        return text
    label = FILE_ICON.get(str(data.get('file_kind') or 'file'), 'File')
    if label == 'Document' and data.get('file_name'):
        label = 'Document: ' + os.path.basename(str(data['file_name']))
    cap = (text or '').strip()
    return label + (': ' + cap if cap else '')


def db_set_status(mid, status):
    """Delivery/read ticks are persisted so they survive a reconnect."""
    db_exec("UPDATE messages SET status=? WHERE mid=?", (status, mid))


# ---- call history (persisted so the Calls tab survives a restart) ----
def db_add_call(entry):
    db_exec("""INSERT INTO call_log
               (owner, peer, peer_avatar, peer_color, kind, outcome, dur,
                time, day, created)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (entry.get('owner', ''), entry.get('peer', ''),
             entry.get('peer_avatar', ''), entry.get('peer_color', '#2c2c2c'),
             entry.get('kind', 'voice'), entry.get('outcome', ''),
             int(entry.get('dur') or 0), entry.get('time', ''),
             entry.get('day', ''), entry.get('created', '')))


def db_get_calls(owner, limit=300):
    """Newest first."""
    rows = db_query("""SELECT * FROM call_log WHERE owner=?
                       ORDER BY id DESC LIMIT ?""", (owner, int(limit)))
    return [{'peer': r.get('peer') or '', 'peer_avatar': r.get('peer_avatar') or '',
             'peer_color': r.get('peer_color') or '#2c2c2c',
             'kind': r.get('kind') or 'voice', 'outcome': r.get('outcome') or '',
             'dur': int(r.get('dur') or 0), 'time': r.get('time') or '',
             'day': r.get('day') or ''} for r in rows]


def db_get_user(ip, username):
    """A user is identified by the (IP, display name) pair, so two clients on
    the same machine can still keep separate histories."""
    rows = db_query("SELECT * FROM users WHERE ip=? AND username=?", (ip, username))
    return rows[0] if rows else None


def db_save_user(ip, username, **kw):
    """Insert / update one user row. Omitted fields keep their old value."""
    if not username:
        return
    cur = db_get_user(ip, username) or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_exec("""INSERT INTO users (ip, username, avatar, color, settings,
                                  last_view, last_chat, last_seen)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(ip, username) DO UPDATE SET
                 avatar=excluded.avatar, color=excluded.color,
                 settings=excluded.settings, last_view=excluded.last_view,
                 last_chat=excluded.last_chat, last_seen=excluded.last_seen""",
            (ip, username,
             kw.get('avatar', cur.get('avatar', '')),
             kw.get('color', cur.get('color', '#25d366')),
             json.dumps(kw['settings']) if 'settings' in kw else cur.get('settings', '{}'),
             kw.get('last_view', cur.get('last_view', 'chats')),
             kw.get('last_chat', cur.get('last_chat', '')),
             now))


def db_rename_user(ip, old, new):
    """A client renamed itself in Settings -> move the record (and its data)."""
    if not old or not new or old == new:
        return
    # grab the affected message rows first so their conversation key can be rebuilt
    rows = db_query("SELECT id, sender, peer, gid FROM messages "
                    "WHERE sender=? OR peer=?", (old, old))
    db_exec("UPDATE users SET username=? WHERE ip=? AND username=?", (new, ip, old))
    for sql in ("UPDATE contacts SET owner=? WHERE owner=?",
                "UPDATE contacts SET peer=? WHERE peer=?",
                "UPDATE messages SET sender=? WHERE sender=?",
                "UPDATE messages SET peer=? WHERE peer=?",
                "UPDATE group_members SET member=? WHERE member=?"):
        db_exec(sql, (new, old))
    for r in rows:
        if r.get('gid'):
            continue                     # group rows are keyed by gid, not by name
        sender = new if r.get('sender') == old else r.get('sender')
        peer = new if r.get('peer') == old else r.get('peer')
        db_exec("UPDATE messages SET conv=? WHERE id=?",
                (json.dumps(sorted([sender or '', peer or ''])), r['id']))


def db_add_contact(owner, c):
    """Persist one contact of `owner` (idempotent upsert)."""
    now_ts = datetime.now().timestamp()
    db_exec("""INSERT INTO contacts (owner, peer, peer_type, peer_avatar, peer_color,
                                     peer_pic, last_msg, last_time, unread, pinned,
                                     last_ts, pin_ts, added_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(owner, peer) DO UPDATE SET
                 peer_type=excluded.peer_type, peer_avatar=excluded.peer_avatar,
                 peer_color=excluded.peer_color, peer_pic=excluded.peer_pic,
                 last_msg=excluded.last_msg, last_time=excluded.last_time,
                 unread=excluded.unread, pinned=excluded.pinned,
                 pin_ts=CASE WHEN excluded.pinned=1 AND excluded.pin_ts=0
                             THEN contacts.pin_ts ELSE excluded.pin_ts END,
                 last_ts=excluded.last_ts""",
            (owner, c.get('name', ''), c.get('type', 'single'),
             c.get('avatar', ''), c.get('color', '#2c2c2c'), c.get('pic', ''),
             c.get('lastMsg', ''), c.get('time', ''),
             int(c.get('unread', 0) or 0),
             1 if c.get('pinned') else 0,
             float(c.get('last_ts') or now_ts),
             float(c.get('pin_ts') or 0),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def db_set_pinned(owner, peer, pinned, pin_ts=None):
    """Pin / unpin a chat for one owner (does not touch the other fields).

    `pin_ts` records *when* the chat was pinned so the most recently pinned
    chat can float to the very top (pinned chats are ordered by it).
    """
    if not owner or not peer:
        return
    if pinned:
        try:
            ts = float(pin_ts or 0)
        except Exception:
            ts = 0.0
        if ts <= 0:
            ts = datetime.now().timestamp()
    else:
        ts = 0.0
    db_exec("UPDATE contacts SET pinned=?, pin_ts=? WHERE owner=? AND peer=?",
            (1 if pinned else 0, ts, owner, peer))


# ---- blocked clients (persisted so the block list survives a restart) ----
def db_block(owner, peer):
    if not owner or not peer:
        return
    db_exec("""INSERT OR IGNORE INTO blocked (owner, peer, blocked_at)
               VALUES (?,?,?)""",
            (owner, peer, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def db_unblock(owner, peer):
    db_exec("DELETE FROM blocked WHERE owner=? AND peer=?", (owner, peer))


def db_get_blocked(owner):
    rows = db_query("SELECT peer, blocked_at FROM blocked WHERE owner=? "
                    "ORDER BY blocked_at, peer", (owner,))
    return [{'peer': r.get('peer') or '', 'blocked_at': r.get('blocked_at') or ''}
            for r in rows]


def db_is_blocked(owner, peer):
    if not owner or not peer:
        return False
    return bool(db_query("SELECT 1 FROM blocked WHERE owner=? AND peer=? LIMIT 1",
                         (owner, peer)))


def db_upsert_contact(owner, peer, peer_type='single', last_msg='',
                      unread_inc=0, color=None):
    """Refresh the preview (and optionally bump the unread badge) of `peer`.

    A single atomic statement per call, so several socket threads handling
    messages at the same time can never clobber each other's unread count.
    """
    now_h = datetime.now().strftime("%H:%M")
    now_d = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now_ts = datetime.now().timestamp()
    if unread_inc:
        db_exec("""INSERT INTO contacts (owner, peer, peer_type, peer_color,
                                         last_msg, last_time, unread, last_ts, added_at)
                   VALUES (?,?,?,?,?,?,1,?,?)
                   ON CONFLICT(owner, peer) DO UPDATE SET
                     last_msg=excluded.last_msg, last_time=excluded.last_time,
                     last_ts=excluded.last_ts,
                     unread=contacts.unread + 1""",
                (owner, peer, peer_type, color or '#2c2c2c', last_msg, now_h,
                 now_ts, now_d))
    else:
        db_exec("""INSERT INTO contacts (owner, peer, peer_type, peer_color,
                                         last_msg, last_time, unread, last_ts, added_at)
                   VALUES (?,?,?,?,?,?,0,?,?)
                   ON CONFLICT(owner, peer) DO UPDATE SET
                     last_msg=excluded.last_msg, last_time=excluded.last_time,
                     last_ts=excluded.last_ts""",
                (owner, peer, peer_type, color or '#2c2c2c', last_msg, now_h,
                 now_ts, now_d))


def db_get_contacts(owner):
    return db_query("SELECT * FROM contacts WHERE owner=? ORDER BY added_at, peer",
                    (owner,))


def db_clear_unread(owner, peer):
    db_exec("UPDATE contacts SET unread=0 WHERE owner=? AND peer=?", (owner, peer))


def db_add_group(group):
    db_exec("""INSERT INTO groups (gid, name, creator, creator_ip, avatar, created_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(gid) DO UPDATE SET name=excluded.name,
                                              creator=excluded.creator,
                                              creator_ip=excluded.creator_ip,
                                              avatar=excluded.avatar""",
            (group['id'], group['name'], group.get('creator', ''),
             group.get('creator_ip', ''), group.get('avatar', ''),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    for m in group['members']:
        db_exec("INSERT OR IGNORE INTO group_members (gid, member) VALUES (?,?)",
                (group['id'], m))


def db_set_group_name(gid, name):
    db_exec("UPDATE groups SET name=? WHERE gid=?", (name, gid))


def db_set_group_avatar(gid, avatar):
    db_exec("UPDATE groups SET avatar=? WHERE gid=?", (avatar, gid))


def db_rename_group_contacts(old_name, new_name):
    """Keep every member's stored group contact in sync after a rename."""
    if not old_name or not new_name:
        return
    db_exec("UPDATE contacts SET peer=? WHERE peer=? AND peer_type='group'",
            (new_name, old_name))


def db_add_group_member(gid, member):
    db_exec("INSERT OR IGNORE INTO group_members (gid, member) VALUES (?,?)",
            (gid, member))


def db_remove_group_member(gid, member):
    db_exec("DELETE FROM group_members WHERE gid=? AND member=?", (gid, member))


def db_delete_group(gid, name=''):
    """Admin deletes the whole group (and every member's copy of it)."""
    db_exec("DELETE FROM groups WHERE gid=?", (gid,))
    db_exec("DELETE FROM group_members WHERE gid=?", (gid,))
    db_exec("DELETE FROM messages WHERE gid=?", (gid,))
    if name:
        db_exec("DELETE FROM contacts WHERE peer_type='group' AND peer=?", (name,))


def db_add_activity(item):
    db_exec("""INSERT INTO activity (ts, kind, actor, summary, detail)
               VALUES (?,?,?,?,?)""",
            (item.get('ts'), item.get('kind'), item.get('actor'),
             item.get('summary'), item.get('detail')))
    # keep the audit trail from growing without bound
    db_exec("""DELETE FROM activity WHERE id <=
               (SELECT MAX(id) - 800 FROM activity)""")


def db_get_activity(limit=250):
    rows = db_query("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))
    rows.reverse()
    return rows


db_init()

__all__ = [
    "DB_PATH",
    "FILE_ICON",
    "_conv_of",
    "_db",
    "_db_lock",
    "_deleted_for",
    "_json_field",
    "_reactions_of",
    "_starred_for",
    "db_add_activity",
    "db_add_call",
    "db_add_contact",
    "db_add_group",
    "db_add_group_member",
    "db_add_message",
    "db_block",
    "db_clear_unread",
    "db_delete_group",
    "db_exec",
    "db_get_activity",
    "db_get_blocked",
    "db_get_calls",
    "db_get_contacts",
    "db_get_user",
    "db_init",
    "db_is_blocked",
    "db_query",
    "db_remove_group_member",
    "db_rename_group_contacts",
    "db_rename_user",
    "db_save_user",
    "db_set_group_avatar",
    "db_set_group_name",
    "db_set_pinned",
    "db_set_status",
    "db_unblock",
    "db_upsert_contact",
    "file_fields",
    "human_size",
    "msg_meta_fields",
    "preview_text",
]
