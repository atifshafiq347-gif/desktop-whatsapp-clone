# client_core.py — shared imports, constants, widgets, theme, audio,
# session helpers and small utilities for the LAN chat client.
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="audioop")

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
import threading
import socket
import queue
import sys
import os
import io
import time
import uuid
import math
import array
import wave
import base64
import hashlib
import struct
import json
import ctypes
import mimetypes
import socketio
from datetime import datetime, timedelta

try:
    import winsound
except Exception:                                   # non-Windows / unavailable
    winsound = None

try:
    import pyaudio as _pyaudio                      # microphone capture
    PYAUDIO_OK = True
except Exception:                                   # pip install pyaudio
    _pyaudio = None
    PYAUDIO_OK = False

# audioop resamples between the device rate and the 16 kHz wire format, so two
# laptops whose sound cards do not agree on 16 kHz can still talk to each other
try:
    import audioop as _audioop
except Exception:
    _audioop = None

# Pillow is optional: with it we can crop any picture (jpg/png/...) into a
# circular profile photo. Without it we fall back to coloured initials.
try:
    from PIL import Image, ImageDraw, ImageTk
    PIL_OK = True
except Exception:
    Image = ImageDraw = ImageTk = None
    PIL_OK = False

# OpenCV powers the video call (webcam capture + JPEG frames over the socket).
try:
    import cv2 as _cv2
    import numpy as _np
    CV2_OK = True
except Exception:                                   # pip install opencv-python
    _cv2 = None
    _np = None
    CV2_OK = False


APP_DIR = os.path.dirname(os.path.abspath(__file__))
RINGTONE_DIR = os.path.join(APP_DIR, "ringtones")


def valid_ipv4(addr):
    """True only for a well-formed IPv4 address like 192.168.1.10."""
    try:
        parts = addr.strip().split(".")
        if len(parts) != 4:
            return False
        for p in parts:
            if not p.isdigit() or len(p) > 3 or not (0 <= int(p) <= 255):
                return False
        return True
    except Exception:
        return False


