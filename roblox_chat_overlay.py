#TODO: add config file, settings in ui

import sys
import threading
import json

from queue import Queue, Empty

from irc.client import SimpleIRCClient, ServerConnectionError

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QSizeGrip,
    QStackedLayout
)

import log_watcher.roblox_server_join_watcher as roblox_server_join_watcher

with open("config.json", "r", encoding="utf-8") as file:
    config = json.load(file)


nickname = config["irc"]["nickname"]
irc_server = config["irc"]["server"]
irc_port = config["irc"]["port"]
raw_irc_messages = config["irc"]["raw_irc_messages"]

ui_event_queue = Queue()
irc_control_queue = Queue()
roblox_event_queue = Queue()



class OverlayIRCClient(SimpleIRCClient):
    
    def __init__(self, ui_event_queue: Queue, control_queue: Queue,
                 nickname, server, port):
        super().__init__()
        self.ui_event_queue = ui_event_queue
        self.control_queue = control_queue
        self.nickname = nickname
        self.server = server
        self.port = port
        self.current_channel = None
        self._running = True

    def connect_and_run(self):
        try:
            self.connect(self.server, self.port, self.nickname)
            self.ui_event_queue.put(("system", f"Connecting to {irc_server} on {irc_port}"))
        except ServerConnectionError as e:
            self.ui_event_queue.put(("system", f"IRC connect failed: {e}"))
            return

        threading.Thread(target=self._process_control_loop, daemon=True).start()

        self.reactor.process_forever()

    def _process_control_loop(self):
        while self._running:
            try:
                cmd, data = self.control_queue.get(timeout=0.2)
            except Empty:
                continue

            if cmd == "join_channel":
                channel = data
                if self.current_channel and self.current_channel != channel:
                    try:
                        self.connection.part(self.current_channel)
                    except Exception:
                        pass
                self.current_channel = channel
                self.connection.join(channel)
                self.ui_event_queue.put(("system", f"Joined IRC channel {channel}"))

            elif cmd == "disconnect":
                if self.current_channel:
                    try:
                        self.connection.part(self.current_channel)
                    except Exception:
                        pass
                    self.ui_event_queue.put(("system", f"Left IRC channel {self.current_channel}"))
                self.current_channel = None

            elif cmd == "send_message":
                msg = data
                if self.current_channel:
                    try:
                        self.connection.privmsg(self.current_channel, msg)
                    except Exception as e:
                        self.ui_event_queue.put(("system", f"Failed to send: {e}"))

            elif cmd == "stop":
                self._running = False
                try:
                    self.connection.quit("Overlay closing")
                except Exception:
                    pass
                break

    def on_welcome(self, connection, event):
        self.ui_event_queue.put(("system", f"Connected to IRC server: {self.server}"))

    def on_join(self, connection, event):
        nick = event.source.nick
        channel = event.target
        if nick == self.nickname:
            return
        self.ui_event_queue.put(("system", f"{nick} joined {channel}"))
    
    def on_part(self, connection, event):
        nick = event.source.nick
        channel = event.target
        if nick == self.nickname:
            return
        self.ui_event_queue.put(("system", f"{nick} left {channel}"))
 
    def on_disconnect(self, connection, event):
        self.ui_event_queue.put(("system", "Disconnected from IRC server"))

    def on_pubmsg(self, connection, event):
        nick = event.source.split("!")[0] if "!" in event.source else event.source
        msg = event.arguments[0]
        self.ui_event_queue.put(("chat", f"<{nick}> {msg}"))

    def on_privmsg(self, connection, event):
        nick = event.source.split("!")[0] if "!" in event.source else event.source
        msg = event.arguments[0]
        self.ui_event_queue.put(("chat", f"[PM from {nick}] {msg}"))

    def on_nicknameinuse(self, connection, event):
        newnick = self.nickname + "_"
        self.ui_event_queue.put(("system", f"Nickname '{self.nickname}' in use, trying '{newnick}'"))
        self.nickname = newnick
        connection.nick(newnick)
    
    def on_all_raw_messages(self, connection, event):
        if raw_irc_messages == True:
            print(event.arguments)
            self.ui_event_queue.put(("system", f"{event.arguments}"))


class GrabBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            # move the window to follow the mouse
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

