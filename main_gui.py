from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import backend


QSS_DARK = """
QMainWindow, QWidget {
  background: #121212;
  color: #E0E0E0;
}

QFrame#TopBar {
  background: #171717;
  border: 1px solid #262626;
  border-radius: 10px;
}

QFrame#Sidebar {
  background: #151515;
  border: 1px solid #262626;
  border-radius: 12px;
}

QLabel#Title {
  font-size: 16px;
  font-weight: 700;
}

QPushButton {
  background: #1f1f1f;
  border: 1px solid #2d2d2d;
  padding: 8px 10px;
  border-radius: 8px;
}
QPushButton:hover {
  background: #232323;
  border: 1px solid #3a3a3a;
}
QPushButton:pressed {
  background: #1b1b1b;
}

QLineEdit, QComboBox {
  background: #1a1a1a;
  border: 1px solid #2d2d2d;
  border-radius: 8px;
  padding: 6px 10px;
}
QComboBox::drop-down {
  border-left: 1px solid #2d2d2d;
  width: 26px;
}

QTableWidget {
  background: #121212;
  gridline-color: #2a2a2a;
  border: 1px solid #262626;
  border-radius: 10px;
  selection-background-color: #263238;
  selection-color: #E0E0E0;
}
QListWidget {
  background: #1a1a1a;
  border: 1px solid #2d2d2d;
  border-radius: 8px;
  padding: 6px;
}
QListWidget::item {
  padding: 6px 8px;
  color: #E0E0E0;
}
QListWidget::item:selected {
  background: #263238;
  color: #E0E0E0;
}
QHeaderView::section {
  background: #171717;
  color: #E0E0E0;
  border: 1px solid #262626;
  padding: 6px 8px;
}
"""


GREEN = QColor("#4CAF50")
RED = QColor("#F44336")
MUTED = QColor("#9E9E9E")


UPSIDE_OPTIONS = ["All", "10%+", "20%+", "30%+", "40%+", "50%+"]