class WindowsVolume:
    """Read/set the Windows master output volume (Core Audio API via ctypes).

    Falls back to simulated media volume keys if the COM API is unavailable.
    """
    _CLSID_ENUM = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
    _IID_ENUM = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
    _IID_VOL = "{5CDF2C82-841E-4546-9722-0CF74078229A}"

    def __init__(self):
        self.ok = False
        self._set_fn = None
        self._get_fn = None
        self._iface = None
        self._level = 50
        if sys.platform == "win32":
            try:
                self._init_com()
                self.ok = True
                v = self.get()
                if v is not None:
                    self._level = v
            except Exception:
                self.ok = False

    def _init_com(self):
        import ctypes
        from ctypes import (POINTER, byref, c_void_p, c_float, c_uint,
                            c_ulong, c_ushort, c_ubyte, c_long, c_wchar_p,
                            Structure)
        ole32 = ctypes.windll.ole32

        class GUID(Structure):
            _fields_ = [("Data1", c_ulong), ("Data2", c_ushort),
                        ("Data3", c_ushort), ("Data4", c_ubyte * 8)]

        def make_guid(s):
            g = GUID()
            hr = ole32.CLSIDFromString(c_wchar_p(s), byref(g))
            if hr != 0:
                raise OSError(f"CLSIDFromString({s}) -> {hr}")
            return g

        ole32.CoInitialize(None)
        enum = c_void_p()
        hr = ole32.CoCreateInstance(byref(make_guid(self._CLSID_ENUM)), None, 23,
                                    byref(make_guid(self._IID_ENUM)), byref(enum))
        if hr != 0 or not enum:
            raise OSError(f"CoCreateInstance -> {hr}")

        # IMMDeviceEnumerator::GetDefaultAudioEndpoint (vtable index 4)
        vt = ctypes.cast(enum, POINTER(POINTER(c_void_p)))[0]
        GetDefault = ctypes.WINFUNCTYPE(c_long, c_void_p, c_uint, c_uint,
                                        POINTER(c_void_p))(vt[4])
        dev = c_void_p()
        hr = GetDefault(enum, 0, 1, byref(dev))       # eRender, eMultimedia
        if hr != 0 or not dev:
            raise OSError(f"GetDefaultAudioEndpoint -> {hr}")

        # IMMDevice::Activate (vtable index 3)
        vtd = ctypes.cast(dev, POINTER(POINTER(c_void_p)))[0]
        Activate = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(GUID), c_uint,
                                      c_void_p, POINTER(c_void_p))(vtd[3])
        iface = c_void_p()
        hr = Activate(dev, byref(make_guid(self._IID_VOL)), 23, None, byref(iface))
        if hr != 0 or not iface:
            raise OSError(f"Activate -> {hr}")

        # IAudioEndpointVolume: Set=index 7, Get=index 9
        vt2 = ctypes.cast(iface, POINTER(POINTER(c_void_p)))[0]
        self._set_fn = ctypes.WINFUNCTYPE(c_long, c_void_p, c_float, c_void_p)(vt2[7])
        self._get_fn = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(c_float))(vt2[9])
        self._iface = iface

    def get(self):
        if self.ok and self._get_fn:
            try:
                import ctypes
                val = ctypes.c_float(0.0)
                if self._get_fn(self._iface, ctypes.byref(val)) == 0:
                    return int(round(val.value * 100))
            except Exception:
                pass
        return self._level

    def set(self, level):
        level = max(0, min(100, int(level)))
        if self.ok and self._set_fn:
            try:
                import ctypes
                if self._set_fn(self._iface, ctypes.c_float(level / 100.0), None) == 0:
                    self._level = level
                    return True
            except Exception:
                pass
        # fallback: simulate volume up/down keys
        try:
            import ctypes
            VK_UP, VK_DOWN = 0xAF, 0xAE
            delta = level - self._level
            vk = VK_UP if delta > 0 else VK_DOWN
            for _ in range(min(abs(delta) // 2, 50)):
                ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            self._level = level
            return True
        except Exception:
            return False


# ===== NOTIFICATION RINGTONES =====
class RingtonePlayer:
    """Plays notification ringtones at an app-level volume (Windows).

    Ships with ~18 built-in tones that are *synthesised* into small WAV files
    the first time the client runs (so no asset files are needed), and it can
    also play any custom file the user picks (wav / mp3 / m4a / wma).

    The notification volume defaults to a low 15 % and only affects this
    ringtone (the system volume is a separate slider).
    """

    SR = 22050

    # (label, waveform, [(freq_hz, seconds), ...])   freq 0 == short silence
    TONES = [
        ("Classic",   'sine',   [(988, 0.16), (1175, 0.22)]),
        ("WhatsApp",  'sine',   [(1319, 0.09), (1760, 0.16)]),
        ("Chime",     'sine',   [(880, 0.11), (1109, 0.11), (1319, 0.20)]),
        ("Ping",      'sine',   [(1568, 0.18)]),
        ("Pop",       'tri',    [(988, 0.06), (740, 0.10)]),
        ("Bell",      'bell',   [(1046, 0.55)]),
        ("Marimba",   'tri',    [(523, 0.10), (784, 0.16)]),
        ("Droplet",   'sine',   [(1200, 0.05), (600, 0.22)]),
        ("Retro",     'square', [(523, 0.10), (659, 0.10), (784, 0.14)]),
        ("Breeze",    'sine',   [(660, 0.30)]),
        ("Alert",     'square', [(880, 0.07), (0, 0.05), (880, 0.07), (0, 0.05), (880, 0.07)]),
        ("Note",      'sine',   [(987, 0.28)]),
        ("Trill",     'sine',   [(1200, 0.06), (1500, 0.06), (1200, 0.06), (1500, 0.10)]),
        ("Digital",   'square', [(1046, 0.09), (0, 0.05), (1046, 0.13)]),
        ("Soft Knob", 'sine',   [(330, 0.10), (700, 0.16)]),
        ("Trio",      'sine',   [(659, 0.12), (880, 0.12), (1108, 0.20)]),
        ("Echo",      'sine',   [(740, 0.09), (925, 0.09), (740, 0.09), (925, 0.16)]),
        ("Beep",      'square', [(1000, 0.12)]),
    ]

    # 10 longer, "ring-ring" style tones for incoming / outgoing calls
    CALL_TONES = [
        ("Ring Classic",   'sine',   [(440, 0.40), (0, 0.20), (480, 0.40), (0, 0.20),
                                      (440, 0.40), (0, 0.20), (480, 0.55)]),
        ("Ring Old Phone", 'bell',   [(660, 0.35), (0, 0.15), (660, 0.35), (0, 0.15),
                                      (660, 0.35), (0, 0.15), (660, 0.60)]),
        ("Ring Digital",   'square', [(880, 0.18), (0, 0.10), (1200, 0.18), (0, 0.10),
                                      (880, 0.18), (0, 0.10), (1200, 0.30)]),
        ("Ring Marimba",   'tri',    [(523, 0.22), (784, 0.22), (0, 0.18),
                                      (523, 0.22), (784, 0.40)]),
        ("Ring Trill",     'sine',   [(1319, 0.10), (1760, 0.10), (1319, 0.10), (1760, 0.10),
                                      (0, 0.18), (1319, 0.10), (1760, 0.10), (1319, 0.35)]),
        ("Ring Pulse",     'sine',   [(784, 0.14), (0, 0.12), (784, 0.14), (0, 0.12),
                                      (784, 0.14), (0, 0.12), (784, 0.14), (0, 0.12),
                                      (784, 0.45)]),
        ("Ring Retro",     'square', [(392, 0.20), (523, 0.20), (659, 0.20),
                                      (0, 0.15), (392, 0.20), (523, 0.20), (659, 0.45)]),
        ("Ring Soft",      'sine',   [(587, 0.45), (0, 0.25), (587, 0.45), (0, 0.25),
                                      (587, 0.70)]),
        ("Ring Echo",      'sine',   [(740, 0.16), (988, 0.16), (0, 0.14),
                                      (740, 0.16), (988, 0.16), (0, 0.14), (740, 0.45)]),
        ("Ring Alert",     'square', [(1046, 0.12), (1318, 0.12), (1046, 0.12),
                                      (0, 0.14), (1046, 0.12), (1318, 0.12), (1046, 0.40)]),
    ]

    def __init__(self, folder=RINGTONE_DIR, tones=None, volume=100):
        self.folder = folder
        self.tones = tones if tones is not None else self.TONES
        self.volume = volume                 # default notification volume
        self.path = ""
        self._buf = None                     # keeps async-played buffer alive
        self._mci = False
        self._generated = {}
        try:
            os.makedirs(self.folder, exist_ok=True)
        except Exception:
            pass
        self.ensure_builtins()

    # ---------- synthesis ----------
    @classmethod
    def _tone_samples(cls, waveform, notes):
        sr = cls.SR
        out = array.array('h')
        for freq, dur in notes:
            n = max(1, int(sr * dur))
            if freq <= 0:
                out.extend([0] * n)
                continue
            for i in range(n):
                t = i / float(sr)
                env = math.exp(-3.4 * t / max(dur, 1e-6))
                env *= min(1.0, i / (sr * 0.004))          # click-free attack
                w = 2 * math.pi * freq * t
                if waveform == 'square':
                    v = 1.0 if math.sin(w) >= 0 else -1.0
                elif waveform == 'tri':
                    v = 4.0 * abs(((freq * t) % 1.0) - 0.5) - 1.0
                elif waveform == 'bell':
                    v = (math.sin(w) + 0.5 * math.sin(2 * w) +
                         0.25 * math.sin(3 * w)) / 1.75
                else:
                    v = math.sin(w)
                out.append(int(max(-1.0, min(1.0, v * env)) * 0.6 * 32767))
        return out

    def _tone_file(self, label):
        slug = label.lower().replace(' ', '_') + ".wav"
        return os.path.join(self.folder, slug)

    def ensure_builtins(self):
        """Create any missing built-in tone WAVs (once)."""
        for label, waveform, notes in self.tones:
            p = self._tone_file(label)
            self._generated[label] = p
            if os.path.exists(p) and os.path.getsize(p) > 44:
                continue
            try:
                samples = self._tone_samples(waveform, notes)
                with wave.open(p, 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(self.SR)
                    w.writeframes(samples.tobytes())
            except Exception:
                pass

    def labels(self):
        return [t[0] for t in self.tones]

    def builtin_path(self, label):
        return self._generated.get(label) or self._tone_file(label)

    # ---------- config ----------
    def set_volume(self, v):
        try:
            self.volume = max(0, min(100, int(v)))
        except Exception:
            self.volume = 100

    def set_label(self, label):
        """Select a built-in tone by its label."""
        self.path = self.builtin_path(label)
        return self.path

    def set_file(self, path):
        self.path = path or ""
        return self.path

    # ---------- playback ----------
    @staticmethod
    def _wav_bytes(frames, sr, sw, ch, factor):
        if sw == 2 and factor < 0.999:
            a = array.array('h')
            a.frombytes(frames)
            for i in range(len(a)):
                a[i] = int(a[i] * factor)
            frames = a.tobytes()
        bio = io.BytesIO()
        with wave.open(bio, 'wb') as w:
            w.setnchannels(ch)
            w.setsampwidth(sw)
            w.setframerate(sr)
            w.writeframes(frames)
        return bio.getvalue()

    def _play_wav(self, path):
        with wave.open(path, 'rb') as w:
            sw, sr = w.getsampwidth(), w.getframerate()
            ch, n = w.getnchannels(), w.getnframes()
            frames = w.readframes(n)
        buf = self._wav_bytes(frames, sr, sw, ch, self.volume / 100.0)
        self._buf = buf                    # must outlive the async playback
        winsound.PlaySound(buf, winsound.SND_MEMORY | winsound.SND_ASYNC |
                           winsound.SND_NODEFAULT)
        return True

    def _play_mci(self, path):
        ext = os.path.splitext(path)[1].lower()
        typ = 'waveaudio' if ext == '.wav' else 'mpegvideo'
        winmm = ctypes.windll.winmm
        winmm.mciSendStringW('close rtone', None, 0, 0)
        rc = winmm.mciSendStringW(f'open "{path}" type {typ} alias rtone',
                                  None, 0, 0)
        if rc != 0:
            rc = winmm.mciSendStringW(f'open "{path}" alias rtone', None, 0, 0)
            if rc != 0:
                return False
        if self.volume < 100:
            winmm.mciSendStringW(f'setaudio rtone volume to {int(self.volume * 10)}',
                                 None, 0, 0)
        winmm.mciSendStringW('play rtone', None, 0, 0)
        self._mci = True
        return True

    def play(self):
        """Play the selected ringtone once at the configured volume."""
        path = self.path
        if not path or not os.path.exists(path) or self.volume <= 0:
            return False
        if winsound is not None and path.lower().endswith('.wav'):
            try:
                return self._play_wav(path)
            except Exception:
                pass
        try:
            return self._play_mci(path)
        except Exception:
            return False

    def stop(self):
        try:
            if winsound is not None:
                winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        try:
            if self._mci:
                ctypes.windll.winmm.mciSendStringW('close rtone', None, 0, 0)
                self._mci = False
        except Exception:
            pass


# ===== ICON GLYPHS =====
# Monochrome, pixel-crisp icons (Segoe MDL2 Assets / Segoe Fluent Icons on Windows)
ICON = {
    "search":   "\uE721",
    "settings": "\uE713",
    "phone":    "\uE717",
    "video":    "\uE714",
    "more":     "\uE712",
    "attach":   "\uE723",
    "mic":      "\uE720",
    "send":     "\uE724",
    "message":  "\uE8BD",
    "add":      "\uE710",
    "person":   "\uE77B",
    "group":    "\uE902",
    "play":     "\uE768",
    "photo":    "\uE91B",
    "music":    "\uE8D6",
    "doc":      "\uE8A5",
    "download": "\uE896",
    "close":    "\uE711",
    "emoji":    "\uE76E",
    "file":     "\uE7C3",
    "status":   "\u25C9",   # ring (rendered with a symbol font)
    # ---- call controls (Segoe MDL2 / Fluent) ----
    "volume":   "\uE767",   # speaker
    "switch":   "\uE72C",   # switch / flip camera
    "hangup":   "\uE717",   # phone (rotated for the hang-up button)
    "adduser":  "\uE8FA",   # add person to call
    "camoff":   "\uE714",   # camera (slashed when off)
    # ---- in-chat search navigation ----
    "chevup":   "\uE70E",   # previous match
    "chevdn":   "\uE70D",   # next match
    # ---- pinned chats ----
    "pin":      "\uE718",   # push-pin (pinned chat marker)
}


# ===== FILE / ATTACHMENT SUPPORT =====
# When a file is shown we draw the logo of the software that opens it, so a
# Word file shows the Word logo, an Excel file the Excel logo, a PDF the PDF
# logo, and so on.  Each entry is  (app title, brand colour, short mark, glyph)
# where the glyph is one of the ICON keys above (or None -> draw the mark).
FILE_APP_LOGO = {
    'doc':  ('Microsoft Word',       '#2b579a', 'W',   None),
    'docx': ('Microsoft Word',       '#2b579a', 'W',   None),
    'dot':  ('Microsoft Word',       '#2b579a', 'W',   None),
    'dotx': ('Microsoft Word',       '#2b579a', 'W',   None),
    'rtf':  ('Microsoft Word',       '#2b579a', 'W',   None),
    'odt':  ('Word Document',        '#2b579a', 'W',   None),
    'xls':  ('Microsoft Excel',      '#217346', 'X',   None),
    'xlsx': ('Microsoft Excel',      '#217346', 'X',   None),
    'xlsm': ('Microsoft Excel',      '#217346', 'X',   None),
    'csv':  ('Microsoft Excel',      '#217346', 'X',   None),
    'ods':  ('Excel Spreadsheet',    '#217346', 'X',   None),
    'ppt':  ('Microsoft PowerPoint', '#c43e1c', 'P',   None),
    'pptx': ('Microsoft PowerPoint', '#c43e1c', 'P',   None),
    'pps':  ('Microsoft PowerPoint', '#c43e1c', 'P',   None),
    'ppsx': ('Microsoft PowerPoint', '#c43e1c', 'P',   None),
    'odp':  ('PowerPoint Slides',    '#c43e1c', 'P',   None),
    'pdf':  ('PDF Document',         '#b30b00', 'PDF', None),
    'txt':  ('Notepad',              '#5b6a73', None,  'doc'),
    'log':  ('Notepad',              '#5b6a73', None,  'doc'),
    'md':   ('Notepad',              '#5b6a73', None,  'doc'),
    'ini':  ('Notepad',              '#5b6a73', None,  'doc'),
    'json': ('Code Editor',          '#6d4c1e', None,  'doc'),
    'xml':  ('Code Editor',          '#6d4c1e', None,  'doc'),
    'html': ('Web Browser',          '#e34f26', None,  'doc'),
    'htm':  ('Web Browser',          '#e34f26', None,  'doc'),
    'py':   ('Python',               '#3776ab', None,  'doc'),
    'js':   ('Code Editor',          '#f0db4f', None,  'doc'),
    'c':    ('Code Editor',          '#5b6a73', None,  'doc'),
    'cpp':  ('Code Editor',          '#5b6a73', None,  'doc'),
    'java': ('Code Editor',          '#e76f00', None,  'doc'),
    'zip':  ('Archive',              '#8a6d3b', None,  'file'),
    'rar':  ('Archive',              '#8a6d3b', None,  'file'),
    '7z':   ('Archive',              '#8a6d3b', None,  'file'),
    'gz':   ('Archive',              '#8a6d3b', None,  'file'),
    'tar':  ('Archive',              '#8a6d3b', None,  'file'),
    'exe':  ('Application',          '#4c6a92', None,  'file'),
    'msi':  ('Application',          '#4c6a92', None,  'file'),
    'apk':  ('Android App',          '#3ddc84', None,  'file'),
    'png':  ('Photos',               '#8957e5', None,  'photo'),
    'jpg':  ('Photos',               '#8957e5', None,  'photo'),
    'jpeg': ('Photos',               '#8957e5', None,  'photo'),
    'gif':  ('Photos',               '#8957e5', None,  'photo'),
    'bmp':  ('Photos',               '#8957e5', None,  'photo'),
    'webp': ('Photos',               '#8957e5', None,  'photo'),
    'tif':  ('Photos',               '#8957e5', None,  'photo'),
    'tiff': ('Photos',               '#8957e5', None,  'photo'),
    'svg':  ('Photos',               '#8957e5', None,  'photo'),
    'ico':  ('Photos',               '#8957e5', None,  'photo'),
    'heic': ('Photos',               '#8957e5', None,  'photo'),
    'mp4':  ('Media Player',         '#c0392b', None,  'video'),
    'mkv':  ('Media Player',         '#c0392b', None,  'video'),
    'mov':  ('Media Player',         '#c0392b', None,  'video'),
    'avi':  ('Media Player',         '#c0392b', None,  'video'),
    'wmv':  ('Media Player',         '#c0392b', None,  'video'),
    'webm': ('Media Player',         '#c0392b', None,  'video'),
    'flv':  ('Media Player',         '#c0392b', None,  'video'),
    'm4v':  ('Media Player',         '#c0392b', None,  'video'),
    '3gp':  ('Media Player',         '#c0392b', None,  'video'),
    'mp3':  ('Music',                '#e67e22', None,  'music'),
    'wav':  ('Music',                '#e67e22', None,  'music'),
    'm4a':  ('Music',                '#e67e22', None,  'music'),
    'aac':  ('Music',                '#e67e22', None,  'music'),
    'ogg':  ('Music',                '#e67e22', None,  'music'),
    'flac': ('Music',                '#e67e22', None,  'music'),
    'wma':  ('Music',                '#e67e22', None,  'music'),
    'opus': ('Music',                '#e67e22', None,  'music'),
}

# short chat-list label per file kind (mirrors the server's preview text)
FILE_KIND_LABEL = {'image': 'Photo', 'video': 'Video',
                   'audio': 'Audio', 'file': 'Document'}


def file_kind_of(name, mime=''):
    """Classify an attachment as image / video / audio / file."""
    ext = os.path.splitext(str(name or ''))[1].lower().lstrip('.')
    glyph = FILE_APP_LOGO.get(ext, (None, None, None, None))[3]
    if glyph == 'photo':
        return 'image'
    if glyph == 'video':
        return 'video'
    if glyph == 'music':
        return 'audio'
    mime = (mime or '').lower()
    if mime.startswith('image/'):
        return 'image'
    if mime.startswith('video/'):
        return 'video'
    if mime.startswith('audio/'):
        return 'audio'
    return 'file'


def file_logo(filename, kind=''):
    """(app title, brand colour, short mark, glyph) of the file's software."""
    ext = os.path.splitext(str(filename or ''))[1].lower().lstrip('.')
    if ext in FILE_APP_LOGO:
        return FILE_APP_LOGO[ext]
    kind = kind or file_kind_of(filename)
    if kind == 'image':
        return ('Photos', '#8957e5', None, 'photo')
    if kind == 'video':
        return ('Media Player', '#c0392b', None, 'video')
    if kind == 'audio':
        return ('Music', '#e67e22', None, 'music')
    return ('File', '#4c6a92', None, 'file')


def human_size(n):
    """1234567 -> '1.2 MB'."""
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


def _rrect(cv, x1, y1, x2, y2, r, fill, outline="", tags=()):
    """Draw a rounded rectangle on a canvas (Tk has no native radius).

    Built from 4 overlapping pies/ovals + 2 crossing rectangles, which stays
    perfectly crisp at any size.  Shared by the bubbles, the rounded buttons
    and the modern scrollbar.
    """
    r = max(1, int(r))
    cv.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill=fill, outline=outline, tags=tags)
    cv.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill=fill, outline=outline, tags=tags)
    cv.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill=fill, outline=outline, tags=tags)
    cv.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill=fill, outline=outline, tags=tags)
    cv.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=outline, tags=tags)
    cv.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=outline, tags=tags)


