# server_core.py — Flask/SocketIO setup, configuration, the in-memory
# state, the activity feed, and the cache loader that ties the DB layer to
# the running server.
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

# The persistence layer (schema + queries) lives in server_db.py; importing it
# here re-exports every db_* helper to the rest of the server modules.
from server_db import *

# ===== FLASK APP =====
app = Flask(__name__)
app.config['SECRET_KEY'] = 'whatsapp_clone_secret_2026'
CORS(app)

# Largest Socket.IO packet we accept.  engineio's default is only 1 MB, so any
# attachment bigger than ~750 KB used to kill the socket mid-send (the peer
# then looked "offline" and nothing arrived).  Clients cap attachments at
# 25 MB, which is ~33 MB once base64-encoded, so 64 MB leaves headroom for the
# JSON envelope.
MAX_PAYLOAD = 64 * 1024 * 1024
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading',
                    max_http_buffer_size=MAX_PAYLOAD)

PORT = int(os.environ.get('CHAT_PORT', '5000'))

# ===== CONFIG =====
# How many clients may be connected at the same time. The limit is generous
# (50) and can be overridden from the environment, or live from the dashboard.
MAX_CLIENTS = int(os.environ.get('CHAT_MAX_CLIENTS', '50'))

def max_clients():
    """The live client limit (the dashboard can change it at runtime)."""
    return MAX_CLIENTS


def set_max_clients(v):
    """Update the live client limit and return it."""
    global MAX_CLIENTS
    MAX_CLIENTS = max(1, min(500, int(v)))
    return MAX_CLIENTS



def _usable_ip(ip):
    """True for a real LAN address (not loopback, not an APIPA/self-assigned one)."""
    return bool(ip) and not ip.startswith('127.') and not ip.startswith('169.254.')


def _detect_lan_ips():
    """Every usable IPv4 address of this machine, best candidate first.

    The UDP "connect" below never sends a packet - it only asks the OS which
    interface would be used to reach the outside world.  That is exactly the
    address another PC / phone on the same Wi-Fi has to type to reach us, so it
    is listed before anything found through the hostname.  Loopback and
    169.254.* (self-assigned, i.e. a cable/adapter with no network) are skipped -
    showing them would only send the user to an address that cannot work.
    """
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.3)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if _usable_ip(ip):
            out.append(ip)
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if _usable_ip(ip) and ip not in out:
                out.append(ip)
    except Exception:
        pass
    return out


def _mix(c1, c2, t):
    """Blend two '#rrggbb' colours (t=0 -> c1, t=1 -> c2)."""
    try:
        a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
        b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
        return '#%02x%02x%02x' % tuple(
            max(0, min(255, int(round(a[i] + (b[i] - a[i]) * t)))) for i in range(3))
    except Exception:
        return c1


# smooth "up - down" bob for the live dots (the animation the dashboard uses).
# Two tables, one phase per 100 ms tick; every dot has 5 px of slack around it,
# which is exactly what "max bob (2) + max ring (3)" needs - so nothing clips.
BOB = (0, 1, 2, 2, 1, 0, -1, -2, -2, -1)
# ...and the expanding ping ring around them (0 = hidden)
RING = (0, 1, 2, 3, 0, 0, 0, 0, 0, 0)


connected_clients = {}      # sid -> {username, sid, ip, connected_at}
active_calls = {}           # call_id -> {caller, callee, kind, group, group_name,
                            #             caller_sid, callee_sid, participants:{sid}}
conversations = {}          # (nameA, nameB) sorted -> [ {text, sender, time, status} ]
groups = {}                 # gid -> {id, name, members:[usernames], creator}
group_messages = {}         # gid -> [ messages ]
servers = []
user_settings = {}
call_history = {}           # username -> [ call entries, newest first ]

# ============================================================
# ICONS  (monochrome font glyphs -> crisp, never blurry emoji)
# ============================================================
ICON = {
    "clients":  "\uE716",   # People
    "chat":     "\uE8BD",   # Chat
    "group":    "\uE902",   # Group
    "activity": "\uE9D9",   # Diagnostic / pulse
    "log":      "\uE756",   # CommandPrompt
    "settings": "\uE713",   # Settings
    "search":   "\uE721",
    "send":     "\uE724",
    "add":      "\uE710",
    "person":   "\uE77B",
    "refresh":  "\uE72C",
    "power":    "\uE7E8",
    "warn":     "\uE7BA",
    "key":      "\uE192",
    "bell":     "\uE7E7",
    "box":      "\uE7B8",
    "save":     "\uE74E",
    "dot":      "\u25CF",
}
_ICON_FAMILY = None


def pick_icon_font(widget=None):
    """Resolve (once) an installed monochrome icon font on this machine."""
    global _ICON_FAMILY
    if _ICON_FAMILY:
        return _ICON_FAMILY
    fams = set()
    try:
        fams = set(tkfont.families(widget))
    except Exception:
        pass
    for fam in ("Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol"):
        if fam in fams:
            _ICON_FAMILY = fam
            return fam
    _ICON_FAMILY = "Segoe UI Symbol"
    return _ICON_FAMILY


def ic(name):
    return ICON.get(name, "")


# ============================================================
# ACTIVITY FEED  ("kis ne kya change kiya" - live audit trail)
# ============================================================
activity_log = collections.deque(maxlen=600)
SERVER_UI = None            # set by ServerApp so socket threads can push events

