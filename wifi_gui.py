#!/usr/bin/env python3
"""Modern PyQt5 Wi-Fi manager UI for Jetson Nano (1080x1920 portrait)."""

import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


@dataclass
class WifiNetwork:
    ssid: str
    signal: int
    secure: bool
    active: bool


class NetworkManagerCLI:
    """Thin wrapper around nmcli."""

    @staticmethod
    def _run_full(cmd: str) -> Tuple[int, str]:
        try:
            result = subprocess.run(
                shlex.split(cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=18,
            )
            return result.returncode, (result.stdout or '').strip()
        except Exception as exc:  # fallback for system issues
            return 1, str(exc)

    def _run(self, cmd: str) -> str:
        return self._run_full(cmd)[1]

    def wifi_enabled(self) -> bool:
        out = self._run("nmcli radio wifi")
        return out.lower() == "enabled"

    def set_wifi(self, enabled: bool) -> str:
        state = "on" if enabled else "off"
        return self._run(f"nmcli radio wifi {state}")

    def scan_networks(self) -> List[WifiNetwork]:
        self._run("nmcli device wifi rescan")
        raw = self._run("nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY device wifi list")
        networks: List[WifiNetwork] = []
        seen = set()
        for line in raw.splitlines():
            if not line.strip():
                continue
            fields = line.split(":")
            if len(fields) < 4:
                continue
            in_use, ssid, signal, security = fields[0], fields[1], fields[2], ":".join(fields[3:])
            ssid = ssid.strip() or "<Hidden Network>"
            if ssid in seen:
                continue
            seen.add(ssid)
            networks.append(
                WifiNetwork(
                    ssid=ssid,
                    signal=int(signal) if signal.isdigit() else 0,
                    secure=security.strip() not in ("", "--"),
                    active=in_use.strip() == "*",
                )
            )
        return sorted(networks, key=lambda n: (not n.active, -n.signal, n.ssid.lower()))

    def saved_networks(self) -> List[str]:
        raw = self._run("nmcli -t -f NAME,TYPE connection show")
        result = []
        for line in raw.splitlines():
            try:
                name, conn_type = line.split(":", 1)
            except ValueError:
                continue
            if conn_type.strip() == "802-11-wireless":
                result.append(name)
        return sorted(set(result), key=str.lower)

    def connected_network(self) -> Optional[str]:
        raw = self._run("nmcli -t -f ACTIVE,SSID device wifi")
        for line in raw.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1]
        return None

    def connect(self, ssid: str, password: str = "") -> Tuple[bool, str, str]:
        cmd = (
            f"nmcli device wifi connect {shlex.quote(ssid)} password {shlex.quote(password)}"
            if password
            else f"nmcli connection up {shlex.quote(ssid)}"
        )
        code, out = self._run_full(cmd)
        low = out.lower()

        if code == 0:
            return True, out or "Connected successfully.", ""

        wrong_password_patterns = [
            "secrets were required",
            "invalid wifi password",
            "wrong password",
            "802-11-wireless-security.psk",
            "activation: failed",
            "ssid not found",
        ]
        if any(p in low for p in wrong_password_patterns):
            return False, out, "wrong_password"

        return False, out, "connection_error"

    def forget(self, name: str) -> str:
        return self._run(f"nmcli connection delete {shlex.quote(name)}")


