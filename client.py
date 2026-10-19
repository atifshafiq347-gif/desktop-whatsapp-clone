# client.py — WhatsApp-style LAN chat client (ENTRY POINT).
#
# The client is assembled from mixins that live in the client_*.py modules.
# Run it with:  py -3.12 client.py
from client_core import *
from client_calls import CallWindow, CallBtn, CallsMixin
from client_net import NetMixin
from client_ui import UiMixin
from client_chat import ChatMixin
from client_settings import SettingsMixin
from client_groups import GroupMixin
from client_menus import MenuMixin


class WhatsAppClient(MenuMixin, UiMixin, ChatMixin, NetMixin,
                     CallsMixin, SettingsMixin, GroupMixin):
    def __init__(self, root, server_url, username="You"):
        self.root = root
        self.root.title("WhatsApp")
        self.root.geometry("1350x780")
        self.root.configure(bg='#121212')
        self.server_url = server_url

        self.theme = ThemeManager()
        self.theme_name = 'Dark'
        self._theme_ready = False
        self.current_chat_id = None
        self.current_chat_name = None
        self.current_chat_type = None
        self.current_chat_color = None
        self.current_chat_avatar = None
        self.current_chat_sid = None
        self.current_chat_gid = None
        self.current_status = "active"
        self.my_username = username or "You"
        self.current_view = 'chats'
        self.volume = WindowsVolume()
        self.ringtone = RingtonePlayer(volume=100)    # built-in + custom notification sounds
        self.ringtone.set_label("Classic")
        self.ringtone_label = "Classic"
        self.custom_ringtone_path = ""
        self.call_ringtone = RingtonePlayer(
            folder=os.path.join(RINGTONE_DIR, "calls"),
            tones=RingtonePlayer.CALL_TONES, volume=100)
        self.call_ringtone.set_label("Ring Classic")
        self.call_ringtone_label = "Ring Classic"
        self.custom_call_ringtone_path = ""
        self.my_pic = ""                    # my profile photo (base64 PNG)
        self.my_color = "#25d366"           # my avatar colour
        self._pending_chat_name = ""        # chat to reopen after a session restore
        self._img_cache = {}                # (hash,size) -> PhotoImage
        self.call_log = []          # newest call first
        self._call = None           # the live CallWindow (voice / video), if any
        self.clients = []           # every connected client (from the server)
        self.my_sid = None          # this client's own sid
        self._peers = []            # contacts added to the middle list (real clients)
        self._peer_seq = 0
        self._client_total = -1     # to detect join/leave
        self.server_max = 50        # server-wide client limit (pushed by the server)
        self._bubble_labels = {}    # mid -> status label (delivery / read ticks)
        self._bubble_widgets = {}   # mid -> bubble frame (used by reply jumps)
        self._bubble_rects = {}     # mid -> (canvas, rounded-rect items) for flashing
        # in-chat search (right panel header 🔍): every message stays visible,
        # the matches are highlighted and navigated with the ▲ / ▼ buttons
        self._search_q = ""         # current query, lower-cased
        self.chat_matches = []      # mids that match, in reading order
        self.chat_idx = -1          # index of the focused match
        self.chat_focus = None      # mid of the focused match
        self._pending_file = None   # attachment waiting in the in-panel preview
        self._file_cache = {}       # mid -> local path of a saved attachment
        self.time_24h = True        # 12-hour vs 24-hour clock (Settings)
        # voice recorder state
        self.REC_RATE = 16000
        self.REC_CHUNK = 1024
        self._recording = False
        self._rec_frames = []
        self._rec_levels = []
        self._rec_job = None
        self.reply_to = None        # message being replied to
        self.pinned = {}            # chat_id -> mid of pinned message
        self.history_period = 'All'  # history date filter for the open chat
        self.muted_chats = set()     # chat ids whose notifications are muted
        self.blocked = set()         # usernames I blocked (client-side mirror)
        self.blocked_meta = []       # [{peer, blocked_at}] from the server
        self._activity_seq = 0       # bumps on every message -> recency order
        self._joined = False         # True once the server accepted our 'join'
        self._join_retry_on = False  # waiting for the other session to log out

        self.setup_ui()
        self._install_click_outside()
        self.notifier = Notifier(self)
        self.connect_to_server()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        # Warn (once, after the UI is up) when the machine is missing the
        # packages video/voice calls need - this is the usual reason a camera
        # "does not open" or the other side cannot be seen/heard.
        self.root.after(1800, self._media_dep_check)

    # ============================================================
    # CHAT LIST (Middle panel)
    # ============================================================
    # ---- reply quote (WhatsApp-style block: click it to jump to the original) ----
    QUOTE_FONT = ("Segoe UI", 9)
    QUOTE_NAME = ("Segoe UI", 10, "bold")

    # ============================================================
    # MESSAGE ACTIONS (reply / forward / copy / pin / delete)
    # ============================================================
    # ---- right-click message menu (real-WhatsApp style) ----
    REACT_EMOJIS = ["\U0001F44D", "\u2764\ufe0f", "\U0001F602",
                    "\U0001F62E", "\U0001F622", "\U0001F64F"]

    def on_closing(self):
        try:
            self._call_end_all()
        except Exception:
            pass
        try:
            if sio.connected:
                sio.emit('leave', {'username': self.my_username})
        except Exception:
            pass
        try:
            sio.disconnect()
        except:
            pass
        self.root.destroy()

def main():
    ip, name = get_server_ip()
    if ip is None:
        return
    url = server_url_from(ip)
    root = tk.Tk()
    WhatsAppClient(root, url, name)
    root.mainloop()


if __name__ == '__main__':
    main()