# colour per activity kind, used by the hacker-style terminal
ACT_COLOR = {
    'join':     '#00ff88',
    'leave':    '#ff6b6b',
    'message':  '#7dd3fc',
    'read':     '#a3e635',
    'settings': '#fbbf24',
    'profile':  '#c084fc',
    'group':    '#38bdf8',
    'contact':  '#34d399',
    'call':     '#f472b6',
    'server':   '#94a3b8',
    'view':     '#64748b',
    'error':    '#ff5c5c',
    'info':     '#94a3b8',
}


def record_activity(kind, actor, summary, detail=''):
    """Called from the socket handlers: remember AND show who changed what."""
    item = {
        'ts': datetime.now().strftime("%H:%M:%S"),
        'kind': kind,
        'actor': actor or 'system',
        'summary': summary,
        'detail': detail or '',
    }
    activity_log.append(item)
    try:
        db_add_activity(item)
    except Exception:
        pass
    ui = SERVER_UI
    if ui is not None:
        try:
            ui.root.after(0, lambda it=item: ui.push_activity(it))
        except Exception:
            pass
    return item


def conv_key(a, b):
    """Stable key for the 1-to-1 conversation between two profile names."""
    return tuple(sorted([str(a), str(b)]))


def db_load():
    """Warm the in-memory caches from SQLite (called once at startup)."""
    for row in db_get_activity(200):
        activity_log.append({'ts': row.get('ts') or '', 'kind': row.get('kind') or 'info',
                             'actor': row.get('actor') or 'system',
                             'summary': row.get('summary') or '',
                             'detail': row.get('detail') or ''})
    for row in db_query("SELECT * FROM users"):
        name = row.get('username') or ''
        if not name:
            continue
        try:
            st = json.loads(row.get('settings') or '{}')
        except Exception:
            st = {}
        if st:
            user_settings[name] = st
    for g in db_query("SELECT * FROM groups"):
        members = [m['member'] for m in
                   db_query("SELECT member FROM group_members WHERE gid=?", (g['gid'],))]
        groups[g['gid']] = {'id': g['gid'], 'name': g['name'],
                            'members': members, 'creator': g.get('creator', ''),
                            'creator_ip': g.get('creator_ip', '') or '',
                            'avatar': g.get('avatar', '') or ''}
        group_messages.setdefault(g['gid'], [])
    for m in db_query("SELECT * FROM messages ORDER BY id"):
        item = {'mid': m.get('mid'), 'text': m.get('text'), 'sender': m.get('sender'),
                'time': m.get('time'), 'status': m.get('status'), 'peer': m.get('peer'),
                'day': m.get('day') or '',
                'reply_to': m.get('reply_to') or '',
                'reply_text': m.get('reply_text') or '',
                'reply_sender': m.get('reply_sender') or '',
                'forwarded': bool(m.get('forwarded')),
                'pinned': bool(m.get('pinned')),
                'deleted': bool(m.get('deleted')),
                'deleted_for': _deleted_for(m),
                'reactions': _reactions_of(m),
                'starred_for': _starred_for(m)}
        if (m.get('kind') or 'text') != 'text':
            item.update({'kind': m.get('kind') or 'file',
                         'file_name': m.get('file_name') or '',
                         'file_kind': m.get('file_kind') or 'file',
                         'file_mime': m.get('file_mime') or '',
                         'file_size': m.get('file_size') or 0,
                         'file_dur': m.get('file_dur') or 0,
                         'file_data': m.get('file_data') or ''})
        gid = m.get('gid') or ''
        if gid:
            item['gid'] = gid
            group_messages.setdefault(gid, []).append(item)
        else:
            try:
                key = tuple(json.loads(m.get('conv') or '[]'))
            except Exception:
                continue
            conversations.setdefault(key, []).append(item)
    # the Calls tab is restored from the database as well
    for r in db_query("SELECT DISTINCT owner FROM call_log"):
        owner = r.get('owner') or ''
        if owner:
            call_history[owner] = db_get_calls(owner)
    print(f"[db] loaded {len(conversations)} conversations, "
          f"{len(groups)} groups, {len(call_history)} call logs "
          f"from {os.path.basename(DB_PATH)}")
db_load()

__all__ = [
    "ACT_COLOR",
    "BOB",
    "CORS",
    "DB_PATH",
    "FILE_ICON",
    "Flask",
    "ICON",
    "Image",
    "ImageTk",
    "MAX_CLIENTS",
    "PORT",
    "RING",
    "SERVER_UI",
    "SRV_PIL_OK",
    "SocketIO",
    "_ICON_FAMILY",
    "_conv_of",
    "_db",
    "_db_lock",
    "_deleted_for",
    "_detect_lan_ips",
    "_json_field",
    "_mix",
    "_reactions_of",
    "_starred_for",
    "_usable_ip",
    "active_calls",
    "activity_log",
    "app",
    "base64",
    "call_history",
    "collections",
    "connected_clients",
    "conv_key",
    "conversations",
    "datetime",
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
    "db_load",
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
    "emit",
    "file_fields",
    "group_messages",
    "groups",
    "human_size",
    "ic",
    "io",
    "json",
    "max_clients",
    "MAX_PAYLOAD",
    "messagebox",
    "msg_meta_fields",
    "os",
    "pick_icon_font",
    "preview_text",
    "record_activity",
    "request",
    "scrolledtext",
    "servers",
    "set_max_clients",
    "socket",
    "socketio",
    "sqlite3",
    "threading",
    "tk",
    "tkfont",
    "ttk",
    "user_settings",
    "uuid",
]
