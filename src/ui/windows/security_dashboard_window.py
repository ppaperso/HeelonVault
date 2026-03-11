"""Fenetre dediee au dashboard securite."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import gi  # type: ignore[import]
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from src.config.environment import get_data_directory, is_dev_mode
from src.i18n import _
from src.models.password_entry import PasswordEntry
from src.services.password_strength_service import PasswordStrengthService
from src.services.security_audit_service import SecurityAuditService

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

if TYPE_CHECKING:
    from src.models.vault import Vault


logger = logging.getLogger(__name__)
DATA_DIR = get_data_directory()
DEV_MODE = is_dev_mode()


@dataclass
class RiskItem:
    entry: PasswordEntry
    score: int
    reasons: list[str]


def compute_top_risk_entries(
    entries: list[PasswordEntry],
    reused_ids: set[int],
    expired_ids: set[int],
    strength_service: PasswordStrengthService,
) -> list[RiskItem]:
    items: list[RiskItem] = []
    for entry in entries:
        entry_id = entry.id
        if not isinstance(entry_id, int):
            continue

        score = entry.strength_score
        if score < 0:
            result = strength_service.evaluate(entry.password)
            score_raw = result.get("score", 0)
            score = score_raw if isinstance(score_raw, int) else 0

        risk = 0
        reasons: list[str] = []
        if score == 0:
            risk += 3
            reasons.append(_("Weak"))
        elif score == 1:
            risk += 2
            reasons.append(_("Weak"))

        if entry_id in reused_ids:
            risk += 2
            reasons.append(_("Reused"))

        if entry_id in expired_ids:
            risk += 1
            reasons.append(_("Expiring"))

        if risk > 0:
            items.append(RiskItem(entry=entry, score=risk, reasons=reasons))

    items.sort(key=lambda item: (item.score, item.entry.modified_at or datetime.min), reverse=True)
    return items[:5]


def ensure_score_history_table(users_db_path: Path) -> None:
    conn = sqlite3.connect(str(users_db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS security_score_history (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                vault_uuid TEXT,
                score INTEGER,
                recorded_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def record_security_score(users_db_path: Path, user_id: int, vault_uuid: str, score: int) -> None:
    ensure_score_history_table(users_db_path)
    conn = sqlite3.connect(str(users_db_path))
    try:
        conn.execute(
            """
            INSERT INTO security_score_history (user_id, vault_uuid, score)
            VALUES (?, ?, ?)
            """,
            (user_id, vault_uuid, score),
        )
        conn.commit()
    finally:
        conn.close()


def load_score_history(
    users_db_path: Path,
    user_id: int,
    vault_uuid: str,
    limit: int = 30,
) -> list[tuple[datetime, int]]:
    ensure_score_history_table(users_db_path)
    conn = sqlite3.connect(str(users_db_path))
    rows: list[tuple[datetime, int]] = []
    try:
        cursor = conn.execute(
            """
            SELECT recorded_at, score
            FROM security_score_history
            WHERE user_id = ? AND vault_uuid = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, vault_uuid, limit),
        )
        for recorded_at, score in cursor.fetchall():
            try:
                dt = datetime.fromisoformat(str(recorded_at))
            except ValueError:
                dt = datetime.now()
            rows.append((dt, int(score)))
    finally:
        conn.close()
    rows.reverse()
    return rows