class OnScreenKeyboardDialog(QDialog):
    def __init__(self, parent=None, title: str = "Enter Password"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(940, 760)

        self.shift_on = False
        self.symbol_mode = False
        self.alpha_rows = [
            list("qwertyuiop"),
            list("asdfghjkl"),
            list("zxcvbnm"),
        ]
        self.symbol_rows = [
            list("1234567890"),
            ["-", "/", ":", ";", "(", ")", "$", "&", "@", '"'],
            [".", ",", "?", "!", "'", "#", "%", "*", "+", "="],
        ]
        self.shift_pairs = {
            "1": "[", "2": "]", "3": "{", "4": "}", "5": "#",
            "6": "%", "7": "^", "8": "*", "9": "+", "0": "=",
            "-": "_", "/": "\\", ":": "|", ";": "~", "(": "<", ")": ">",
            "$": "€", "&": "£", "@": "§", '"': "`",
            ".": "…", ",": "_", "?": "¿", "!": "¡", "'": '"',
            "#": "№", "%": "‰", "*": "×", "+": "÷", "=": "≈",
        }
        self.char_buttons = []

        main = QVBoxLayout(self)
        self.input_field = QLineEdit()
        self.input_field.setEchoMode(QLineEdit.Password)
        self.input_field.setPlaceholderText("Type Wi-Fi password")
        self.input_field.setMinimumHeight(66)
        self.input_field.setObjectName("PasswordField")
        main.addWidget(self.input_field)

        kb_shell = QFrame()
        kb_shell.setObjectName("KeyboardShell")
        kb_layout = QVBoxLayout(kb_shell)
        kb_layout.setSpacing(8)
        kb_layout.setContentsMargins(12, 14, 12, 14)

        for _ in range(3):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)
            kb_layout.addLayout(row_layout)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.shift_button = self._action_key("⇧", self._toggle_shift, width=90)
        self.backspace_button = self._action_key("⌫", self.input_field.backspace, width=90)
        row3.addWidget(self.shift_button)
        self.row3_chars = QHBoxLayout()
        self.row3_chars.setSpacing(8)
        row3.addLayout(self.row3_chars)
        row3.addWidget(self.backspace_button)
        kb_layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.setSpacing(8)
        self.mode_button = self._action_key("123", self._toggle_mode, width=110)
        row4.addWidget(self.mode_button)
        self.hide_button = self._action_key("🔒", self._toggle_echo, width=90)
        row4.addWidget(self.hide_button)

        self.space_button = self._key_button("Space", width=360)
        self.space_button.clicked.connect(lambda: self.input_field.insert(" "))
        row4.addWidget(self.space_button)

        self.clear_button = self._action_key("Clear", self.input_field.clear, width=110)
        row4.addWidget(self.clear_button)
        self.connect_button = self._action_key("Connect", self.accept, width=150, primary=True)
        row4.addWidget(self.connect_button)
        kb_layout.addLayout(row4)

        main.addWidget(kb_shell)

        footer = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("FooterButton")
        cancel.clicked.connect(self.reject)
        footer.addStretch()
        footer.addWidget(cancel)
        main.addLayout(footer)

        self._apply_keyboard_style()
        self._rebuild_keys()

    def _apply_keyboard_style(self):
        self.setStyleSheet(
            """
            QDialog {
                background: #eef2ff;
                font-family: 'Roboto';
            }
            QFrame#KeyboardShell {
                background: #e2e8f0;
                border-radius: 18px;
                border: 1px solid #cbd5e1;
            }
            QLineEdit#PasswordField {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 16px;
                padding: 10px 14px;
                font-size: 22px;
                font-weight: 500;
                color: #111827;
            }
            QPushButton {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                font-size: 18px;
                font-weight: 400;
            }
            QPushButton:hover { background: #f9fafb; }
            QPushButton:pressed { background: #e5e7eb; }
            QPushButton#ActionKey {
                background: #b6bac5;
                font-size: 17px;
                font-weight: 400;
            }
            QPushButton#PrimaryKey {
                background: #0a84ff;
                color: #ffffff;
                border: 1px solid #0a75de;
                font-size: 17px;
                font-weight: 400;
            }
            QPushButton#FooterButton {
                background: transparent;
                border: none;
                color: #0a84ff;
                font-size: 18px;
                font-weight: 500;
            }
            """
        )

    def _key_button(self, label: str, width: Optional[int] = None) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(64)
        if width is None:
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumWidth(48)
        else:
            btn.setFixedWidth(width)
        return btn

    def _action_key(self, label: str, handler, width: int = 96, primary: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("PrimaryKey" if primary else "ActionKey")
        btn.setFixedWidth(width)
        btn.setFixedHeight(64)
        btn.clicked.connect(handler)
        return btn

    def _clear_layout(self, layout: QHBoxLayout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _rebuild_keys(self):
        kb_shell = self.findChild(QFrame, "KeyboardShell")
        rows = kb_shell.layout()
        for row_idx in range(3):
            row_layout = rows.itemAt(row_idx).layout()
            self._clear_layout(row_layout)

        self._clear_layout(self.row3_chars)
        self.char_buttons = []

        source_rows = self.symbol_rows if self.symbol_mode else self.alpha_rows
        row_offsets = [0, 24, 48]

        for row_idx in range(2):
            row_layout = rows.itemAt(row_idx).layout()
            row_layout.addSpacing(row_offsets[row_idx])
            for ch in source_rows[row_idx]:
                self._add_char_key(row_layout, ch)

        self.row3_chars.addSpacing(row_offsets[2])
        for ch in source_rows[2]:
            self._add_char_key(self.row3_chars, ch)

        self.mode_button.setText("ABC" if self.symbol_mode else "123")
        self.shift_button.setText("Caps" if self.shift_on else "⇧")
        self._refresh_key_labels()

    def _add_char_key(self, layout: QHBoxLayout, value: str):
        btn = self._key_button(value)
        btn.clicked.connect(lambda _, v=value: self._type_character(v))
        btn.base_value = value
        self.char_buttons.append(btn)
        layout.addWidget(btn)

    def _refresh_key_labels(self):
        for btn in self.char_buttons:
            value = btn.base_value
            if not self.symbol_mode and value.isalpha():
                btn.setText(value.upper() if self.shift_on else value.lower())
            elif self.symbol_mode and self.shift_on and value in self.shift_pairs:
                btn.setText(self.shift_pairs[value])
            else:
                btn.setText(value)

    def _toggle_shift(self):
        self.shift_on = not self.shift_on
        self.shift_button.setText("Caps" if self.shift_on else "⇧")
        self._refresh_key_labels()

    def _toggle_mode(self):
        self.symbol_mode = not self.symbol_mode
        self.shift_on = False
        self._rebuild_keys()

    def _toggle_echo(self):
        mode = self.input_field.echoMode()
        is_password = mode == QLineEdit.Password
        self.input_field.setEchoMode(QLineEdit.Normal if is_password else QLineEdit.Password)
        self.hide_button.setText("🙈" if is_password else "🔒")

    def _type_character(self, key: str):
        if not self.symbol_mode and key.isalpha():
            self.input_field.insert(key.upper() if self.shift_on else key.lower())
            if self.shift_on:
                self.shift_on = False
                self.shift_button.setText("⇧")
                self._refresh_key_labels()
            return

        if self.symbol_mode and self.shift_on and key in self.shift_pairs:
            self.input_field.insert(self.shift_pairs[key])
        else:
            self.input_field.insert(key)

    def password(self) -> str:
        return self.input_field.text()


class WifiCard(QFrame):
    def __init__(self, network: WifiNetwork, connect_cb):
        super().__init__()
        self.setObjectName("WifiCard")
        layout = QHBoxLayout(self)

        details = QVBoxLayout()
        name = QLabel(network.ssid)
        name.setObjectName("Title")
        status_bits = [f"Signal: {network.signal}%"]
        status_bits.append("Secured" if network.secure else "Open")
        if network.active:
            status_bits.append("Connected")
        info = QLabel("  •  ".join(status_bits))
        info.setObjectName("Subtle")
        details.addWidget(name)
        details.addWidget(info)

        connect_btn = QPushButton("Connected" if network.active else "Connect")
        connect_btn.setEnabled(not network.active)
        connect_btn.clicked.connect(lambda: connect_cb(network))

        layout.addLayout(details)
        layout.addStretch()
        layout.addWidget(connect_btn)


class WifiMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jetson Wi-Fi Manager")
        self.setMinimumSize(1080, 1920)
        self.nm = NetworkManagerCLI()

        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)

        header = QHBoxLayout()
        title = QLabel("Wi-Fi Settings")
        title.setObjectName("Header")
        self.connection_label = QLabel("Status: checking...")
        self.connection_label.setObjectName("Subtle")

        self.toggle_button = QPushButton("Turn Wi-Fi Off")
        self.toggle_button.clicked.connect(self.toggle_wifi)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_all)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.connection_label)
        header.addWidget(self.toggle_button)
        header.addWidget(refresh)
        main.addLayout(header)

        self.body = QStackedWidget()
        main.addWidget(self.body)

        self.networks_page = self._build_networks_page()
        self.saved_page = self._build_saved_page()

        self.body.addWidget(self.networks_page)
        self.body.addWidget(self.saved_page)

        nav = QHBoxLayout()
        scan_btn = QPushButton("Available Networks")
        saved_btn = QPushButton("Saved Networks")
        scan_btn.clicked.connect(lambda: self.body.setCurrentWidget(self.networks_page))
        saved_btn.clicked.connect(lambda: self.body.setCurrentWidget(self.saved_page))
        nav.addWidget(scan_btn)
        nav.addWidget(saved_btn)
        main.addLayout(nav)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(10000)

        self._apply_styles()
        self.refresh_all()

    def _build_networks_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.networks_scroll = QScrollArea()
        self.networks_scroll.setWidgetResizable(True)
        self.networks_container = QWidget()
        self.networks_layout = QVBoxLayout(self.networks_container)
        self.networks_layout.addStretch()
        self.networks_scroll.setWidget(self.networks_container)
        layout.addWidget(self.networks_scroll)
        return page

    def _build_saved_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.saved_list = QListWidget()
        forget = QPushButton("Forget Selected Network")
        forget.clicked.connect(self.forget_selected)
        layout.addWidget(self.saved_list)
        layout.addWidget(forget)
        return page

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #f1f5f9;
                color: #0f172a;
                font-family: 'Roboto';
                font-size: 20px;
            }
            QLabel#Header {
                font-size: 40px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#Title {font-size: 30px; font-weight: 600; color: #0f172a;}
            QLabel#Subtle {color: #64748b; font-size: 18px;}
            QPushButton {
                background-color: #1d4ed8;
                color: #ffffff;
                border: none;
                border-radius: 16px;
                padding: 14px 20px;
                font-weight: 600;
            }
            QPushButton:disabled {
                background-color: #cbd5e1;
                color: #64748b;
            }
            QPushButton:hover:!disabled {
                background-color: #2563eb;
            }
            QFrame#WifiCard {
                background-color: #ffffff;
                border: 1px solid #d6e0ea;
                border-radius: 18px;
                padding: 10px;
                margin: 6px;
            }
            QListWidget, QLineEdit, QScrollArea {
                background: #ffffff;
                border: 1px solid #d6e0ea;
                border-radius: 12px;
                padding: 8px;
            }
            """
        )

    def refresh_status(self):
        enabled = self.nm.wifi_enabled()
        self.toggle_button.setText("Turn Wi-Fi Off" if enabled else "Turn Wi-Fi On")
        connected = self.nm.connected_network()
        self.connection_label.setText(f"Connected: {connected}" if connected else "Not connected")

    def refresh_networks(self):
        while self.networks_layout.count() > 1:
            item = self.networks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for network in self.nm.scan_networks():
            self.networks_layout.insertWidget(
                self.networks_layout.count() - 1,
                WifiCard(network, self.connect_to_network),
            )

    def refresh_saved(self):
        self.saved_list.clear()
        for name in self.nm.saved_networks():
            self.saved_list.addItem(QListWidgetItem(name))

    def refresh_all(self):
        self.refresh_status()
        self.refresh_networks()
        self.refresh_saved()

    def toggle_wifi(self):
        enabled = self.nm.wifi_enabled()
        self.nm.set_wifi(not enabled)
        self.refresh_all()

    def connect_to_network(self, network: WifiNetwork):
        password = ""
        if network.secure:
            dlg = OnScreenKeyboardDialog(self, title=f"Connect to {network.ssid}")
            if dlg.exec_() != QDialog.Accepted:
                return
            password = dlg.password()

        self.connection_label.setText(f"Connecting to {network.ssid}...")
        self.toggle_button.setEnabled(False)
        QApplication.processEvents()

        try:
            ok, out, error_type = self.nm.connect(network.ssid, password)
        except Exception as exc:
            ok, out, error_type = False, str(exc), "connection_error"

        self.toggle_button.setEnabled(True)

        if ok:
            QMessageBox.information(self, "Connected", out or f"Connected to {network.ssid}.")
        elif error_type == "wrong_password":
            QMessageBox.warning(
                self,
                "Wrong Password",
                "Wrong password. Please check your Wi-Fi password and try again."
                f"\n\nDetails: {out or 'Authentication failed.'}",
            )
        else:
            QMessageBox.critical(
                self,
                "Connection Failed",
                f"Could not connect to '{network.ssid}'.\n\nDetails: {out or 'Unknown error.'}",
            )

        self.refresh_all()

    def forget_selected(self):
        item = self.saved_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Please select a saved network first.")
            return

        name = item.text()
        if QMessageBox.question(self, "Confirm Forget", f"Forget network '{name}'?") != QMessageBox.Yes:
            return

        out = self.nm.forget(name)
        QMessageBox.information(self, "Forget Result", out or "Done")
        self.refresh_all()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Roboto", 16))
    win = WifiMainWindow()
    win.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