# ===== MODERN SCROLLBAR =====
class ModernScrollbar(tk.Canvas):
    """A slim, rounded, self-hiding scrollbar.

    Behaviours that make it feel like the flat scrollbars in modern chat apps:

    * it only packs itself while the content is really taller than the view
      (nothing to scroll -> the strip disappears and the panel gets the space)
    * no arrows, no 3-D grip, no trough texture - just a soft rounded thumb
    * the thumb is thin while the pointer is away and widens on hover / drag
    * clicking the track jumps, dragging moves, and both stay smooth

    It exposes the same interface a Tk scrollbar does (`command=` + `.set()`),
    so a canvas can use it as its `yscrollcommand` unchanged.
    """

    IDLE_W = 5          # thumb width while the pointer is elsewhere
    HOVER_W = 8         # thumb width while hovered or dragged
    MIN_THUMB = 22      # never paint a thumb shorter than this
    PAD = 3             # gap between the thumb and the panel edges

    def __init__(self, master, command=None, width=12, parent_bg='#1e1e1e',
                 thumb='#4a4a4a', thumb_hover='#5f6d75', **kw):
        super().__init__(master, width=width, bg=parent_bg, bd=0,
                         highlightthickness=0, takefocus=0, **kw)
        self._cmd = command
        self._strip = int(width)      # our own strip width (never touch Tk's `_w`)
        self._bg = parent_bg
        self._thumb_c = thumb
        self._hover_c = thumb_hover
        self._lo, self._hi = 0.0, 1.0
        self._hover = False
        self._drag_dy = None
        self._shown = False
        self.bind('<Configure>', lambda e: self._redraw())
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<Button-1>', self._on_press)
        self.bind('<B1-Motion>', self._on_drag)
        self.bind('<ButtonRelease-1>', self._on_release)

    # ---- the scrollbar protocol ----
    def set(self, lo, hi):
        try:
            lo, hi = float(lo), float(hi)
        except Exception:
            return
        needed = (hi - lo) < 0.999        # a fraction of a pixel must not count
        if needed and not self._shown:
            self._shown = True
            try:
                self.pack(side=tk.RIGHT, fill=tk.Y)
                self.lift()
            except Exception:
                pass
        elif not needed and self._shown and self._drag_dy is None:
            self._shown = False
            try:
                self.pack_forget()
            except Exception:
                pass
        self._lo, self._hi = lo, hi
        self._redraw()

    def theme_remap(self, bgmap, fgmap):
        """Re-skin for the active theme (called by the app's retheme pass)."""
        self._bg = bgmap.get(self._bg.lower(), self._bg)
        self._thumb_c = bgmap.get(self._thumb_c.lower(), self._thumb_c)
        self._hover_c = bgmap.get(self._hover_c.lower(), self._hover_c)
        try:
            self.configure(bg=self._bg)
        except Exception:
            pass
        self._redraw()

    # ---- internals ----
    def _span(self):
        h = max(1, self.winfo_height())
        top = int(self._lo * h)
        bot = int(self._hi * h)
        if bot - top < self.MIN_THUMB:
            bot = min(h, top + self.MIN_THUMB)
            top = max(0, bot - self.MIN_THUMB)
        return top, bot, h

    def _redraw(self):
        try:
            self.delete('thumb')
        except Exception:
            return
        if not self._shown:
            return
        top, bot, h = self._span()
        active = self._hover or self._drag_dy is not None
        wt = self.HOVER_W if active else self.IDLE_W
        col = self._hover_c if active else self._thumb_c
        x0 = (self._strip - wt) // 2
        y0 = top + self.PAD
        y1 = bot - self.PAD
        if y1 - y0 < 8:
            y1 = min(h, y0 + 8)
        try:
            _rrect(self, x0, y0, x0 + wt, y1, wt // 2, col, tags=('thumb',))
        except Exception:
            pass

    def _on_enter(self, e=None):
        self._hover = True
        self._redraw()

    def _on_leave(self, e=None):
        if self._drag_dy is None:
            self._hover = False
            self._redraw()

    def _on_press(self, e):
        top, bot, h = self._span()
        if top <= e.y <= bot:
            self._drag_dy = e.y - top
        else:
            frac = min(max(e.y / float(h), 0.0), 1.0) - (self._hi - self._lo) / 2.0
            self._jump_to(frac)
            self._drag_dy = (bot - top) // 2
        self._redraw()

    def _on_drag(self, e):
        if self._drag_dy is None:
            return
        top, bot, h = self._span()
        room = max(1, h - (bot - top))
        self._jump_to((e.y - self._drag_dy) / float(room))

    def _on_release(self, e=None):
        self._drag_dy = None
        if not self._hover:
            self._redraw()

    def _jump_to(self, frac):
        frac = min(max(float(frac), 0.0), 1.0)
        try:
            self._cmd('moveto', frac)
        except Exception:
            pass


# ===== ROUNDED BUTTON (Tkinter doesn't support radius natively) =====
class RoundedButton(tk.Canvas):
    def __init__(self, parent, text="", icon=None, icon_font=None, command=None,
                 bg="#2c2c2c", fg="white", hover_bg=None, font=("Segoe UI", 12),
                 padx=14, pady=6, radius=14, width=None, height=None,
                 parent_bg="#121212", enabled=True, active_bg="#25d366",
                 active_fg="white", inactive_bg="#2c2c2c", inactive_fg="#bdc3c7",
                 align="center", icon_gap=7, pad_left=None, draw_extra=None, **kwargs):
        self.font_spec = font
        self.text = text
        self.icon = icon
        self.icon_font = icon_font or font
        self.align = align
        self.icon_gap = icon_gap
        f = tkfont.Font(font=font)
        fi = tkfont.Font(font=self.icon_font)
        self.text_w = f.measure(text) if text else 0
        self.icon_w = fi.measure(icon) if icon else 0
        line_h = max(f.metrics("linespace"), fi.metrics("linespace"))
        content_w = self.icon_w + (self.icon_gap if (icon and text) else 0) + self.text_w
        self.w = width if width else max(content_w + padx * 2, 2 * radius + 4)
        self.h = height if height else line_h + pady * 2
        self.pad_left = pad_left if pad_left is not None else padx
        self.radius = max(0, min(radius, self.h // 2, self.w // 2))
        super().__init__(parent, width=self.w, height=self.h, bg=parent_bg,
                         highlightthickness=0, bd=0, **kwargs)
        self.command = command
        self.bg_color = bg
        self.fg_color = fg
        self.hover_color = hover_bg or self._adjust(bg)
        self.parent_bg = parent_bg
        self.enabled = enabled
        self.active_bg = active_bg
        self.active_fg = active_fg
        self.inactive_bg = inactive_bg
        self.inactive_fg = inactive_fg
        self.is_active = (bg == active_bg)
        self.draw_extra = draw_extra
        self._draw(self.bg_color)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    @staticmethod
    def _adjust(color):
        try:
            r = int(color[1:3], 16); g = int(color[3:5], 16); b = int(color[5:7], 16)
            r = min(255, r + 24); g = min(255, g + 24); b = min(255, b + 24)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return color

    def _draw(self, bg):
        self.delete("all")
        r, w, h = self.radius, self.w, self.h
        # rounded rectangle out of overlapping shapes
        self.create_oval(0, 0, 2 * r, 2 * r, fill=bg, outline=bg)
        self.create_oval(w - 2 * r, 0, w, 2 * r, fill=bg, outline=bg)
        self.create_oval(0, h - 2 * r, 2 * r, h, fill=bg, outline=bg)
        self.create_oval(w - 2 * r, h - 2 * r, w, h, fill=bg, outline=bg)
        self.create_rectangle(r, 0, w - r, h, fill=bg, outline=bg)
        self.create_rectangle(0, r, w, h - r, fill=bg, outline=bg)
        cy = h / 2
        if self.icon and self.text:
            content_w = self.icon_w + self.icon_gap + self.text_w
            x = self.pad_left if self.align == "left" else (w - content_w) / 2
            self.create_text(x, cy, text=self.icon, fill=self.fg_color,
                             font=self.icon_font, anchor="w")
            self.create_text(x + self.icon_w + self.icon_gap, cy, text=self.text,
                             fill=self.fg_color, font=self.font_spec, anchor="w")
        elif self.icon:
            self.create_text(w / 2, cy, text=self.icon, fill=self.fg_color, font=self.icon_font)
        else:
            self.create_text(w / 2, cy, text=self.text, fill=self.fg_color, font=self.font_spec)
        if self.draw_extra:
            self.draw_extra(self, bg)

    def _on_enter(self, e):
        if self.enabled:
            self._draw(self.hover_color)

    def _on_leave(self, e):
        if self.enabled:
            self._draw(self.bg_color)

    def _on_click(self, e):
        if self.enabled and self.command:
            self.command()

    def set_active(self, active):
        self.is_active = active
        self.bg_color = self.active_bg if active else self.inactive_bg
        self.fg_color = self.active_fg if active else self.inactive_fg
        self.hover_color = self._adjust(self.bg_color)
        self._draw(self.bg_color)

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.bg_color = self.active_bg if enabled else "#3c3c3c"
        self.fg_color = self.active_fg if enabled else "#8696a0"
        self.hover_color = self._adjust(self.bg_color)
        self._draw(self.bg_color)

    def set_bg(self, color):
        self.bg_color = color
        self.hover_color = self._adjust(color)
        self._draw(self.bg_color)

    def theme_remap(self, bgmap, fgmap):
        """Re-skin this button for a new theme."""
        for name in ('bg_color', 'active_bg', 'inactive_bg', 'parent_bg'):
            cur = getattr(self, name, None)
            if isinstance(cur, str) and cur.lower() in bgmap:
                setattr(self, name, bgmap[cur.lower()])
        for name in ('fg_color', 'active_fg', 'inactive_fg'):
            cur = getattr(self, name, None)
            if isinstance(cur, str) and cur.lower() in fgmap:
                setattr(self, name, fgmap[cur.lower()])
        # the canvas background (visible around the rounded shape) must follow too
        try:
            self.configure(bg=self.parent_bg)
        except Exception:
            pass
        # keep labels readable: white text on a now-light button -> dark text
        for bg_name, fg_name in (('bg_color', 'fg_color'),
                                 ('active_bg', 'active_fg'),
                                 ('inactive_bg', 'inactive_fg')):
            bg = getattr(self, bg_name, None)
            fg = getattr(self, fg_name, None)
            if not isinstance(bg, str) or not isinstance(fg, str):
                continue
            lb, lf = _lum_str(bg), _lum_str(fg)
            if lb is not None and lf is not None and lf > 0.8 and lb > 0.62:
                setattr(self, fg_name, '#111b21')
        self.hover_color = self._adjust(self.bg_color)
        self._draw(self.bg_color)


# ===== ROUNDED BOX (a frame with rounded corners, for inputs/search) =====
class RoundedBox(tk.Frame):
    """Frame whose corners are rounded by 4 small masking canvases drawn on top."""
    def __init__(self, parent, radius=16, bg="#2c2c2c", parent_bg="#1e1e1e", **kw):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0, **kw)
        self.radius = radius
        self.box_bg = bg
        self.parent_bg = parent_bg
        self._corners = []
        for pos in ("nw", "ne", "sw", "se"):
            c = tk.Canvas(self, bg=parent_bg, highlightthickness=0, bd=0,
                          width=radius, height=radius)
            c._pos = pos
            self._corners.append(c)
        self._draw_corners()
        self.bind("<Configure>", self._place_corners)

    def _draw_corners(self):
        r = self.radius
        for c in self._corners:
            c.delete("all")
            if c._pos == "nw":
                c.create_arc(0, 0, 2 * r, 2 * r, start=90, extent=90, style=tk.PIESLICE,
                             fill=self.box_bg, outline=self.box_bg)
            elif c._pos == "ne":
                c.create_arc(-r, 0, r, 2 * r, start=0, extent=90, style=tk.PIESLICE,
                             fill=self.box_bg, outline=self.box_bg)
            elif c._pos == "sw":
                c.create_arc(0, -r, 2 * r, r, start=180, extent=90, style=tk.PIESLICE,
                             fill=self.box_bg, outline=self.box_bg)
            else:
                c.create_arc(-r, -r, r, r, start=270, extent=90, style=tk.PIESLICE,
                             fill=self.box_bg, outline=self.box_bg)

    def _place_corners(self, e=None):
        r = self.radius
        w, h = self.winfo_width(), self.winfo_height()
        for c in self._corners:
            if c._pos == "nw":
                c.place(x=0, y=0, width=r, height=r)
            elif c._pos == "ne":
                c.place(x=w - r, y=0, width=r, height=r)
            elif c._pos == "sw":
                c.place(x=0, y=h - r, width=r, height=r)
            else:
                c.place(x=w - r, y=h - r, width=r, height=r)
            # raise the corner mask above the embedded content (Text/Entry)
            c.tk.call('raise', c._w)

    def set_bg(self, color):
        self.box_bg = color
        self.configure(bg=color)
        for ch in self.winfo_children():
            if not isinstance(ch, tk.Canvas):
                try:
                    ch.configure(bg=color)
                except Exception:
                    pass
        self._draw_corners()

    def theme_remap(self, bgmap, fgmap):
        """Re-skin this rounded box (body + corner masks) for a new theme."""
        if self.box_bg.lower() in bgmap:
            self.box_bg = bgmap[self.box_bg.lower()]
        if self.parent_bg.lower() in bgmap:
            self.parent_bg = bgmap[self.parent_bg.lower()]
        try:
            self.configure(bg=self.box_bg)
        except Exception:
            pass
        for c in self._corners:
            try:
                c.configure(bg=self.parent_bg)
            except Exception:
                pass
        self._draw_corners()
        self._place_corners()


class PlaceholderEntry(tk.Entry):
    """A normal Entry that shows grey placeholder text while it is empty.

    The placeholder vanishes the instant the field is clicked / focused and
    comes back if you click away without typing - exactly like the real app.
    `get()` returns '' while the placeholder is on, so filtering and the send
    button logic never see it.
    """

    def __init__(self, parent, placeholder='', **kw):
        kw.setdefault('bd', 0)
        kw.setdefault('relief', tk.FLAT)
        super().__init__(parent, **kw)
        self._ph = placeholder
        self._ph_on = False
        self.bind('<FocusIn>', self._ph_in, add='+')
        self.bind('<FocusOut>', self._ph_out, add='+')
        self.bind('<Button-1>', self._ph_click, add='+')
        # typing goes through Tk's own insert, bypassing our Python insert(),
        # so clear the placeholder on the key press itself
        self.bind('<KeyPress>', self._ph_key, add='+')
        self._show_ph()

    # ---- theme-aware colours (derived from the live background) ----
    def _colors(self):
        """(text colour, placeholder colour) for whichever theme is active."""
        try:
            lb = _lum_str(self.cget('bg'))
        except Exception:
            lb = None
        if lb is not None and lb > 0.6:          # light background
            return '#111b21', '#54656f'
        return '#ffffff', '#8696a0'

    def _show_ph(self):
        if not self._ph or super().get():
            return
        _real, ph = self._colors()
        try:
            self.configure(fg=ph)
        except Exception:
            pass
        super().insert(0, self._ph)
        self._ph_on = True

    def _hide_ph(self):
        if not self._ph_on:
            return
        self._ph_on = False
        super().delete(0, tk.END)
        real, _ph = self._colors()
        try:
            self.configure(fg=real)
        except Exception:
            pass

    def _ph_click(self, e=None):
        if self._ph_on:
            self._hide_ph()
            try:
                self.icursor(0)
            except Exception:
                pass

    def _ph_in(self, e=None):
        self._hide_ph()

    def _ph_out(self, e=None):
        if not super().get():
            self._show_ph()

    def _ph_key(self, e=None):
        if self._ph_on and getattr(e, 'char', ''):
            self._hide_ph()

    # ---- public API (placeholder aware) ----
    def get(self):
        if self._ph_on:
            return ''
        return super().get()

    def insert(self, index, string):
        self._hide_ph()
        return super().insert(index, string)

    def delete(self, first, last=None):
        try:
            if last is None:
                return super().delete(first)
            return super().delete(first, last)
        except Exception:
            return None

    def set_text(self, text):
        """Programmatic set (never shows the placeholder mid-typing)."""
        self._hide_ph()
        super().delete(0, tk.END)
        if text:
            super().insert(0, text)
        self._ph_out()

# ===== SOCKET.IO CLIENT =====
# request_timeout is raised from the 5 s default: a 25 MB attachment becomes
# ~33 MB of base64 and can easily take longer than 5 s to upload over Wi-Fi.
sio = socketio.Client(request_timeout=30)


# ===== MODERN LEFT-SIDE NOTIFICATIONS (React-toast style) =====
class Notifier:
    """Stackable toast notifications on the left side with a 5s countdown bar.

    Each toast slides in from the left, shows an icon + title + message, and
    drains a progress bar at the bottom until it disappears (click to dismiss).
    """
    W, H, GAP = 344, 84, 10

    STYLES = {
        'message':  ("\uE8BD", '#25d366'),   # chat bubble
        'group':    ("\uE902", '#75b798'),
        'client':   ("\uE77B", '#1f6feb'),   # person added
        'settings': ("\uE713", '#e3b341'),
        'call':     ("\uE717", '#25d366'),
        'info':     ("\uE946", '#8696a0'),
        'warn':     ("\uE7BA", '#e3b341'),
        'error':    ("\uE783", '#ff5c5c'),
        'offline':  ("\uE7BA", '#8696a0'),
    }

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.items = []          # newest first
        self.base_x = 14
        self.base_y = 64
        self.tick_ms = 30
        self.max_visible = 4

    # ---- helpers ----
    @staticmethod
    def _clip(text, n):
        text = (text or '').replace('\n', ' ').strip()
        return text if len(text) <= n else text[:n - 1] + '\u2026'

    def _ring_rect(self, cv, x1, y1, x2, y2, r, fill, outline=''):
        self.app._round_rect(cv, x1, y1, x2, y2, r, fill, outline)

    def _paint(self, cv, icon, color, title, message):
        W, H = self.W, self.H
        light = getattr(self.app, 'theme_name', 'Dark') == 'Light'
        border = '#d1d7db' if light else '#3b4a56'
        card = '#ffffff' if light else '#202c33'
        fg_main = '#111b21' if light else '#e9edef'
        fg_sub = '#54656f' if light else '#aebac1'
        track = '#d1d7db' if light else '#2a3942'
        close_fg = '#54656f' if light else '#8696a0'
        cv.configure(bg='#e9eef2' if light else '#121212')
        # card + subtle border
        self._ring_rect(cv, 0, 0, W, H, 14, border)
        self._ring_rect(cv, 1, 1, W - 1, H - 1, 13, card)
        # icon circle
        cv.create_oval(16, 18, 56, 58, fill=color, outline='')
        cv.create_text(36, 38, text=icon, fill='white',
                       font=(self.app.icon_family, 15))
        # texts
        cv.create_text(68, 18, text=self._clip(title, 30), anchor='nw',
                       fill=fg_main, font=('Segoe UI', 11, 'bold'))
        cv.create_text(68, 39, text=self._clip(message, 42), anchor='nw',
                       fill=fg_sub, font=('Segoe UI', 10))
        # close button
        cv.create_text(W - 20, 18, text='\u2715', anchor='nw', fill=close_fg,
                       font=('Segoe UI', 10, 'bold'), tags='close')
        # progress bar (track + fill)
        cv.create_rectangle(16, H - 15, W - 16, H - 11, fill=track, outline='')
        cv.create_rectangle(16, H - 15, W - 16, H - 11, fill=color,
                            outline='', tags='bar')

    # ---- layout / lifecycle ----
    def _relayout(self, animate=False):
        for i, it in enumerate(self.items):
            it['target_y'] = self.base_y + i * (self.H + self.GAP)
            if not animate:
                it['y'] = it['target_y']
            it['cv'].place(x=it['x'], y=it['y'])

    def notify(self, title, message='', kind='info', duration=5000):
        icon, color = self.STYLES.get(kind, self.STYLES['info'])
        cv = tk.Canvas(self.root, width=self.W, height=self.H,
                       bg='#121212', highlightthickness=0, bd=0, cursor='hand2')
        self._paint(cv, icon, color, title, message)
        item = {'cv': cv, 'x': -self.W, 'y': self.base_y, 'target_y': self.base_y,
                'remain': duration, 'dur': duration, 'done': False, 'timer': None}
        cv.bind('<Button-1>', lambda e, it=item: self.dismiss(it))
        self.items.insert(0, item)
        # keep the newest N only
        while len(self.items) > self.max_visible:
            self.dismiss(self.items[-1])
        self._relayout()
        cv.place(x=item['x'], y=item['y'])
        try:
            cv.tkraise()
        except Exception:
            pass
        self._tick(item)
        return item

    def _tick(self, item):
        if item['done']:
            return
        cv = item['cv']
        # slide in from the left
        if item['x'] < self.base_x:
            item['x'] = min(self.base_x, item['x'] + max(10, (self.base_x - item['x'] + 4) // 3))
        # ease toward the target y (so closing one moves the rest up smoothly)
        if abs(item['y'] - item['target_y']) > 1:
            item['y'] += int((item['target_y'] - item['y']) / 2) or (
                1 if item['target_y'] > item['y'] else -1)
        try:
            cv.place(x=item['x'], y=item['y'])
        except Exception:
            return
        # drain the progress bar
        item['remain'] -= self.tick_ms
        frac = max(0.0, item['remain'] / float(item['dur']))
        W, H = self.W, self.H
        try:
            cv.coords('bar', 16, H - 15, 16 + (W - 32) * frac, H - 11)
        except Exception:
            pass
        if item['remain'] <= 0:
            self.dismiss(item)
            return
        item['timer'] = self.root.after(self.tick_ms, lambda: self._tick(item))

    def dismiss(self, item):
        if item.get('done'):
            return
        item['done'] = True
        if item.get('timer'):
            try:
                self.root.after_cancel(item['timer'])
            except Exception:
                pass
        try:
            item['cv'].destroy()
        except Exception:
            pass
        self.items = [i for i in self.items if i is not item]
        self._relayout(animate=True)


SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'client_session.json')


def load_local_session():
    """Remember the last name + server IP locally so the welcome popup is
    pre-filled and the server can restore this user's session immediately."""
    try:
        with open(SESSION_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_local_session(name, ip):
    try:
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump({'name': name, 'ip': ip}, f, indent=2)
    except Exception:
        pass


def normalize_server(value, default_port=5000):
    """Turn whatever was typed into (host, port).

    Deliberately forgiving: a stray scheme, port or trailing slash must never
    be the reason a client cannot reach the server.

        '192.168.1.5'              -> ('192.168.1.5', 5000)
        '192.168.1.5:5000'         -> ('192.168.1.5', 5000)
        'http://192.168.1.5:5000/' -> ('192.168.1.5', 5000)
        '  localhost  '            -> ('localhost', 5000)
    """
    v = (value or '').strip().replace(' ', '')
    if '://' in v:
        v = v.split('://', 1)[1]
    v = v.split('/', 1)[0]
    host, port = v, default_port
    if v.startswith('['):                       # [::1]:5000
        host, _, rest = v[1:].partition(']')
        port = rest[1:] or default_port
    elif v.count(':') == 1:
        host, _, port = v.partition(':')
        port = port or default_port
    try:
        port = int(port)
    except Exception:
        port = default_port
    if not (1 <= port <= 65535):
        port = default_port
    return host.strip(), port


def server_url_from(value, default_port=5000):
    """The http URL the socketio client needs, built from the typed address."""
    host, port = normalize_server(value, default_port)
    if not host:
        return ''
    if host.strip('[]').lower() in ('localhost', '127.0.0.1', '::1'):
        return "http://127.0.0.1:%d" % port
    return "http://%s:%d" % (host, port)


def local_ipv4():
    """This machine's LAN IPv4 address (the interface the OS routes through)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def scan_lan_for_server(port=5000, timeout=0.4, workers=48):
    """Scan this machine's /24 for a chat server listening on `port`.

    Wireless networks hand out addresses by DHCP, so the server's address can
    change (or the user simply typed the old one).  Instead of failing, the
    connect dialog can find the server again.  Returns a sorted list of IPs.
    """
    base = local_ipv4()
    if not base or base.count('.') != 3:
        return []
    prefix = base.rsplit('.', 1)[0]
    todo = ["%s.%d" % (prefix, i) for i in range(1, 255)]
    found, lock = [], threading.Lock()

    def probe():
        while True:
            with lock:
                if not todo:
                    return
                ip = todo.pop()
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                ok = s.connect_ex((ip, port)) == 0
                try:
                    s.close()
                except Exception:
                    pass
            except Exception:
                ok = False
            if ok:
                with lock:
                    found.append(ip)

    threads = [threading.Thread(target=probe, daemon=True)
               for _ in range(max(1, min(workers, len(todo))))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    found.sort(key=lambda h: tuple(int(x) for x in h.split('.')))
    return found


def get_server_ip():
    """Startup dialog: ask for the profile name AND the server IP (LAN)."""
    saved = load_local_session()
    ip_win = tk.Tk()
    ip_win.title("Connect to Server")
    ip_win.configure(bg="#121212")
    ip_win.resizable(False, False)
    w, h = 420, 450
    x = (ip_win.winfo_screenwidth() // 2) - (w // 2)
    y = (ip_win.winfo_screenheight() // 2) - (h // 2)
    ip_win.geometry(f'{w}x{h}+{x}+{y}')
    result = {"ip": None, "name": "You"}

    # WhatsApp-style logo
    logo = tk.Label(ip_win, text="\U0001F4AC", bg="#121212", fg="#25d366", font=("Segoe UI", 30))
    logo.pack(pady=(22, 4))
    tk.Label(ip_win, text="WhatsApp Clone", bg="#121212", fg="white",
             font=("Segoe UI", 16, "bold")).pack()

    tk.Label(ip_win, text="Your Profile Name:", bg="#121212", fg="#bdc3c7",
             font=("Segoe UI", 11)).pack(pady=(18, 4))
    name_e = tk.Entry(ip_win, font=("Segoe UI", 13), width=24, justify="center",
                      bg="#1e1e1e", fg="white", insertbackground="#25d366",
                      relief=tk.FLAT, bd=0)
    name_e.pack(ipady=6)
    name_e.insert(0, saved.get('name') or "You")
    name_e.focus()

    tk.Label(ip_win, text="Server IP (LAN):", bg="#121212", fg="#bdc3c7",
             font=("Segoe UI", 11)).pack(pady=(16, 4))
    ip_e = tk.Entry(ip_win, font=("Segoe UI", 13), width=24, justify="center",
                    bg="#1e1e1e", fg="white", insertbackground="#25d366",
                    relief=tk.FLAT, bd=0)
    ip_e.pack(ipady=6)
    ip_e.insert(0, saved.get('ip') or "192.168.1.100")

    tk.Label(ip_win, text="e.g.  192.168.100.13     (port 5000 is automatic)",
             bg="#121212", fg="#7f8c8d",
             font=("Segoe UI", 9)).pack(pady=(10, 0))

    err = tk.Label(ip_win, text="", bg="#121212", fg="#ff5c5c",
                   font=("Segoe UI", 10, "bold"), wraplength=380, justify="center")
    err.pack(pady=(6, 0))

    def test_conn():
        """Quick reachability check so a wrong IP is obvious before connecting."""
        host, port = normalize_server(ip_e.get())
        if not host:
            err.configure(text="Enter the server IP", fg="#ff5c5c")
            return
        err.configure(text="Testing %s:%d ..." % (host, port), fg="#f0b232")
        ip_win.update_idletasks()
        try:
            s = socket.create_connection((host, port), timeout=3.0)
            s.close()
            err.configure(text="\u2713 Server reachable  %s:%d" % (host, port),
                          fg="#25d366")
        except Exception as e:
            why = (str(e).strip() or 'timed out')[:44]
            err.configure(text="\u2717 Not reachable  (%s)" % why, fg="#ff5c5c")

    def connect():
        name = name_e.get().strip()
        host, port = normalize_server(ip_e.get())
        if not name:
            err.configure(text="Enter your profile name", fg="#ff5c5c")
            return
        if not host:
            err.configure(text="Enter the server IP", fg="#ff5c5c")
            return
        result["name"] = name
        result["ip"] = host if port == 5000 else "%s:%d" % (host, port)
        save_local_session(name, result["ip"])
        ip_win.destroy()

    def cancel():
        result["ip"] = None
        ip_win.destroy()

    scan_state = {'result': None, 'running': False}

    def _scan_thread():
        try:
            r = scan_lan_for_server()
        except Exception:
            r = []
        scan_state['result'] = r
        scan_state['running'] = False

    def _poll_scan():
        if scan_state['running']:
            ip_win.after(250, _poll_scan)
            return
        found = scan_state['result'] or []
        try:
            btn_scan.configure(state=tk.NORMAL)
        except Exception:
            pass
        if found:
            ip_e.delete(0, tk.END)
            ip_e.insert(0, found[0])
            if len(found) > 1:
                err.configure(text="\u2713 Found %d servers - using %s"
                                   % (len(found), found[0]), fg="#25d366")
            else:
                err.configure(text="\u2713 Found the server at %s" % found[0],
                              fg="#25d366")
        else:
            err.configure(text="\u2717 No server on this network - is the server "
                               "running, and are both PCs on the same Wi-Fi?",
                          fg="#ff5c5c")

    def do_scan():
        if scan_state['running']:
            return
        scan_state['running'] = True
        scan_state['result'] = None
        err.configure(text="Scanning the network for the server ...", fg="#f0b232")
        try:
            btn_scan.configure(state=tk.DISABLED)
        except Exception:
            pass
        threading.Thread(target=_scan_thread, daemon=True).start()
        ip_win.after(250, _poll_scan)

    bf = tk.Frame(ip_win, bg="#121212")
    bf.pack(pady=18)
    tk.Button(bf, text="Connect", bg="#25d366", fg="#0b1a0e", font=("Segoe UI", 11, "bold"),
              width=9, cursor="hand2", relief=tk.FLAT, bd=0, command=connect).pack(side=tk.LEFT, padx=5)
    tk.Button(bf, text="Test", bg="#2c2c2c", fg="#e9edef", font=("Segoe UI", 11, "bold"),
              width=7, cursor="hand2", relief=tk.FLAT, bd=0, command=test_conn).pack(side=tk.LEFT, padx=5)
    btn_scan = tk.Button(bf, text="Scan", bg="#2c2c2c", fg="#e9edef",
                         font=("Segoe UI", 11, "bold"), width=7, cursor="hand2",
                         relief=tk.FLAT, bd=0, command=do_scan)
    btn_scan.pack(side=tk.LEFT, padx=5)
    tk.Button(bf, text="Cancel", bg="#2c2c2c", fg="white", font=("Segoe UI", 11, "bold"),
              width=7, cursor="hand2", relief=tk.FLAT, bd=0, command=cancel).pack(side=tk.LEFT, padx=5)
    ip_win.bind('<Return>', lambda e: connect())
    ip_win.mainloop()
    return result["ip"], result["name"]


class ThemeManager:
    """WhatsApp Desktop theme manager (dark <-> light).

    The UI is written with dark-mode colour literals. Theme switching works by
    translating every colour option in the widget tree with one of the maps
    below, so a single click re-skins the entire app. Each map is injective and
    never maps to one of its own keys, so the switch is perfectly reversible.
    """

    def __init__(self):
        self.dark = {
            'bg_app': '#121212',
            'bg_sidebar': '#121212',
            'bg_middle': '#1e1e1e',
            'bg_right': '#121212',
            'bg_header': '#121212',
            'bg_chat_header': '#121212',
            'bg_input': '#1e1e1e',
            'bg_message_sent': '#25d366',
            'bg_message_received': '#1e1e1e',
            'fg_text': '#ffffff',
            'fg_secondary': '#bdc3c7',
            'fg_time': '#7f8c8d',
            'accent': '#25d366',
            'border': '#2c2c2c',
            'search_bg': '#2c2c2c',
            'search_fg': '#ffffff',
            'chip_active': '#25d366',
            'chip_inactive': '#2c2c2c',
            'chip_text_active': '#ffffff',
            'chip_text_inactive': '#bdc3c7',
            'empty_text': '#7f8c8d',
            'status_online': '#25d366',
            'status_offline': '#7f8c8d',
            'card_bg': '#1e1e1e',
            'hover_bg': '#2c2c2c',
            'input_bg': '#2c2c2c',
            'input_text': '#ffffff',
            'unread_bg': '#25d366',
            'unread_fg': '#ffffff',
        }
        self.current = self.dark.copy()
        self.name = 'Dark'

    def set_theme(self, theme_name):
        self.name = theme_name
        self.current = self.dark.copy()
        return self.current

    def get(self, key):
        return self.current.get(key, '#ffffff')

    def maps_for(self, target):
        """(bg_map, fg_map) that translate the *current* look to `target`."""
        if target == 'Light':
            return dict(BG_D2L), dict(FG_D2L)
        return dict(BG_L2D), dict(FG_L2D)


# ---- whole-app colour translation tables ----
# dark literal -> light literal (backgrounds / fills)
BG_D2L = {
    '#121212': '#e9eef2',   # app chrome, sidebar, chat backdrop
    '#1e1e1e': '#ffffff',   # panels, list rows, received bubbles
    '#2c2c2c': '#f0f2f5',   # cards, inputs, hover / active rows
    '#2a2a2a': '#dde3e8',   # separators
    '#3a3a3a': '#cfd8dd',
    '#3c3c3c': '#d1d7db',   # borders
    '#3b4a56': '#c3ccd2',
    '#2a3942': '#b9c4cc',
    '#202c33': '#fbfdff',   # notification card
    '#25d366': '#00a884',   # accent
    '#ffe97a': '#fff3b0',   # search highlight strip
    '#4a4a4a': '#c9d3d9',   # scrollbar thumb
    '#5f6d75': '#a9b6bd',   # scrollbar thumb (hover / drag)
}
# dark literal -> light literal (text / foregrounds)
FG_D2L = {
    '#e9edef': '#111b21',   # primary text
    '#aebac1': '#54656f',   # nav labels
    '#bdc3c7': '#5b6a73',
    '#7f8c8d': '#6f7f88',
    '#6b7780': '#7a8a93',
    '#667781': '#4a5c66',
    '#8696a0': '#54656f',   # secondary text, grey ticks
    '#25d366': '#00806a',   # green text / icons on white
    '#ff5c5c': '#d32f2f',
}
BG_L2D = {v: k for k, v in BG_D2L.items()}
FG_L2D = {v: k for k, v in FG_D2L.items()}


def _lum_str(color):
    """Perceived brightness (0..1) of a '#rrggbb' / named colour, else None."""
    if not isinstance(color, str):
        return None
    c = color.strip().lower()
    if c.startswith('#') and len(c) == 7:
        try:
            r = int(c[1:3], 16); g = int(c[3:5], 16); b = int(c[5:7], 16)
            return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        except Exception:
            return None
    return {'white': 1.0, 'black': 0.0}.get(c)

# widget option names, grouped by the role they play
_BG_OPTIONS = ('bg', 'background', 'activebackground', 'troughcolor',
               'highlightbackground', 'highlightcolor', 'selectbackground',
               'selectcolor')
_FG_OPTIONS = ('fg', 'foreground', 'activeforeground', 'disabledforeground',
               'insertbackground')


def _shade(hexcolor, f):
    """Lighten (f>0) or darken (f<0) a '#rrggbb' colour (for button hovers)."""
    try:
        c = hexcolor.lstrip('#')
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        if f >= 0:
            r = int(r + (255 - r) * f)
            g = int(g + (255 - g) * f)
            b = int(b + (255 - b) * f)
        else:
            r = int(r * (1 + f)); g = int(g * (1 + f)); b = int(b * (1 + f))
        return '#%02x%02x%02x' % (max(0, min(255, r)), max(0, min(255, g)),
                                  max(0, min(255, b)))
    except Exception:
        return hexcolor


class CallBtn(tk.Canvas):
    """A round, WhatsApp-style call control button (icon glyph on a circle)."""

    def __init__(self, parent, glyph, command, size=58, bg='#2a3942',
                 fg='#e9edef', icon_font=('Segoe UI', 22), rotation=0):
        super().__init__(parent, width=size, height=size, bg=parent.cget('bg'),
                         highlightthickness=0, bd=0, cursor='hand2')
        self.size = size
        self.glyph = glyph
        self.command = command
        self.bg = bg
        self.fg = fg
        self.icon_font = icon_font
        self.rotation = rotation
        self.slash = False
        self._draw()
        self.bind('<Button-1>', self._click)
        self.bind('<Enter>', lambda e=None: self._draw(hover=True))
        self.bind('<Leave>', lambda e=None: self._draw())

    def _click(self, _e=None):
        if self.command:
            try:
                self.command()
            except Exception:
                pass

    def restyle(self, bg=None, fg=None, slash=None):
        if bg is not None:
            self.bg = bg
        if fg is not None:
            self.fg = fg
        if slash is not None:
            self.slash = slash
        self._draw()

    def _draw(self, hover=False):
        self.delete('all')
        s = self.size
        bg = _shade(self.bg, 0.12) if hover else self.bg
        self.create_oval(0, 0, s, s, fill=bg, outline='')
        self.create_text(s / 2, s / 2, text=self.glyph, fill=self.fg,
                         font=self.icon_font, angle=self.rotation)
        if self.slash:
            self.create_line(s * 0.26, s * 0.28, s * 0.74, s * 0.72,
                             fill='#ff6b6b', width=3, capstyle=tk.ROUND)


__all__ = [
    "APP_DIR",
    "BG_D2L",
    "BG_L2D",
    "CV2_OK",
    "CallBtn",
    "FG_D2L",
    "FG_L2D",
    "FILE_APP_LOGO",
    "FILE_KIND_LABEL",
    "ICON",
    "Image",
    "ImageDraw",
    "ImageTk",
    "ModernScrollbar",
    "Notifier",
    "PIL_OK",
    "PYAUDIO_OK",
    "PlaceholderEntry",
    "RINGTONE_DIR",
    "RingtonePlayer",
    "RoundedBox",
    "RoundedButton",
    "SESSION_FILE",
    "ThemeManager",
    "WindowsVolume",
    "_BG_OPTIONS",
    "_FG_OPTIONS",
    "_audioop",
    "_cv2",
    "_lum_str",
    "_np",
    "_pyaudio",
    "_rrect",
    "_shade",
    "array",
    "base64",
    "colorchooser",
    "ctypes",
    "datetime",
    "file_kind_of",
    "file_logo",
    "filedialog",
    "get_server_ip",
    "hashlib",
    "human_size",
    "io",
    "json",
    "load_local_session",
    "local_ipv4",
    "math",
    "messagebox",
    "mimetypes",
    "normalize_server",
    "os",
    "queue",
    "save_local_session",
    "scan_lan_for_server",
    "server_url_from",
    "simpledialog",
    "sio",
    "socket",
    "socketio",
    "struct",
    "sys",
    "threading",
    "time",
    "timedelta",
    "tk",
    "tkfont",
    "ttk",
    "uuid",
    "valid_ipv4",
    "warnings",
    "wave",
    "winsound",
]
