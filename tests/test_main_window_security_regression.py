"""PR4 security non-regression tests for MainWindow behaviors."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

from src.models.secret_types import SECRET_TYPE_API_TOKEN, SECRET_TYPE_SSH_KEY
from src.ui.windows.main_window import PasswordManagerWindow


class FakeLabel:
    def __init__(self, label: str = "") -> None:
        self.label = label
        self.visible = True

    def set_label(self, value: str) -> None:
        self.label = value

    def set_visible(self, visible: bool) -> None:
        self.visible = visible


class FakePasswordRow:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def set_text(self, text: str) -> None:
        self.text = text


class _Action:
    pass


def test_copy_autoclear_uses_same_30s_timer_for_api_and_ssh(monkeypatch) -> None:
    window = cast(Any, PasswordManagerWindow.__new__(PasswordManagerWindow))

    timeout_seconds: list[int] = []
    removed_ids: list[int] = []

    monkeypatch.setattr(
        "src.ui.windows.main_window.GLib.timeout_add_seconds",
        lambda seconds, _callback: (timeout_seconds.append(int(seconds)) or len(timeout_seconds)),
    )
    monkeypatch.setattr(
        "src.ui.windows.main_window.GLib.source_remove",
        lambda source_id: removed_ids.append(int(source_id)),
    )

    copied_messages: list[str] = []
    window.copy_to_clipboard = (
        lambda _text, message="": (
            copied_messages.append(message),
            window._schedule_clipboard_clear(),
        )
    )
    window._clipboard_token = 0
    window._clipboard_clear_source_id = None

    window.current_sort_mode = "modified_desc"
    window.current_entry_id = -1_000_007
    window._from_secret_ui_id = lambda _ui_id: 7
    window._refresh_secret_usage_after_access = lambda _ui_id: None
    window.load_entries = lambda: None
    window.show_toast = lambda _message: None

    window.secret_service = MagicMock()
    window.secret_service.reveal_api_token.return_value = "api-token"
    window.secret_service.reveal_ssh_private_key.return_value = "ssh-private-key"

    window.current_secret_type_filter = SECRET_TYPE_API_TOKEN
    window._on_copy_password_clicked(MagicMock())

    window.current_secret_type_filter = SECRET_TYPE_SSH_KEY
    window._on_copy_password_clicked(MagicMock())

    assert timeout_seconds == [30, 30]
    assert removed_ids == [1]
    assert copied_messages == ["API token copied", "SSH private key copied"]


def test_panic_purge_with_open_ssh_item_clears_sensitive_state(monkeypatch) -> None:
    window = cast(Any, PasswordManagerWindow.__new__(PasswordManagerWindow))

    removed_ids: list[int] = []
    monkeypatch.setattr(
        "src.ui.windows.main_window.GLib.source_remove",
        lambda source_id: removed_ids.append(int(source_id)),
    )

    window._clipboard_clear_source_id = 11
    window._clipboard_token = 5
    window._ssh_reveal_source_id = 22

    window.current_detail_mode = SECRET_TYPE_SSH_KEY
    window.detail_ssh_reveal_label = FakeLabel("-----BEGIN OPENSSH PRIVATE KEY-----")
    window.detail_password_row = FakePasswordRow("Revealed below for 30s")

    state = {
        "clipboard_cleared": False,
        "detail_cleared": False,
        "detail_sensitive": None,
        "flowbox_cleared": False,
    }
    window._clear_clipboard_now = lambda: state.__setitem__("clipboard_cleared", True)
    window._clear_detail = lambda: state.__setitem__("detail_cleared", True)
    window._set_detail_sensitive = lambda enabled: state.__setitem__("detail_sensitive", enabled)
    window._clear_flowbox = lambda _flow: state.__setitem__("flowbox_cleared", True)

    window.current_entry_id = -1_000_042
    window.current_search_text = "ssh"
    window.current_tag_filter = "infra"
    window.current_security_filter = "expiring"
    window._detail_dirty = True

    window._entry_by_child = {"k": "v"}
    window._entry_child_by_id = {1: "child"}
    window._entry_card_by_id = {1: "card"}
    window.entry_flowbox = object()

    window.password_service = MagicMock()

    app = MagicMock()
    app.vault_service = MagicMock()
    app.password_service = object()
    app.repository = object()
    app.secret_service = object()
    app.secret_repository = object()
    app.crypto_service = object()
    app._session_master_password = "MASTER-SECRET"
    app.current_vault = object()
    app.current_user = object()
    app.current_db_path = "demo.db"
    window.app = app

    window._panic_purge_memory_state()

    assert removed_ids == [11, 22]
    assert window._clipboard_token == 6
    assert state["clipboard_cleared"] is True

    assert window.detail_ssh_reveal_label.label == ""
    assert window.detail_ssh_reveal_label.visible is False
    assert window.detail_password_row.text == "••••••••"

    assert state["detail_cleared"] is True
    assert state["detail_sensitive"] is False
    assert state["flowbox_cleared"] is True

    assert window.current_entry_id is None
    assert window.current_search_text == ""
    assert window.current_tag_filter is None
    assert window.current_security_filter is None
    assert window._detail_dirty is False

    assert window._entry_by_child == {}
    assert window._entry_child_by_id == {}
    assert window._entry_card_by_id == {}

    assert app.vault_service is None
    assert app.password_service is None
    assert app.repository is None
    assert app.secret_service is None
    assert app.secret_repository is None
    assert app.crypto_service is None
    assert app._session_master_password is None
    assert app.current_vault is None
    assert app.current_user is None
    assert app.current_db_path is None


def test_soft_lock_with_ssh_detail_triggers_logout_action() -> None:
    window = cast(Any, PasswordManagerWindow.__new__(PasswordManagerWindow))

    nav_visible_values: list[bool] = []
    window._set_navigation_visible = lambda visible: nav_visible_values.append(bool(visible))

    app = MagicMock()
    app.lookup_action.side_effect = lambda name: _Action() if name == "logout" else None
    window.app = app

    window.current_detail_mode = SECRET_TYPE_SSH_KEY
    window.detail_ssh_reveal_label = FakeLabel("-----BEGIN OPENSSH PRIVATE KEY-----")

    window._on_soft_lock_clicked(MagicMock())

    assert nav_visible_values == [False]
    app.activate_action.assert_called_once_with("logout", None)
