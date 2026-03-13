"""Integration-style tests for SSH detail behavior in MainWindow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from src.models.secret_item import SecretItem
from src.models.secret_types import SECRET_TYPE_PASSWORD, SECRET_TYPE_SSH_KEY
from src.ui.windows.main_window import PasswordManagerWindow


class FakeRow:
    def __init__(self) -> None:
        self.title = ""
        self.text = ""
        self.visible = True
        self.sensitive = True
        self.editable = True
        self.show_peek_icon = True
        self.value = 0.0

    def set_title(self, title: str) -> None:
        self.title = title

    def set_text(self, text: str) -> None:
        self.text = text

    def get_text(self) -> str:
        return self.text

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def set_sensitive(self, sensitive: bool) -> None:
        self.sensitive = sensitive

    def set_editable(self, editable: bool) -> None:
        self.editable = editable

    def set_show_peek_icon(self, show_peek_icon: bool) -> None:
        self.show_peek_icon = show_peek_icon

    def set_value(self, value: float) -> None:
        self.value = value


class FakeBuffer:
    def __init__(self) -> None:
        self.text = ""

    def set_text(self, text: str) -> None:
        self.text = text


class FakeNotesView:
    def __init__(self) -> None:
        self.buffer = FakeBuffer()
        self.editable = True
        self.cursor_visible = True

    def get_buffer(self) -> FakeBuffer:
        return self.buffer

    def set_editable(self, editable: bool) -> None:
        self.editable = editable

    def set_cursor_visible(self, visible: bool) -> None:
        self.cursor_visible = visible


class FakeLabel:
    def __init__(self) -> None:
        self.label = ""
        self.visible = True

    def set_label(self, value: str) -> None:
        self.label = value

    def set_visible(self, visible: bool) -> None:
        self.visible = visible


class FakeButton:
    def __init__(self) -> None:
        self.tooltip = ""
        self.visible = True
        self.sensitive = True

    def set_tooltip_text(self, text: str) -> None:
        self.tooltip = text

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def set_sensitive(self, sensitive: bool) -> None:
        self.sensitive = sensitive


@dataclass
class DetailRows:
    title: FakeRow
    username: FakeRow
    password: FakeRow
    url: FakeRow
    category: FakeRow
    tags: FakeRow
    validity: FakeRow
    validity_display: FakeRow
    notes: FakeNotesView


def _build_window_stub() -> tuple[Any, DetailRows]:
    window = cast(Any, PasswordManagerWindow.__new__(PasswordManagerWindow))

    rows = DetailRows(
        title=FakeRow(),
        username=FakeRow(),
        password=FakeRow(),
        url=FakeRow(),
        category=FakeRow(),
        tags=FakeRow(),
        validity=FakeRow(),
        validity_display=FakeRow(),
        notes=FakeNotesView(),
    )

    window.current_detail_mode = "password"
    window.current_secret_type_filter = SECRET_TYPE_SSH_KEY
    window.current_entry_id = -1_000_123
    window._updating_detail = False
    window._ssh_reveal_source_id = None

    window.detail_password_row = rows.password
    window.detail_password_strength_inline_label = FakeLabel()
    window.detail_password_copy_button = FakeButton()
    window.detail_password_generate_button = FakeButton()
    window.detail_password_reveal_button = FakeButton()
    window.detail_password_import_button = FakeButton()
    window.detail_password_export_button = FakeButton()

    window.detail_header_title = FakeLabel()
    window.detail_meta_label = FakeLabel()
    window.detail_validity_display_row = rows.validity_display
    window.detail_validity_display_value_label = FakeLabel()
    window.detail_ssh_reveal_label = FakeLabel()

    window._secret_item_by_ui_id = {}
    window._entry_card_by_id = {}
    window.current_sort_mode = "usage_desc"

    window._clear_detail_badges = lambda: None
    window._add_detail_icon_badge = lambda _icon, _tooltip, _css: None
    window._hide_ssh_reveal_value = lambda: None
    window._set_detail_sensitive = lambda _enabled: None
    window._update_detail_strength_indicator = lambda _text: None

    window._require_detail_rows = lambda: (
        rows.title,
        rows.username,
        rows.password,
        rows.url,
        rows.category,
        rows.tags,
        rows.validity,
        rows.notes,
    )

    return window, rows


def test_set_detail_mode_ssh_updates_labels_and_actions() -> None:
    window, rows = _build_window_stub()

    window._set_detail_mode(SECRET_TYPE_SSH_KEY)

    assert rows.username.title == "Algorithm"
    assert rows.password.title == "SSH private key"
    assert rows.url.title == "Fingerprint"
    assert rows.tags.title == "Comment"
    assert rows.category.visible is False
    assert rows.validity.title == "Key size (bits)"
    assert rows.validity.visible is False
    assert rows.validity_display.title == "Key size (bits)"
    assert rows.validity_display.visible is True

    assert window.detail_password_copy_button.visible is False
    assert window.detail_password_reveal_button.visible is False
    assert window.detail_password_import_button.visible is True
    assert window.detail_password_export_button.visible is True
    assert window.detail_password_generate_button.visible is False

    assert rows.title.editable is True
    assert rows.username.editable is False
    assert rows.password.editable is False
    assert rows.password.show_peek_icon is False
    assert rows.url.editable is False
    assert rows.tags.editable is False
    assert rows.validity.sensitive is False
    assert rows.notes.editable is False
    assert rows.notes.cursor_visible is False


def test_set_detail_mode_password_restores_field_editability() -> None:
    window, rows = _build_window_stub()

    window._set_detail_mode(SECRET_TYPE_SSH_KEY)
    window._set_detail_mode(SECRET_TYPE_PASSWORD)

    assert rows.title.editable is True
    assert rows.username.editable is True
    assert rows.password.editable is True
    assert rows.url.editable is True
    assert rows.tags.editable is True
    assert rows.validity.sensitive is True
    assert rows.validity.visible is True
    assert rows.validity_display.visible is False
    assert rows.notes.editable is True
    assert rows.notes.cursor_visible is True

    assert window.detail_password_copy_button.visible is True
    assert window.detail_password_reveal_button.visible is False
    assert window.detail_password_import_button.visible is False
    assert window.detail_password_export_button.visible is False
    assert rows.password.show_peek_icon is True


def test_populate_ssh_detail_sets_fingerprint_and_badges() -> None:
    window, rows = _build_window_stub()

    badges: list[str] = []
    window._add_detail_badge = lambda label, _css: badges.append(label)

    item = SecretItem(
        id=123,
        item_uuid="u-123",
        secret_type=SECRET_TYPE_SSH_KEY,
        title="Deploy Key",
        metadata={
            "algorithm": "ed25519",
            "fingerprint": "SHA256:abc",
            "public_key_preview": "ssh-ed25519 AAAA... preview",
            "has_passphrase": True,
            "comment": "infra",
        },
        payload=b"encrypted",
        usage_count=2,
        modified_at=datetime(2026, 3, 13, 10, 30),
    )
    window._secret_item_by_ui_id[-1_000_123] = item

    window._populate_ssh_key_detail_from_ui_id(-1_000_123)

    assert rows.title.text == "Deploy Key"
    assert rows.username.text == "ED25519"
    assert rows.url.text == "SHA256:abc"
    assert rows.tags.text == "infra"
    assert window.detail_validity_display_value_label.label == "255"
    assert rows.notes.buffer.text == "ssh-ed25519 AAAA... preview"
    assert "ED25519" in badges
    assert "Protected" in badges