class SecurityDashboardWindow(Adw.Window):
    """Fenetre premium de dashboard securite du vault actif."""

    def __init__(
        self,
        *,
        parent: Gtk.Window,
        entries: list[PasswordEntry],
        audit_summary: dict[str, object],
        strength_service: PasswordStrengthService,
        audit_service: SecurityAuditService,
        vault: Vault | None,
        user_info: dict[str, object] | None,
        users_db_path: Path,
        log_file: Path | None,
    ) -> None:
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(False)
        self.set_title(_("Security Dashboard"))
        self.set_default_size(1100, 720)
        self.maximize()
        self._temp_assets_dir: Path | None = None
        self.connect("destroy", lambda *_args: self._cleanup_temp_assets())

        self.entries = entries
        self.audit_summary = audit_summary
        self.strength_service = strength_service
        self.audit_service = audit_service
        self.vault = vault
        self.user_info = user_info or {}
        self.users_db_path = users_db_path
        self.log_file = log_file

        self.score_counts = self._compute_score_counts(entries)
        self.strong_count = sum(self.score_counts[level] for level in (3, 4))
        self.category_scores = self._compute_category_scores(entries)
        self.expiration_rows = self._compute_expiration_rows(entries)
        self.global_score = self._as_int(self.audit_summary.get("global_score", 100), 100)
        self.weak_count = self._as_int(self.audit_summary.get("weak_count", 0), 0)
        self.reused_count = self._as_int(self.audit_summary.get("reused_count", 0), 0)
        self.expired_count = self._as_int(self.audit_summary.get("expired_count", 0), 0)

        user_id_raw = self.user_info.get("id")
        if isinstance(user_id_raw, int) and self.vault is not None:
            record_security_score(
                self.users_db_path,
                user_id_raw,
                self.vault.uuid,
                self.global_score,
            )
            self.history_points = load_score_history(
                self.users_db_path,
                user_id_raw,
                self.vault.uuid,
                limit=30,
            )
        else:
            self.history_points = []

        self.top_risk = compute_top_risk_entries(
            entries,
            self._as_int_set(self.audit_summary.get("reused_ids", set())),
            self._as_int_set(self.audit_summary.get("expired_ids", set())),
            self.strength_service,
        )

        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label=_("Security Dashboard"), xalign=0)
        title.set_css_classes(["title-3"])
        title_box.append(title)

        vault_name = self.vault.name if self.vault else _("Unknown vault")
        subtitle = Gtk.Label(label=vault_name, xalign=0)
        subtitle.set_css_classes(["caption", "dim-label"])
        title_box.append(subtitle)
        header.set_title_widget(title_box)

        export_btn = Gtk.Button(label=_("Export PDF"))
        export_btn.set_css_classes(["suggested-action"])
        export_btn.connect("clicked", self._on_export_pdf_clicked)
        header.pack_end(export_btn)

        webview = self._build_webview_widget()
        if webview is None:
            unavailable = Adw.StatusPage.new()
            unavailable.set_icon_name("dialog-warning-symbolic")
            unavailable.set_title(_("Web security dashboard unavailable"))
            unavailable.set_description(
                _("WebKit runtime is missing. Install WebKitGTK to display this dashboard.")
            )
            toolbar.set_content(unavailable)
            return

        toolbar.set_content(webview)

    def _build_webview_widget(self) -> Gtk.Widget | None:
        try:
            gi.require_version("WebKit", "6.0")
            from gi.repository import WebKit
        except Exception:
            return None

        assets_dir = Path(tempfile.mkdtemp(prefix="heelonvault-security-dashboard-"))
        self._temp_assets_dir = assets_dir

        payload = self._build_web_payload()
        html_content = self._render_web_template(payload)

        if DEV_MODE:
            debug_path = DATA_DIR / "debug_dashboard.html"
            debug_path.write_text(html_content, encoding="utf-8")
            logger.debug("Dashboard HTML ecrit dans %s", debug_path)

        webview = WebKit.WebView()
        settings = WebKit.Settings.new()
        settings.set_enable_javascript(True)
        settings.set_enable_developer_extras(DEV_MODE)
        settings.set_javascript_can_open_windows_automatically(False)
        if hasattr(settings, "set_allow_file_access_from_file_urls"):
            settings.set_allow_file_access_from_file_urls(True)
        if hasattr(settings, "set_allow_universal_access_from_file_urls"):
            settings.set_allow_universal_access_from_file_urls(True)
        webview.set_settings(settings)

        def _on_load_failed(
            _wv: object,
            _load_event: object,
            failing_uri: str,
            err: object,
        ) -> bool:
            logger.error("WebKit load failed for %s: %s", failing_uri, err)
            return False

        webview.connect("load-failed", _on_load_failed)
        webview.load_html(html_content, f"{assets_dir.as_uri()}/")
        return webview

    def _build_web_payload(self) -> dict[str, object]:
        timeline = [
            {
                "title": entry.title,
                "expires": expires_at.strftime("%Y-%m-%d"),
                "days_left": days_left,
            }
            for entry, expires_at, days_left in self.expiration_rows
        ]
        categories = [
            {"name": name, "strong_percent": percent} for name, percent in self.category_scores
        ]
        risks = [
            {
                "title": item.entry.title,
                "subtitle": " · ".join(item.reasons),
                "reasons": item.reasons,
                "score": item.score,
            }
            for item in self.top_risk
        ]
        history = [
            {"date": dt.strftime("%Y-%m-%d"), "score": score}
            for dt, score in self.history_points
        ]

        payload: dict[str, object] = {
            "title": _("Security Dashboard"),
            "vault": self.vault.name if self.vault else _("Unknown vault"),
            "global_score": self.global_score,
            "weak_count": self.weak_count,
            "reused_count": self.reused_count,
            "expired_count": self.expired_count,
            "strong_count": self.strong_count,
            "score_counts": self.score_counts,
            "categories": categories,
            "risks": risks,
            "timeline": timeline,
            "history": history,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "i18n": {
                "global_security_score": _("Global security score"),
                "password_strength_distribution": _("Password strength distribution"),
                "vulnerability_by_category": _("Vulnerability by category"),
                "top_5_entries_at_risk": _("Top 5 entries at risk"),
                "password_expiration_timeline": _("Top 5 password expirations"),
                "score_history": _("Score history"),
                "application_logs_admin": _("Application logs (admin)"),
                "updated_prefix": _("Updated:"),
                "kpi_weak": _("Weak"),
                "kpi_reused": _("Reused"),
                "kpi_expiring": _("Expiring"),
                "kpi_strong": _("Strong"),
                "kpi_score": _("Score"),
                "strong_suffix": _("strong"),
                "no_category_data": _("No category data"),
                "no_immediate_risks_detected": _("No immediate risks detected"),
                "expires_prefix": _("Expires"),
                "days_suffix": _("days"),
                "no_expiration_configured": _("No expiration configured"),
                "history_hint": _("Open this dashboard regularly to build history"),
                "load_error": _("Unable to load local report data."),
                "reason_weak": _("Weak"),
                "reason_reused": _("Reused"),
                "reason_expiring": _("Expiring"),
            },
        }

        if self.user_info.get("role") == "admin":
            payload["admin_logs"] = self._read_last_log_lines(100)
        else:
            payload["admin_logs"] = []

        return payload

    def _render_web_template(self, payload: dict[str, object]) -> str:
        template = """<!doctype html>
<html lang='en'>
<head>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1' />
    <title>Security Dashboard</title>
    <style>
        :root {
            --bg:
                radial-gradient(1200px 600px at 15% -10%, #d9f4f2, transparent),
                radial-gradient(1000px 500px at 100% 0%, #e9faf8, transparent),
                #f4f8f7;
            --card: #ffffff;
            --ink: #07393A;
            --muted: #4f7070;
            --teal: #13A1A1;
            --good: #43A047;
            --mid: #FB8C00;
            --bad: #E53935;
            --line: rgba(7,57,58,.12);
            --line-strong: rgba(7,57,58,.20);
            --shadow: 0 14px 30px rgba(7,57,58,.10);
            --shadow-hover: 0 18px 36px rgba(7,57,58,.16);
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: 'Space Grotesk', 'Cantarell', sans-serif;
            background: var(--bg);
            color: var(--ink);
            padding: 18px;
        }
        .hero {
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 14px;
            margin-bottom: 14px;
        }
        .panel {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: var(--shadow);
            padding: 14px;
            position: relative;
            overflow: hidden;
            animation: panel-in .35s ease-out both;
        }
        .panel::before {
            content: '';
            position: absolute;
            inset: 0;
            pointer-events: none;
            border-radius: 18px;
            background: linear-gradient(180deg, rgba(255,255,255,.65), rgba(255,255,255,0));
            opacity: .45;
        }
        .title { font-size: 1.4rem; font-weight: 800; }
        .sub { color: var(--muted); font-size: .88rem; margin-top: 4px; }
        .kpis { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: 10px; }
        .kpi {
            background: linear-gradient(160deg, rgba(19,161,161,.10), rgba(255,255,255,.65));
            border: 1px solid rgba(19,161,161,.26);
            border-radius: 14px;
            padding: 10px;
        }
        .kpi .v { font-size: 1.55rem; font-weight: 800; }
        .kpi .l { color: var(--muted); font-size: .75rem; }
        .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
        .grid3 {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin: 14px 0;
            align-items: stretch;
        }
        .section-title { font-size: .95rem; font-weight: 760; margin: 0 0 8px; }
        .row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            padding: 7px 0;
            border-bottom: 1px dashed rgba(7,57,58,.08);
        }
        .row:last-child { border-bottom: none; }
        .pill { border-radius: 999px; padding: 2px 8px; font-size: .72rem; font-weight: 700; }
        .weak { color: var(--bad); background: rgba(229,57,53,.12); }
        .reused { color: var(--mid); background: rgba(251,140,0,.12); }
        .exp { color: #0A5F5C; background: rgba(19,161,161,.12); }
        .legend {
            margin-top: 10px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            font-size: .78rem;
            color: var(--muted);
            border: 1px solid rgba(7,57,58,.10);
            border-radius: 10px;
            padding: 6px 8px;
            background: rgba(255,255,255,.72);
        }
        .legend-left {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            min-width: 0;
        }
        .legend-value {
            color: var(--ink);
            font-weight: 700;
        }
        .dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            flex: 0 0 auto;
        }
        .chart-hint {
            margin-top: 8px;
            color: var(--muted);
            font-size: .75rem;
        }
        canvas { max-width: 100%; display: block; }
        .mono {
            font-family: 'Space Mono', monospace;
            font-size: .75rem;
            line-height: 1.45;
            background: #0D1117;
            color: #C9D1D9;
            border-radius: 10px;
            padding: 10px;
            max-height: 240px;
            overflow: auto;
            white-space: pre-wrap;
        }
        @keyframes panel-in {
            from { transform: translateY(8px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        @media (max-width: 980px) {
            .hero, .grid2, .grid3 { grid-template-columns: 1fr; }
            .kpis { grid-template-columns: repeat(2, minmax(0,1fr)); }
            .legend { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class='hero'>
        <div class='panel'>
            <div class='title' id='title'></div>
            <div class='sub' id='subtitle'></div>
            <div class='sub' id='updated'></div>
        </div>
        <div class='panel'>
            <div class='title' id='score'></div>
            <div class='sub' id='globalScoreLabel'></div>
        </div>
    </div>
    <div class='kpis panel' id='kpis'></div>
    <div class='grid3'>
        <div class='panel'>
            <h3 class='section-title' id='distributionTitle'></h3>
            <canvas id='donut' width='360' height='220'></canvas>
            <div class='legend' id='donutLegend'></div>
        </div>
        <div class='panel'>
            <h3 class='section-title' id='categoriesTitle'></h3>
            <canvas id='categoriesChart' width='420' height='280'></canvas>
            <div class='chart-hint' id='catsHint'></div>
        </div>
        <div class='panel'>
            <h3 class='section-title' id='historyTitle'></h3>
            <canvas id='history' width='420' height='220'></canvas>
            <div class='chart-hint' id='historyHint'></div>
        </div>
    </div>
    <div class='grid2'>
        <div class='panel'>
            <h3 class='section-title' id='risksTitle'></h3>
            <div id='risks'></div>
        </div>
        <div class='panel'>
            <h3 class='section-title' id='timelineTitle'></h3>
            <div id='timeline'></div>
        </div>
    </div>
    <div class='panel' id='logsWrap' style='display:none;'>
        <h3 class='section-title' id='logsTitle'></h3>
        <div class='mono' id='logs'></div>
    </div>
    <script>
        document.addEventListener('DOMContentLoaded', function() {
        const data = __PAYLOAD__;
        const colors = ['#E53935','#FB8C00','#FDD835','#43A047','#13A1A1'];
        const donutCtx = document.getElementById('donut').getContext('2d');
        const categoriesCtx = document.getElementById('categoriesChart').getContext('2d');
        const historyCtx = document.getElementById('history').getContext('2d');
        try {
            const i18n = data.i18n || {};
            const text = (key, fallback = '') => i18n[key] || fallback;

            document.getElementById('title').textContent = data.title;
            document.getElementById('subtitle').textContent = data.vault;
            document.getElementById('updated').textContent = (
                text('updated_prefix', 'Updated:') + ' ' + data.updated_at
            );
            document.getElementById('globalScoreLabel').textContent = text(
                'global_security_score',
                'Global security score'
            );
            document.getElementById('distributionTitle').textContent = text(
                'password_strength_distribution',
                'Password strength distribution'
            );
            document.getElementById('categoriesTitle').textContent = text(
                'vulnerability_by_category',
                'Vulnerability by category'
            );
            document.getElementById('risksTitle').textContent = text(
                'top_5_entries_at_risk',
                'Top 5 entries at risk'
            );
            document.getElementById('timelineTitle').textContent = text(
                'password_expiration_timeline',
                'Password expiration timeline'
            );
            document.getElementById('historyTitle').textContent = text(
                'score_history',
                'Score history'
            );
            document.getElementById('logsTitle').textContent = text(
                'application_logs_admin',
                'Application logs (admin)'
            );

            const scoreEl = document.getElementById('score');
            scoreEl.textContent = data.global_score + '%';
            scoreEl.style.color = data.global_score >= 80
                ? '#43A047'
                : (data.global_score >= 50 ? '#FB8C00' : '#E53935');

            const kpis = [
                ['🔴 ' + text('kpi_weak', 'Weak'), data.weak_count],
                ['♻️ ' + text('kpi_reused', 'Reused'), data.reused_count],
                ['⏰ ' + text('kpi_expiring', 'Expiring'), data.expired_count],
                ['✅ ' + text('kpi_strong', 'Strong'), data.strong_count],
                ['🔒 ' + text('kpi_score', 'Score'), data.global_score + '%']
            ];
            document.getElementById('kpis').innerHTML = kpis
                .map(([l, v]) => {
                    return (
                        `<div class='kpi'><div class='v'>${v}</div>` +
                        `<div class='l'>${l}</div></div>`
                    );
                })
                .join('');

            function getScoreCount(obj, k) {
                if (obj[k] !== undefined) {
                    return obj[k];
                }
                const ks = String(k);
                if (obj[ks] !== undefined) {
                    return obj[ks];
                }
                return 0;
            }

            const counts = [0,1,2,3,4].map(function(k) {
                return Number(getScoreCount(data.score_counts, k));
            });

            const total = counts.reduce((a,b)=>a+b,0) || 1;
            let start = -Math.PI/2;
            const cx = 160, cy = 110, radius = 82, inner = 50;
            counts.forEach((count, idx)=>{
                const angle = (count / total) * Math.PI * 2;
                donutCtx.beginPath();
                donutCtx.strokeStyle = colors[idx];
                donutCtx.lineWidth = radius - inner;
                donutCtx.arc(cx, cy, (radius+inner)/2, start, start + angle);
                donutCtx.stroke();
                start += angle;
            });
            donutCtx.fillStyle = '#fff';
            donutCtx.beginPath();
            donutCtx.arc(cx, cy, inner-4, 0, Math.PI * 2);
            donutCtx.fill();
            donutCtx.fillStyle = '#07393A';
            donutCtx.font = '700 26px Space Grotesk';
            donutCtx.textAlign = 'center';
            donutCtx.fillText(data.global_score + '%', cx, cy + 8);

            const scoreLabels = [
                text('score_0_label', 'Score 0'),
                text('score_1_label', 'Score 1'),
                text('score_2_label', 'Score 2'),
                text('score_3_label', 'Score 3'),
                text('score_4_label', 'Score 4')
            ];
            document.getElementById('donutLegend').innerHTML = counts
                .map((count, idx) => {
                    return (
                        `<div class='legend-item'><span class='legend-left'>` +
                        `<span class='dot' style='background:${colors[idx]}'></span>` +
                        `<span>${scoreLabels[idx]}</span></span>` +
                        `<span class='legend-value'>${count}</span></div>`
                    );
                })
                .join('');

            const categories = (data.categories || []).slice(0, 12);
            if (!categories.length) {
                document.getElementById('catsHint').textContent = text('no_category_data',
                'No category data');
            } else {
                const w = categoriesCtx.canvas.width;
                const h = categoriesCtx.canvas.height;
                const m = 30;
                const mb = 65;
                const gw = w - m * 2;
                const gh = h - m - mb;
                const barW = gw / Math.max(1, categories.length) * 0.72;

                categoriesCtx.strokeStyle = 'rgba(7,57,58,.14)';
                [0, 25, 50, 75, 100].forEach(v => {
                    const y = m + gh - gh * (v / 100);
                    categoriesCtx.beginPath();
                    categoriesCtx.moveTo(m, y);
                    categoriesCtx.lineTo(m + gw, y);
                    categoriesCtx.stroke();
                });

                categoriesCtx.textAlign = 'center';
                categoriesCtx.textBaseline = 'top';
                categoriesCtx.font = '600 10px Space Grotesk';
                categoriesCtx.fillStyle = '#6b8888';
                [0, 25, 50, 75, 100].forEach(v => {
                    const y = m + gh - gh * (v / 100);
                    categoriesCtx.fillText(String(v), m - 12, y - 5);
                });

                categories.forEach((c, i) => {
                    const x = m + gw * (i / categories.length) +
                    (gw / categories.length - barW) / 2;
                    const y = m + gh - gh * ((c.strong_percent || 0) / 100);
                    const barColor = (c.strong_percent || 0) >= 80
                        ? '#43A047'
                        : ((c.strong_percent || 0) >= 50 ? '#FB8C00' : '#E53935');
                    const grad = categoriesCtx.createLinearGradient(0, y, 0, m + gh);
                    grad.addColorStop(0, barColor);
                    grad.addColorStop(1, 'rgba(255,255,255,.85)');
                    categoriesCtx.fillStyle = grad;
                    categoriesCtx.fillRect(x, y, barW, (m + gh) - y);

                    categoriesCtx.strokeStyle = 'rgba(7,57,58,.12)';
                    categoriesCtx.strokeRect(x, y, barW, (m + gh) - y);

                    const label = String(c.name || '').slice(0, 12);
                    const lx = x + barW / 2;
                    categoriesCtx.save();
                    categoriesCtx.fillStyle = '#4f7070';
                    categoriesCtx.translate(lx + 2, m + gh + 18);
                    categoriesCtx.rotate(-0.6);
                    categoriesCtx.textAlign = 'right';
                    categoriesCtx.textBaseline = 'middle';
                    categoriesCtx.fillText(label, 0, 0);
                    categoriesCtx.restore();
                });
            }

            const risks = (data.risks || []).slice(0, 5);
            document.getElementById('risks').innerHTML = risks.map(r => {
                const pills = (r.reasons || []).map(reason => {
                    let cls = 'exp';
                    if (reason === text('reason_weak', 'Weak')) {
                        cls = 'weak';
                    } else if (reason === text('reason_reused', 'Reused')) {
                        cls = 'reused';
                    }
                    return `<span class='pill ${cls}'>${reason}</span>`;
                }).join(' ');
                return (
                    `<div class='row'><div><div style='font-weight:700'>${r.title}</div>` +
                    `<div class='sub'>${r.subtitle}</div></div><div>${pills}</div></div>`
                );
            }).join('') || (`<div class="sub">` +
                `${text('no_immediate_risks_detected', 'No immediate risks detected')}</div>`);

            const timelineRows = (data.timeline || []).slice(0, 5);
            document.getElementById('timeline').innerHTML = timelineRows.map(t => {
                const color = t.days_left <= 0
                    ? '#E53935'
                    : (t.days_left <= 7 ? '#FB8C00' : '#43A047');
                return (
                    `<div class='row'><div><div style='font-weight:700'>${t.title}</div>` +
                    `<div class='sub'>${text('expires_prefix', 'Expires')}` +
                    ` ${t.expires}</div></div>` +
                    `<div style='color:${color};font-weight:700'>` +
                    `${t.days_left} ${text('days_suffix', 'days')}</div></div>`
                );
            }).join('') || (`<div class="sub">` +
                `${text('no_expiration_configured', 'No expiration configured')}</div>`);

            const history = data.history || [];
            if (history.length < 2) {
                document.getElementById('historyHint').textContent = (
                    text('history_hint', 'Open this dashboard regularly to build history')
                );
            } else {
                const w = historyCtx.canvas.width, h = historyCtx.canvas.height;
                const m = 30, gw = w - m*2, gh = h - m*2;
                historyCtx.strokeStyle = 'rgba(7,57,58,.16)';
                [25,50,75,100].forEach(v => {
                    const y = m + gh - gh * (v/100);
                    historyCtx.beginPath();
                    historyCtx.moveTo(m, y);
                    historyCtx.lineTo(m + gw, y);
                    historyCtx.stroke();
                });

                const areaGrad = historyCtx.createLinearGradient(0, m, 0, m + gh);
                areaGrad.addColorStop(0, 'rgba(19,161,161,.28)');
                areaGrad.addColorStop(1, 'rgba(19,161,161,.02)');

                historyCtx.beginPath();
                history.forEach((p, i) => {
                    const x = m + gw * (i / Math.max(1, history.length - 1));
                    const y = m + gh - gh * (p.score / 100);
                    if (i === 0) historyCtx.moveTo(x, y); else historyCtx.lineTo(x, y);
                });
                historyCtx.lineTo(m + gw, m + gh);
                historyCtx.lineTo(m, m + gh);
                historyCtx.closePath();
                historyCtx.fillStyle = areaGrad;
                historyCtx.fill();

                historyCtx.beginPath();
                historyCtx.strokeStyle = '#13A1A1';
                historyCtx.lineWidth = 2;
                history.forEach((p, i) => {
                    const x = m + gw * (i / Math.max(1, history.length - 1));
                    const y = m + gh - gh * (p.score / 100);
                    if (i === 0) historyCtx.moveTo(x, y); else historyCtx.lineTo(x, y);
                });
                historyCtx.stroke();
                history.forEach((p, i) => {
                    const x = m + gw * (i / Math.max(1, history.length - 1));
                    const y = m + gh - gh * (p.score / 100);
                    historyCtx.fillStyle = '#13A1A1';
                    historyCtx.beginPath();
                    historyCtx.arc(x, y, 4, 0, Math.PI * 2);
                    historyCtx.fill();
                });

                const dateStep = Math.max(1, Math.ceil(history.length / 6));
                historyCtx.fillStyle = '#4f7070';
                historyCtx.font = '600 10px Space Grotesk';
                historyCtx.textAlign = 'center';
                historyCtx.textBaseline = 'top';
                [0, 25, 50, 75, 100].forEach(v => {
                    const y = m + gh - gh * (v/100);
                    historyCtx.fillText(String(v), m - 12, y - 5);
                });
                history.forEach((p, i) => {
                    if (i % dateStep !== 0 && i !== history.length - 1) {
                        return;
                    }
                    const x = m + gw * (i / Math.max(1, history.length - 1));
                    const label = String(p.date || '').slice(5);
                    historyCtx.fillText(label, x, m + gh + 4);
                });
            }

            const logs = data.admin_logs || [];
            if (logs.length) {
                document.getElementById('logsWrap').style.display = 'block';
                document.getElementById('logs').textContent = logs.join('\\n');
            }
        } catch (_error) {
            document.body.innerHTML = (
                '<div class="panel"><div class="title">Security Dashboard</div>' +
                `<div class="sub">__LOAD_ERROR__ (${_error})</div></div>`
            );
        }
        });
    </script>
</body>
</html>
"""
        payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        return (
            template.replace("__PAYLOAD__", payload_json)
            .replace(
                "__LOAD_ERROR__",
                _("Unable to load local report data.").replace("'", "\\'"),
            )
        )

    def _cleanup_temp_assets(self) -> None:
        if DEV_MODE:
            return
        if not self._temp_assets_dir:
            return
        try:
            shutil.rmtree(self._temp_assets_dir, ignore_errors=True)
        finally:
            self._temp_assets_dir = None

    def _read_last_log_lines(self, limit: int) -> list[str]:
        if not self.log_file or not self.log_file.exists():
            return [_("No logs available")]
        try:
            lines = self.log_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            return [_("Unable to read logs")]
        return lines[-limit:]

    def _compute_score_counts(self, entries: list[PasswordEntry]) -> dict[int, int]:
        counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
        for entry in entries:
            score = entry.strength_score
            if score < 0:
                result = self.strength_service.evaluate(entry.password)
                score_raw = result.get("score", 0)
                score = score_raw if isinstance(score_raw, int) else 0
            score = max(0, min(score, 4))
            counts[score] += 1
        return counts

    def _compute_category_scores(self, entries: list[PasswordEntry]) -> list[tuple[str, int]]:
        if not entries:
            return []

        grouped: dict[str, list[int]] = {}
        for entry in entries:
            category = entry.category or _("Uncategorized")
            score = entry.strength_score
            if score < 0:
                result = self.strength_service.evaluate(entry.password)
                score_raw = result.get("score", 0)
                score = score_raw if isinstance(score_raw, int) else 0
            grouped.setdefault(category, []).append(score)

        rows: list[tuple[str, int]] = []
        for category, scores in grouped.items():
            strong_count = sum(1 for score in scores if score >= 3)
            percent = round((strong_count / len(scores)) * 100)
            rows.append((category, percent))

        rows.sort(key=lambda item: item[0].lower())
        return rows

    def _compute_expiration_rows(
        self,
        entries: list[PasswordEntry],
    ) -> list[tuple[PasswordEntry, datetime, int]]:
        rows: list[tuple[PasswordEntry, datetime, int]] = []
        now = datetime.now()

        for entry in entries:
            validity = entry.password_validity_days
            if not validity or validity <= 0:
                continue
            base = entry.modified_at or entry.created_at
            if not base:
                continue
            expires_at = base + timedelta(days=validity)
            days_left = (expires_at.date() - now.date()).days
            rows.append((entry, expires_at, days_left))

        rows.sort(key=lambda item: item[1])
        return rows

    def _on_export_pdf_clicked(self, _button: Gtk.Button) -> None:
        chooser = Gtk.FileChooserNative.new(
            _("Export Security Report"),
            self,
            Gtk.FileChooserAction.SAVE,
            _("Save"),
            _("Cancel"),
        )
        chooser.set_current_name(
            f"heelonvault-report-{datetime.now().strftime('%Y-%m-%d')}.pdf"
        )

        pdf_filter = Gtk.FileFilter()
        pdf_filter.set_name(_("PDF files"))
        pdf_filter.add_pattern("*.pdf")
        chooser.add_filter(pdf_filter)

        def on_response(native: Gtk.FileChooserNative, response: int) -> None:
            if response != Gtk.ResponseType.ACCEPT:
                return
            target = native.get_file()
            if not target:
                return
            path = target.get_path()
            if not path:
                return
            self._export_pdf(Path(path))

        chooser.connect("response", on_response)
        chooser.show()

    def _export_pdf(self, pdf_path: Path) -> None:
        if pdf_path.suffix.lower() != ".pdf":
            pdf_path = pdf_path.with_suffix(".pdf")

        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        width, height = A4
        y = height - 60

        vault_name = self.vault.name if self.vault else _("Unknown vault")
        date_label = datetime.now().strftime("%Y-%m-%d %H:%M")

        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, y, _("Security Dashboard"))
        y -= 24
        c.setFont("Helvetica", 11)
        c.drawString(50, y, _("Generated at: %(date)s") % {"date": date_label})
        y -= 18
        c.drawString(50, y, _("Vault: %(vault)s") % {"vault": vault_name})
        y -= 30

        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, _("Global score: %(score)s%%") % {
            "score": self.global_score,
        })
        y -= 26

        c.setFont("Helvetica", 11)
        kpis = [
            (_("Weak passwords"), self.weak_count),
            (_("Reused passwords"), self.reused_count),
            (_("Expiring soon"), self.expired_count),
            (_("Strong passwords"), self.strong_count),
        ]
        for label, value in kpis:
            c.drawString(50, y, f"- {label}: {value}")
            y -= 16

        c.showPage()
        y = height - 60
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, _("Top 5 entries at risk"))
        y -= 24
        c.setFont("Helvetica", 10)
        for item in self.top_risk:
            line = f"{item.entry.title} - {' / '.join(item.reasons)}"
            c.drawString(50, y, line[:100])
            y -= 14

        c.showPage()
        y = height - 60
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, _("Password expiration timeline"))
        y -= 24
        c.setFont("Helvetica", 10)
        for entry, expires_at, days_left in self.expiration_rows[:25]:
            line = _("%(title)s - %(date)s (%(days)s days)") % {
                "title": entry.title,
                "date": expires_at.strftime("%Y-%m-%d"),
                "days": days_left,
            }
            c.drawString(50, y, line[:100])
            y -= 14

        c.setFont("Helvetica-Oblique", 9)
        c.drawString(
            50,
            22,
            _("Generated by HeelonVault - Your secrets never leave your machine."),
        )
        c.save()

    @staticmethod
    def _as_int(value: object, default: int) -> int:
        return value if isinstance(value, int) else default

    @staticmethod
    def _as_int_set(value: object) -> set[int]:
        if not isinstance(value, set):
            return set()
        return {item for item in value if isinstance(item, int)}