def pct_str(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return f"{v:.1f}%"


def num_str(v: Any) -> str:
    if v is None:
        return "-"
    try:
        f = float(v)
        if abs(f) >= 100:
            return f"{f:.0f}"
        return f"{f:.2f}"
    except Exception:
        return str(v)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AnalystRecom — S&P 500 Institutional Screening")
        self.resize(1250, 760)

        backend.ensure_user_assets()
        backend.sync_latest_data_from_resources()

        user_root = backend.user_root()
        self.config_path = user_root / "config" / "app_config.json"
        self.portfolio_path = user_root / "config" / "portfolio.json"

        self.config = backend.load_app_config(self.config_path)
        self.portfolio = backend.load_portfolio(self.portfolio_path)

        self.dataset: Dict[str, Any] = {"rows": [], "meta": {}, "sp500_proxy": {}}
        self.filtered_rows: List[Dict[str, Any]] = []
        self.sectors: List[str] = []
        self.industries: List[str] = []

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        self.sidebar = self._build_sidebar()
        self.main_area = self._build_main_area()
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.main_area)
        splitter.setSizes([320, 930])

        self._reload_portfolio_list()
        self._sync_and_refresh(initial=True)

    def _build_sidebar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Sidebar")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("My Portfolio")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.portfolio_summary = QLabel("-")
        self.portfolio_summary.setStyleSheet("color: #BDBDBD;")
        layout.addWidget(self.portfolio_summary)

        layout.addSpacing(6)
        layout.addWidget(QLabel("Watched Tickers"))

        self.portfolio_list = QListWidget()
        self.portfolio_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.portfolio_list, 1)

        add_row = QHBoxLayout()
        self.new_ticker_input = QLineEdit()
        self.new_ticker_input.setPlaceholderText("e.g. AAPL")
        add_row.addWidget(self.new_ticker_input, 1)
        self.btn_add_ticker = QPushButton("Add")
        self.btn_add_ticker.clicked.connect(self._add_ticker)
        add_row.addWidget(self.btn_add_ticker)
        layout.addLayout(add_row)

        self.btn_remove_selected = QPushButton("Remove Selected")
        self.btn_remove_selected.clicked.connect(self._remove_selected_ticker)
        layout.addWidget(self.btn_remove_selected)

        btn_row = QHBoxLayout()
        self.btn_save_portfolio = QPushButton("Save")
        self.btn_save_portfolio.clicked.connect(self._save_portfolio)
        btn_row.addWidget(self.btn_save_portfolio)

        self.btn_run_alerts = QPushButton("Run Alerts")
        self.btn_run_alerts.clicked.connect(self._run_alerts)
        btn_row.addWidget(self.btn_run_alerts)
        layout.addLayout(btn_row)

        layout.addSpacing(10)
        layout.addWidget(QLabel("Telegram (config/app_config.json)"))
        self.telegram_status = QLabel("Disabled")
        self.telegram_status.setStyleSheet("color: #BDBDBD;")
        layout.addWidget(self.telegram_status)

        self.btn_open_config = QPushButton("Open Config Folder")
        self.btn_open_config.clicked.connect(self._open_config_folder)
        layout.addWidget(self.btn_open_config)

        layout.addStretch(1)
        footer = QLabel("Theme: Bloomberg/TradingView dark\nData: finvizfinance")
        footer.setStyleSheet("color: #616161; font-size: 11px;")
        layout.addWidget(footer)
        return frame

    def _build_main_area(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.topbar = QFrame()
        self.topbar.setObjectName("TopBar")
        top_layout = QHBoxLayout(self.topbar)
        top_layout.setContentsMargins(14, 12, 14, 12)
        top_layout.setSpacing(10)

        self.lbl_market = QLabel("SPY: -")
        self.lbl_market.setFont(QFont("Segoe UI", 10, 600))
        top_layout.addWidget(self.lbl_market)

        top_layout.addStretch(1)

        top_layout.addWidget(QLabel("Upside"))
        self.cmb_upside = QComboBox()
        self.cmb_upside.addItems(UPSIDE_OPTIONS)
        self.cmb_upside.currentIndexChanged.connect(self._apply_filters)
        top_layout.addWidget(self.cmb_upside)

        top_layout.addWidget(QLabel("Sector"))
        self.cmb_sector = QComboBox()
        self.cmb_sector.addItems(["All"])
        self.cmb_sector.currentIndexChanged.connect(self._apply_filters)
        top_layout.addWidget(self.cmb_sector)

        top_layout.addWidget(QLabel("Industry"))
        self.cmb_industry = QComboBox()
        self.cmb_industry.addItems(["All"])
        self.cmb_industry.currentIndexChanged.connect(self._apply_filters)
        top_layout.addWidget(self.cmb_industry)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._sync_and_refresh)
        top_layout.addWidget(self.btn_refresh)
        self.btn_live_refresh = QPushButton("Live Fetch")
        self.btn_live_refresh.clicked.connect(self._live_fetch)
        top_layout.addWidget(self.btn_live_refresh)

        layout.addWidget(self.topbar)

        self.table = QTableWidget(0, 10)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.table.setHorizontalHeaderLabels(
            [
                "Ticker",
                "Tier",
                "Buy+ Inst",
                "Recom",
                "W.Recom",
                "Price",
                "Target",
                "Upside",
                "Sector",
                "Industry",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        return container

    def _sync_and_refresh(self, initial: bool = False) -> None:
        try:
            self.config = backend.load_app_config(self.config_path)
            backend.try_update_latest_data_remote(self.config)

            if self.config.sync_on_start or not initial:
                self.dataset = backend.sync_latest_data(self.config, force_live_fetch=False)
            else:
                self.dataset = backend.load_json(self.config.data_file)

            rows = self.dataset.get("rows", []) or []
            screened = backend.screen_rows(rows)

            filters = backend.derive_filter_values(rows)
            self.sectors = filters["sectors"]
            self.industries = filters["industries"]
            self._refresh_filter_sources()

            self.filtered_rows = screened
            self._apply_filters()

            self._refresh_market_bar()
            self._refresh_sidebar_summary()
            self._refresh_telegram_status()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to sync/refresh.\n\n{e}")

    def _live_fetch(self) -> None:
        try:
            self.config = backend.load_app_config(self.config_path)
            self.dataset = backend.sync_latest_data(self.config, force_live_fetch=True)
            rows = self.dataset.get("rows", []) or []
            self.filtered_rows = backend.screen_rows(rows)
            filters = backend.derive_filter_values(rows)
            self.sectors = filters["sectors"]
            self.industries = filters["industries"]
            self._refresh_filter_sources()
            self._apply_filters()
            self._refresh_market_bar()
            QMessageBox.information(self, "Live Fetch", "Live data fetched and saved to data/latest_data.json")
        except Exception as e:
            QMessageBox.critical(self, "Live Fetch Error", str(e))

    def _refresh_filter_sources(self) -> None:
        current_sector = self.cmb_sector.currentText() if hasattr(self, "cmb_sector") else "All"
        current_industry = self.cmb_industry.currentText() if hasattr(self, "cmb_industry") else "All"

        self.cmb_sector.blockSignals(True)
        self.cmb_industry.blockSignals(True)
        self.cmb_sector.clear()
        self.cmb_industry.clear()
        self.cmb_sector.addItems(["All"] + self.sectors)
        self.cmb_industry.addItems(["All"] + self.industries)

        if current_sector in (["All"] + self.sectors):
            self.cmb_sector.setCurrentText(current_sector)
        if current_industry in (["All"] + self.industries):
            self.cmb_industry.setCurrentText(current_industry)
        self.cmb_sector.blockSignals(False)
        self.cmb_industry.blockSignals(False)

    def _refresh_market_bar(self) -> None:
        m = self.dataset.get("sp500_proxy", {}) or {}
        sym = m.get("symbol", "SPY")
        price = m.get("price")
        chg = m.get("change_pct")
        if price is None or chg is None:
            self.lbl_market.setText(f"{sym}: -")
            self.lbl_market.setStyleSheet("color: #E0E0E0;")
            return
        txt = f"{sym}: {price:.2f}  ({chg:+.2f}%)"
        self.lbl_market.setText(txt)
        self.lbl_market.setStyleSheet(f"color: {'#4CAF50' if chg >= 0 else '#F44336'};")

    def _refresh_sidebar_summary(self) -> None:
        self.portfolio_summary.setText(f"{len(self.portfolio)} tickers watched")

    def _reload_portfolio_list(self) -> None:
        if not hasattr(self, "portfolio_list"):
            return
        self.portfolio_list.clear()
        for t in self.portfolio:
            self.portfolio_list.addItem(QListWidgetItem(t))

    @staticmethod
    def _normalize_ticker(s: str) -> str:
        s = (s or "").strip().upper()
        # Finviz sometimes uses '-' instead of '.' for tickers.
        return s.replace(".", "-")

    def _persist_portfolio(self) -> None:
        self.portfolio_path.parent.mkdir(parents=True, exist_ok=True)
        self.portfolio_path.write_text(
            json.dumps({"tickers": self.portfolio}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._refresh_sidebar_summary()

    def _add_ticker(self) -> None:
        if not hasattr(self, "new_ticker_input"):
            return
        t = self._normalize_ticker(self.new_ticker_input.text())
        if not t:
            return
        if t not in self.portfolio:
            self.portfolio.append(t)
            self._persist_portfolio()
            self._reload_portfolio_list()
        self.new_ticker_input.setText("")

    def _remove_selected_ticker(self) -> None:
        if not hasattr(self, "portfolio_list"):
            return
        items = self.portfolio_list.selectedItems()
        if not items:
            return
        to_remove = {self._normalize_ticker(it.text()) for it in items}
        self.portfolio = [x for x in self.portfolio if x not in to_remove]
        self._persist_portfolio()
        self._reload_portfolio_list()

    def _refresh_telegram_status(self) -> None:
        enabled = self.config.telegram_enabled and bool(self.config.telegram_bot_token) and bool(self.config.telegram_chat_id)
        self.telegram_status.setText("Enabled" if enabled else "Disabled")
        self.telegram_status.setStyleSheet("color: #4CAF50;" if enabled else "color: #BDBDBD;")

    def _save_portfolio(self) -> None:
        # List modifications are already persisted in add/remove; this is a manual sync button.
        self._persist_portfolio()
        QMessageBox.information(self, "Saved", "Portfolio saved to config/portfolio.json.")

    def _run_alerts(self) -> None:
        try:
            events = backend.run_portfolio_alerts(self.config, self.portfolio, self.dataset)
            if not events:
                QMessageBox.information(self, "Alerts", "No portfolio changes detected.")
                return
            msg = "\n".join([backend.format_event_message(e) for e in events])
            QMessageBox.information(self, "Alerts", f"Detected events:\n\n{msg}")
        except Exception as e:
            QMessageBox.critical(self, "Alerts Error", f"Failed to run alerts.\n\n{e}")

    def _open_config_folder(self) -> None:
        folder = str(self.portfolio_path.parent.resolve())
        try:
            import os

            os.startfile(folder)  # type: ignore[attr-defined]
        except Exception:
            QMessageBox.information(self, "Config", f"Config folder:\n{folder}")

    def _apply_filters(self) -> None:
        rows = self.filtered_rows

        min_up = 0
        up_choice = self.cmb_upside.currentText()
        if up_choice.endswith("+") and up_choice != "All":
            try:
                min_up = int(up_choice.replace("%+", ""))
            except Exception:
                min_up = 0

        sector = self.cmb_sector.currentText()
        industry = self.cmb_industry.currentText()

        def ok(r: Dict[str, Any]) -> bool:
            u = r.get("upside_pct")
            if min_up > 0:
                if u is None or float(u) < float(min_up):
                    return False
            if sector != "All":
                if str(r.get("sector") or "").strip() != sector:
                    return False
            if industry != "All":
                if str(r.get("industry") or "").strip() != industry:
                    return False
            return True

        filtered = [r for r in rows if ok(r)]
        self._render_table(filtered)

    def _render_table(self, rows: List[Dict[str, Any]]) -> None:
        self.table.setRowCount(0)
        tier1_set = {x.lower() for x in self.config.tier1_institutions}

        def add_item(row: int, col: int, text: str, color: Optional[QColor] = None) -> None:
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if color is not None:
                item.setForeground(color)
            self.table.setItem(row, col, item)

        for r in rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)

            t = str(r.get("ticker") or "")
            inst = r.get("institutions") or []
            tier1_hit = False
            if isinstance(inst, list):
                for s in inst:
                    name = str((s or {}).get("institution") or "")
                    if name.strip().lower() in tier1_set and backend.rating_to_buy_or_better(str((s or {}).get("rating") or "")):
                        tier1_hit = True
                        break

            tier_badge = "★" if tier1_hit else ""
            add_item(row_idx, 0, t, GREEN if (r.get("upside_pct") or 0) >= 30 else None)
            add_item(row_idx, 1, tier_badge, QColor("#FFD54F") if tier1_hit else MUTED)
            add_item(row_idx, 2, str(r.get("buy_or_better_count") or 0), None)

            recom = backend.safe_float(r.get("recom_score"))
            wrecom = backend.safe_float(r.get("recom_score_weighted"))
            add_item(row_idx, 3, num_str(recom), None)
            add_item(row_idx, 4, num_str(wrecom), QColor("#FFD54F") if tier1_hit else MUTED)

            price = backend.safe_float(r.get("price"))
            target = backend.safe_float(r.get("target_price"))
            ups = backend.safe_float(r.get("upside_pct"))

            up_color = GREEN if (ups is not None and ups >= 30) else (MUTED if ups is None else QColor("#E0E0E0"))
            add_item(row_idx, 5, num_str(price), None)
            add_item(row_idx, 6, num_str(target), None)
            add_item(row_idx, 7, pct_str(ups), up_color)

            add_item(row_idx, 8, str(r.get("sector") or "-"), MUTED)
            add_item(row_idx, 9, str(r.get("industry") or "-"), MUTED)


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_DARK)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

