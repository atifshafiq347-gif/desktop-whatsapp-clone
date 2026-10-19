# server.py — LAN chat server (ENTRY POINT).
#
# The server is assembled from server_*.py modules:
#   server_core.py      - config + shared state + cache loader + Flask/SocketIO
#   server_db.py        - SQLite persistence
#   server_events.py    - Socket.IO event handlers
#   server_dashboard.py - the Tk control-room dashboard
#
# Run it with:  py -3.12 server.py
from server_core import *
from server_db import *
from server_events import *
from server_dashboard import *




if __name__ == '__main__':
    root = tk.Tk()
    ServerApp(root)
    root.mainloop()
