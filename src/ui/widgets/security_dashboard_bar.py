"""Mini dashboard securite avec badges filtrants."""

from __future__ import annotations

import gi  # type: ignore[import]

from src.i18n import N_, _

gi.require_version("Gtk", "4.0")
from gi.repository import GObject, Gtk  # noqa: E402


class SecurityDashboardBar(Gtk.Box):
    """Barre horizontale de badges securite cliquables."""

    __gsignals__ = {
        "filter-changed": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)

        self._active_filter: str | None = None
        self._buttons: dict[str, Gtk.Button] = {}
        self._counts: dict[str, Gtk.Label] = {}

        self._build_badge("weak", "🔴", N_("Weak"))
        self._build_badge("reused", "♻️", N_("Reused"))
        self._build_badge("expired", "⏰", N_("Expiring"))
        self._build_badge("score", "🔒", N_("Score"), clickable=False)

    def _build_badge(
        self,
        badge_type: str,
        icon: str,
        label: str,
        *,
        clickable: bool = True,
    ) -> None:
        button = Gtk.Button()
        button.set_css_classes(["security-badge", f"badge-{badge_type}"])
        button.set_focusable(clickable)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        count_label = Gtk.Label(label=f"{icon} 0", xalign=0)
        count_label.set_css_classes(["security-badge-count"])
        box.append(count_label)

        text_label = Gtk.Label(label=_(label), xalign=0)
        text_label.set_css_classes(["security-badge-label"])
        box.append(text_label)

        button.set_child(box)

        if clickable:
            button.connect("clicked", self._on_badge_clicked, badge_type)
        else:
            button.add_css_class("security-badge-static")

        self._buttons[badge_type] = button
        self._counts[badge_type] = count_label
        self.append(button)

    def _on_badge_clicked(self, _button: Gtk.Button, badge_type: str) -> None:
        if self._active_filter == badge_type:
            self.set_active_filter(None)
            self.emit("filter-changed", None)
            return
        self.set_active_filter(badge_type)
        self.emit("filter-changed", badge_type)

    def set_active_filter(self, filter_type: str | None) -> None:
        self._active_filter = filter_type
        for badge_type, button in self._buttons.items():
            if badge_type == filter_type:
                button.add_css_class("security-badge-active")
            else:
                button.remove_css_class("security-badge-active")

    def update(self, summary: dict[str, object]) -> None:
        weak_raw = summary.get("weak_count", 0)
        reused_raw = summary.get("reused_count", 0)
        expired_raw = summary.get("expired_count", 0)
        score_raw = summary.get("global_score", 100)

        weak_count = weak_raw if isinstance(weak_raw, int) else 0
        reused_count = reused_raw if isinstance(reused_raw, int) else 0
        expired_count = expired_raw if isinstance(expired_raw, int) else 0
        global_score = score_raw if isinstance(score_raw, int) else 100

        self._counts["weak"].set_label(f"🔴 {weak_count}")
        self._counts["reused"].set_label(f"♻️ {reused_count}")
        self._counts["expired"].set_label(f"⏰ {expired_count}")
        self._counts["score"].set_label(f"🔒 {global_score}%")

        score_button = self._buttons["score"]
        score_button.remove_css_class("score-good")
        score_button.remove_css_class("score-medium")
        score_button.remove_css_class("score-bad")
        if global_score >= 80:
            score_button.add_css_class("score-good")
        elif global_score >= 50:
            score_button.add_css_class("score-medium")
        else:
            score_button.add_css_class("score-bad")