class ChatOverlay(QWidget):
    def __init__(self, ui_event_queue: Queue, irc_control_queue: Queue, parent=None):
        super().__init__(parent)
        self.ui_event_queue = ui_event_queue
        self.irc_control_queue = irc_control_queue

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
            )
        self.setAttribute(Qt.WA_TranslucentBackground)

        screen = QGuiApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.35)
        height = int(screen.height() * 0.35)
        self.setGeometry(20, screen.height() - height - 80, width, height)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)


        self.main_window = QWidget()
        self.main_window.setStyleSheet("""
            QWidget {
                background: rgba(10, 10, 20, 120);
                border-radius: 8px;
                padding: 6px;
            }
        """)

        self.main_window_layout = QVBoxLayout(self.main_window)
        self.main_window_layout.setContentsMargins(0, 0, 0, 0)
        self.main_window_layout.setAlignment(Qt.AlignTop)



        self.top_bar = GrabBar()
        
        self.top_bar_layout = QHBoxLayout(self.top_bar)
        self.top_bar_layout.setContentsMargins(4, 4, 4, 4)
        self.top_bar_layout.setAlignment(Qt.AlignRight)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(10, 10, 20, 230);
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                color: black;
            }
        """)
        self.close_btn.clicked.connect(QApplication.quit)
        self.top_bar_layout.addWidget(self.close_btn)

        self.main_window_layout.addWidget(self.top_bar)


        self.chat_window = QWidget()
        self.chat_window.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 0);
            }
        """)
        self.bottom_half_layout = QHBoxLayout(self.chat_window)
        self.bottom_half_layout.setContentsMargins(0, 0, 0, 0)



        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet("""
            QTextEdit {
                background: rgba(0, 0, 0, 0);
                color: #ffffff;
                font-size: 12px;
            }
        """)
        font = QFont("Consolas")
        font.setPointSize(10)
        self.chat_view.setFont(font)

        self.bottom_half_layout.addWidget(self.chat_view)



        self.right_side_bar = QWidget()
        self.right_side_bar.setStyleSheet("""
            QWidget {
                background: rgba(0, 0, 0, 0);
            }
        """)
        self.right_side_bar_layout = QVBoxLayout(self.right_side_bar)
        self.right_side_bar_layout.setContentsMargins(0, 0, 2, 2)
        self.right_side_bar_layout.setAlignment(Qt.AlignBottom | Qt.AlignRight)
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("""
            QWidget {
                background: rgba(10, 10, 20, 120);
            }
        """)
        self.right_side_bar_layout.addWidget(self.size_grip, alignment=Qt.AlignRight)

        self.bottom_half_layout.addWidget(self.right_side_bar)



        self.main_window_layout.addWidget(self.chat_window)

        layout.addWidget(self.main_window)
        self.setLayout(layout)



        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Press Enter to start typing")
        self.input_box.setStyleSheet("""
            QLineEdit {
                background: rgba(20, 20, 30, 200);
                color: #ffffff;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                border: 1px solid #555555;
            }
            QLineEdit:focus {
                border: 1px solid #8888ff;
            }
        """)

        layout.addWidget(self.input_box)
        self.setLayout(layout)



        self.timer = QTimer(self)
        self.timer.timeout.connect(self._process_ui_events)
        self.timer.start(50)

        self.current_job_id = None



    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.input_box.hasFocus():
                self.submit_text()
                self.input_box.clearFocus()
            else:
                self.input_box.setFocus()
        else:
            super().keyPressEvent(event)

    def submit_text(self):
        text = self.input_box.text().strip()
        if not text:
            return
        self.input_box.clear()
        self._append_chat_line(f"<you> {text}")
        self.irc_control_queue.put(("send_message", text))

    def _process_ui_events(self):
        while True:
            try:
                kind, payload = self.ui_event_queue.get_nowait()
            except Empty:
                break

            if kind == "chat":
                self._append_chat_line(payload)
            elif kind == "system":
                self._append_system_line(payload)
            elif kind == "join_display":
                self._append_system_line(f"Joined Roblox server: {payload}")
            elif kind == "disconnect_display":
                self._append_system_line(f"Disconnected from Roblox server: {payload}")

    def _append_chat_line(self, text: str):
        self.chat_view.append(text)
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    def _append_system_line(self, text: str):
        self.chat_view.append(f"<span style='color:#77aaff;'>[SYSTEM]</span> {text}")
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    def handle_roblox_join(self, job_id: str):
        self.current_job_id = job_id
        channel = f"#roblox_{job_id.replace('-', '')[:20]}"
        self.irc_control_queue.put(("join_channel", channel))
        self.ui_event_queue.put(("join_display", job_id))

    def handle_roblox_disconnect(self):
        if self.current_job_id == None:
            return
        self.irc_control_queue.put(("disconnect", None))
        self.ui_event_queue.put(("disconnect_display", self.current_job_id))
        self.current_job_id = None


def set_roblox_server_id(roblox_server_id):
    roblox_event_queue.put(("joined", roblox_server_id))

def disconnect_roblox_server():
    roblox_event_queue.put(("disconnected", None))

def main():
    join_watcher_thread = threading.Thread(target=roblox_server_join_watcher.run_observer, 
                                            args=(set_roblox_server_id, disconnect_roblox_server), 
                                            daemon=True)
    join_watcher_thread.start()
    
    irc_client = OverlayIRCClient(
        ui_event_queue,
        irc_control_queue,
        nickname=nickname,
        server=irc_server,
        port=irc_port,
    )
    irc_thread = threading.Thread(target=irc_client.connect_and_run, daemon=True)
    irc_thread.start()

    app = QApplication(sys.argv)
    overlay = ChatOverlay(ui_event_queue, irc_control_queue)
    overlay.show()

    def process_roblox_events():
        while True:
            try:
                kind, payload = roblox_event_queue.get_nowait()
            except Empty:
                break

            if kind == "joined":
                overlay.handle_roblox_join(payload)
            elif kind == "disconnected":
                overlay.handle_roblox_disconnect()
            elif kind == "info":
                ui_event_queue.put(("system", payload))

    roblox_timer = QTimer()
    roblox_timer.timeout.connect(process_roblox_events)
    roblox_timer.start(100)

    try:
        sys.exit(app.exec())
    finally:
        irc_control_queue.put(("stop", None))


if __name__ == "__main__":
    main()