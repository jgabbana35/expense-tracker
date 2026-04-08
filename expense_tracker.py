"""
Expense Tracker
Full budget tracking with categories, limits, charts, and CSV export.
Dark theme via CustomTkinter.
"""

import csv
import json
import os
import sqlite3
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Colors ─────────────────────────────────────────────────────────────────────
BG_BASE      = "#0F1117"
BG_SURFACE   = "#1A1D27"
BG_SURFACE2  = "#222636"
BG_SIDEBAR   = "#0D0F18"
BORDER       = "#2D3748"
ACCENT       = "#6C63FF"
ACCENT_HOVER = "#5A52E0"
ACCENT_LIGHT = "#2D2B4E"
TEXT_PRIMARY = "#F1F5F9"
TEXT_SEC     = "#94A3B8"
TEXT_MUTED   = "#475569"
GREEN        = "#10B981"
GREEN_LIGHT  = "#0D2B1F"
ORANGE       = "#F59E0B"
ORANGE_LIGHT = "#2D2010"
RED          = "#EF4444"
RED_LIGHT    = "#2D1515"
CYAN         = "#00D4FF"

CATEGORY_COLORS = [
    "#6C63FF", "#10B981", "#F59E0B", "#EF4444", "#00D4FF",
    "#EC4899", "#8B5CF6", "#14B8A6", "#F97316", "#84CC16",
]

DEFAULT_CATEGORIES = [
    "Housing", "Food & Dining", "Transportation", "Healthcare",
    "Entertainment", "Shopping", "Utilities", "Education",
    "Savings", "Other",
]

DB_PATH = Path(__file__).parent / "expenses.db"


# ── Database ───────────────────────────────────────────────────────────────────

class DB:
    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._init()

    def _init(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS budgets (
                category    TEXT PRIMARY KEY,
                monthly_limit REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS categories (
                name        TEXT PRIMARY KEY,
                color       TEXT
            );
        """)
        # Seed default categories
        for i, cat in enumerate(DEFAULT_CATEGORIES):
            color = CATEGORY_COLORS[i % len(CATEGORY_COLORS)]
            self.conn.execute(
                "INSERT OR IGNORE INTO categories (name, color) VALUES (?, ?)", (cat, color)
            )
        self.conn.commit()

    # Expenses
    def add_expense(self, date_str: str, amount: float, category: str, description: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO expenses (date, amount, category, description) VALUES (?, ?, ?, ?)",
            (date_str, amount, category, description)
        )
        self.conn.commit()
        return cur.lastrowid

    def update_expense(self, eid: int, date_str: str, amount: float, category: str, description: str):
        self.conn.execute(
            "UPDATE expenses SET date=?, amount=?, category=?, description=? WHERE id=?",
            (date_str, amount, category, description, eid)
        )
        self.conn.commit()

    def delete_expense(self, eid: int):
        self.conn.execute("DELETE FROM expenses WHERE id=?", (eid,))
        self.conn.commit()

    def get_expenses(self, month: str | None = None, category: str | None = None) -> list[dict]:
        query = "SELECT id, date, amount, category, description FROM expenses WHERE 1=1"
        params: list = []
        if month:
            query += " AND strftime('%Y-%m', date) = ?"
            params.append(month)
        if category and category != "All":
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY date DESC, id DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [{"id": r[0], "date": r[1], "amount": r[2],
                 "category": r[3], "description": r[4] or ""} for r in rows]

    def get_monthly_totals(self, month: str) -> dict[str, float]:
        rows = self.conn.execute(
            "SELECT category, SUM(amount) FROM expenses WHERE strftime('%Y-%m', date)=? GROUP BY category",
            (month,)
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def get_total(self, month: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE strftime('%Y-%m', date)=?",
            (month,)
        ).fetchone()
        return row[0]

    # Budgets
    def set_budget(self, category: str, limit: float):
        self.conn.execute(
            "INSERT OR REPLACE INTO budgets (category, monthly_limit) VALUES (?, ?)",
            (category, limit)
        )
        self.conn.commit()

    def get_budgets(self) -> dict[str, float]:
        rows = self.conn.execute("SELECT category, monthly_limit FROM budgets").fetchall()
        return {r[0]: r[1] for r in rows}

    # Categories
    def get_categories(self) -> list[dict]:
        rows = self.conn.execute("SELECT name, color FROM categories ORDER BY name").fetchall()
        return [{"name": r[0], "color": r[1]} for r in rows]

    def add_category(self, name: str, color: str):
        self.conn.execute("INSERT OR IGNORE INTO categories (name, color) VALUES (?, ?)", (name, color))
        self.conn.commit()

    # CSV export
    def export_csv(self, path: str, month: str | None = None):
        expenses = self.get_expenses(month=month)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "date", "amount", "category", "description"])
            writer.writeheader()
            writer.writerows(expenses)


# ── Mini bar chart (pure tkinter canvas) ──────────────────────────────────────

class MiniBarChart(tk.Canvas):
    def __init__(self, parent, data: dict[str, float], colors: dict[str, str],
                 budgets: dict[str, float], width=420, height=200, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=BG_SURFACE2, highlightthickness=0, **kwargs)
        self._draw(data, colors, budgets, width, height)

    def _draw(self, data, colors, budgets, W, H):
        if not data:
            self.create_text(W // 2, H // 2, text="No data this month",
                             fill=TEXT_MUTED, font=("Segoe UI", 11))
            return
        pad_l, pad_r, pad_t, pad_b = 10, 10, 20, 50
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b
        max_val = max(data.values()) * 1.15 or 1

        n    = len(data)
        bw   = max(8, int(chart_w / n) - 8)
        gap  = (chart_w - n * bw) // (n + 1)

        for i, (cat, val) in enumerate(data.items()):
            x1 = pad_l + gap + i * (bw + gap)
            bar_h = int((val / max_val) * chart_h)
            y1 = pad_t + chart_h - bar_h
            y2 = pad_t + chart_h
            color = colors.get(cat, ACCENT)
            # Over budget — highlight in red
            budget = budgets.get(cat)
            fill = RED if (budget and val > budget) else color
            self.create_rectangle(x1, y1, x1 + bw, y2, fill=fill, outline="", width=0)
            # Budget line
            if budget and budget <= max_val * 1.1:
                by = pad_t + chart_h - int((budget / max_val) * chart_h)
                self.create_line(x1 - 2, by, x1 + bw + 2, by,
                                 fill=ORANGE, width=1, dash=(3, 2))
            # Value label
            self.create_text(x1 + bw // 2, y1 - 4,
                             text=f"${val:.0f}", fill=TEXT_SEC,
                             font=("Segoe UI", 8), anchor="s")
            # Category label (rotated via truncation)
            label = cat[:8] + ("…" if len(cat) > 8 else "")
            self.create_text(x1 + bw // 2, y2 + 6, text=label,
                             fill=TEXT_MUTED, font=("Segoe UI", 8),
                             angle=0, anchor="n")

        # Baseline
        self.create_line(pad_l, pad_t + chart_h, W - pad_r, pad_t + chart_h,
                         fill=BORDER, width=1)


# ── Donut chart ────────────────────────────────────────────────────────────────

class DonutChart(tk.Canvas):
    def __init__(self, parent, data: dict[str, float], colors: dict[str, str],
                 size=200, **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=BG_SURFACE, highlightthickness=0, **kwargs)
        self._draw(data, colors, size)

    def _draw(self, data, colors, size):
        total = sum(data.values())
        if not total:
            self.create_text(size // 2, size // 2, text="No data",
                             fill=TEXT_MUTED, font=("Segoe UI", 10))
            return
        pad = 20
        x0, y0, x1, y1 = pad, pad, size - pad, size - pad
        start = -90.0
        for cat, val in data.items():
            extent = (val / total) * 360
            color  = colors.get(cat, ACCENT)
            self.create_arc(x0, y0, x1, y1, start=start, extent=extent,
                            fill=color, outline=BG_SURFACE, width=2, style="pieslice")
            start += extent
        # Donut hole
        hole = 50
        hx0, hy0 = size // 2 - hole, size // 2 - hole
        hx1, hy1 = size // 2 + hole, size // 2 + hole
        self.create_oval(hx0, hy0, hx1, hy1, fill=BG_SURFACE, outline=BG_SURFACE)
        # Total in center
        self.create_text(size // 2, size // 2, text=f"${total:,.0f}",
                         fill=TEXT_PRIMARY, font=("Segoe UI", 11, "bold"))


# ── Add/Edit Expense Dialog ────────────────────────────────────────────────────

class ExpenseDialog(ctk.CTkToplevel):
    def __init__(self, parent, categories: list[str], expense: dict | None = None):
        super().__init__(parent)
        self.title("Edit Expense" if expense else "Add Expense")
        self.geometry("420x340")
        self.resizable(False, False)
        self.configure(fg_color=BG_SURFACE)
        self.grab_set()
        self.result: dict | None = None
        self._build(categories, expense)

    def _build(self, categories: list[str], expense: dict | None):
        pad = {"padx": 20, "pady": 6}

        ctk.CTkLabel(self, text="Date (YYYY-MM-DD)",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=TEXT_SEC, fg_color=BG_SURFACE).pack(anchor="w", **pad)
        self._date = ctk.CTkEntry(self, fg_color=BG_SURFACE2, text_color=TEXT_PRIMARY,
                                   border_color=BORDER, height=36, corner_radius=8)
        self._date.insert(0, expense["date"] if expense else date.today().isoformat())
        self._date.pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkLabel(self, text="Amount ($)",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=TEXT_SEC, fg_color=BG_SURFACE).pack(anchor="w", **pad)
        self._amount = ctk.CTkEntry(self, fg_color=BG_SURFACE2, text_color=TEXT_PRIMARY,
                                     border_color=BORDER, height=36, corner_radius=8)
        self._amount.insert(0, str(expense["amount"]) if expense else "")
        self._amount.pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkLabel(self, text="Category",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=TEXT_SEC, fg_color=BG_SURFACE).pack(anchor="w", **pad)
        self._cat = ctk.CTkOptionMenu(self, values=categories,
                                       fg_color=BG_SURFACE2, text_color=TEXT_PRIMARY,
                                       button_color=ACCENT, button_hover_color=ACCENT_HOVER,
                                       dropdown_fg_color=BG_SURFACE2,
                                       dropdown_text_color=TEXT_PRIMARY,
                                       corner_radius=8, height=36)
        if expense:
            self._cat.set(expense["category"])
        self._cat.pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkLabel(self, text="Description (optional)",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=TEXT_SEC, fg_color=BG_SURFACE).pack(anchor="w", **pad)
        self._desc = ctk.CTkEntry(self, fg_color=BG_SURFACE2, text_color=TEXT_PRIMARY,
                                   border_color=BORDER, height=36, corner_radius=8)
        self._desc.insert(0, expense["description"] if expense else "")
        self._desc.pack(fill="x", padx=20, pady=(0, 12))

        btn_row = ctk.CTkFrame(self, fg_color=BG_SURFACE)
        btn_row.pack(fill="x", padx=20)
        ctk.CTkButton(btn_row, text="Save",
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      text_color=TEXT_PRIMARY, corner_radius=8, height=36,
                      command=self._save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Cancel",
                      fg_color=BG_SURFACE2, hover_color=BORDER,
                      text_color=TEXT_SEC, corner_radius=8, height=36,
                      command=self.destroy).pack(side="left")

    def _save(self):
        try:
            d = self._date.get().strip()
            datetime.strptime(d, "%Y-%m-%d")
            a = float(self._amount.get().strip().replace("$", "").replace(",", ""))
            if a <= 0:
                raise ValueError("Amount must be positive")
        except ValueError as e:
            messagebox.showerror("Invalid Input", str(e), parent=self)
            return
        self.result = {
            "date":        d,
            "amount":      round(a, 2),
            "category":    self._cat.get(),
            "description": self._desc.get().strip(),
        }
        self.destroy()


# ── Budget Settings Dialog ─────────────────────────────────────────────────────

class BudgetDialog(ctk.CTkToplevel):
    def __init__(self, parent, categories: list[str], budgets: dict[str, float]):
        super().__init__(parent)
        self.title("Monthly Budget Limits")
        self.geometry("380x480")
        self.resizable(False, True)
        self.configure(fg_color=BG_SURFACE)
        self.grab_set()
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._build(categories, budgets)

    def _build(self, categories, budgets):
        ctk.CTkLabel(self, text="Set Monthly Limits",
                     font=ctk.CTkFont("Segoe UI", 14, "bold"),
                     text_color=TEXT_PRIMARY, fg_color=BG_SURFACE).pack(pady=(16, 4), padx=20, anchor="w")
        ctk.CTkLabel(self, text="Leave blank for no limit. Over-limit categories show in red.",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_MUTED, fg_color=BG_SURFACE,
                     wraplength=340).pack(padx=20, anchor="w", pady=(0, 12))

        scroll = ctk.CTkScrollableFrame(self, fg_color=BG_SURFACE)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        for cat in categories:
            row = ctk.CTkFrame(scroll, fg_color=BG_SURFACE)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=cat, font=ctk.CTkFont("Segoe UI", 12),
                         text_color=TEXT_PRIMARY, fg_color=BG_SURFACE,
                         width=160, anchor="w").pack(side="left")
            entry = ctk.CTkEntry(row, fg_color=BG_SURFACE2, text_color=TEXT_PRIMARY,
                                  border_color=BORDER, height=30, width=110,
                                  corner_radius=6, placeholder_text="$ no limit")
            if cat in budgets:
                entry.insert(0, str(budgets[cat]))
            entry.pack(side="left", padx=8)
            self._entries[cat] = entry

        btn_row = ctk.CTkFrame(self, fg_color=BG_SURFACE)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(btn_row, text="Save Budgets",
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      text_color=TEXT_PRIMARY, corner_radius=8, height=36,
                      command=self._save).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Cancel",
                      fg_color=BG_SURFACE2, hover_color=BORDER,
                      text_color=TEXT_SEC, corner_radius=8, height=36,
                      command=self.destroy).pack(side="left")

    def _save(self):
        result: dict[str, float] = {}
        for cat, entry in self._entries.items():
            val = entry.get().strip().replace("$", "").replace(",", "")
            if val:
                try:
                    result[cat] = float(val)
                except ValueError:
                    messagebox.showerror("Invalid", f"Invalid amount for {cat}", parent=self)
                    return
        self.result = result
        self.destroy()


# ── Main App ───────────────────────────────────────────────────────────────────

class ExpenseTracker(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Expense Tracker")
        self.geometry("1300x860")
        self.minsize(1000, 680)
        self.configure(fg_color=BG_BASE)

        self.db = DB()
        self._current_month = date.today().strftime("%Y-%m")
        self._filter_cat = "All"
        self._expense_rows: list[dict] = []   # current displayed rows

        self._build()
        self._refresh()

    # ── Layout ─────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG_SURFACE, corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="💰 Expense Tracker",
                     font=ctk.CTkFont("Segoe UI", 20, "bold"),
                     text_color=TEXT_PRIMARY, fg_color=BG_SURFACE).pack(side="left", padx=20)

        # Month nav
        nav = ctk.CTkFrame(hdr, fg_color=BG_SURFACE)
        nav.pack(side="left", padx=20)
        ctk.CTkButton(nav, text="◀", width=32, height=30, corner_radius=6,
                      fg_color=BG_SURFACE2, hover_color=BORDER, text_color=TEXT_PRIMARY,
                      command=self._prev_month).pack(side="left", padx=2)
        self._month_lbl = ctk.CTkLabel(nav, text="", font=ctk.CTkFont("Segoe UI", 13, "bold"),
                                        text_color=ACCENT, fg_color=BG_SURFACE, width=110)
        self._month_lbl.pack(side="left", padx=4)
        ctk.CTkButton(nav, text="▶", width=32, height=30, corner_radius=6,
                      fg_color=BG_SURFACE2, hover_color=BORDER, text_color=TEXT_PRIMARY,
                      command=self._next_month).pack(side="left", padx=2)

        # Header buttons
        btns = ctk.CTkFrame(hdr, fg_color=BG_SURFACE)
        btns.pack(side="right", padx=16)
        ctk.CTkButton(btns, text="📊 Budgets", height=34, corner_radius=8,
                      fg_color=BG_SURFACE2, hover_color=BORDER, text_color=TEXT_SEC,
                      border_width=1, border_color=BORDER,
                      command=self._open_budgets).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="📥 Export CSV", height=34, corner_radius=8,
                      fg_color=BG_SURFACE2, hover_color=BORDER, text_color=TEXT_SEC,
                      border_width=1, border_color=BORDER,
                      command=self._export_csv).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="＋ Add Expense", height=34, corner_radius=8,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT_PRIMARY,
                      command=self._add_expense).pack(side="left", padx=4)

        # Body
        body = ctk.CTkFrame(self, fg_color=BG_BASE)
        body.pack(fill="both", expand=True, padx=14, pady=10)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left sidebar — summary + charts
        left = ctk.CTkScrollableFrame(body, fg_color=BG_BASE, width=320,
                                       scrollbar_button_color=BORDER,
                                       scrollbar_button_hover_color=ACCENT)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        self._left = left

        # Right — expense list
        right = ctk.CTkFrame(body, fg_color=BG_SURFACE, corner_radius=12,
                              border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self._build_list_panel(right)

    def _build_list_panel(self, parent):
        # Filter bar
        fbar = ctk.CTkFrame(parent, fg_color=BG_SURFACE)
        fbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        ctk.CTkLabel(fbar, text="Filter:",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=TEXT_MUTED, fg_color=BG_SURFACE).pack(side="left")
        cats = ["All"] + [c["name"] for c in self.db.get_categories()]
        self._filter_var = ctk.StringVar(value="All")
        self._filter_menu = ctk.CTkOptionMenu(
            fbar, values=cats, variable=self._filter_var,
            fg_color=BG_SURFACE2, text_color=TEXT_PRIMARY,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            dropdown_fg_color=BG_SURFACE2, dropdown_text_color=TEXT_PRIMARY,
            corner_radius=8, height=30, width=160,
            command=self._on_filter_change
        )
        self._filter_menu.pack(side="left", padx=8)

        # Column headers
        hdr = ctk.CTkFrame(parent, fg_color=BG_SURFACE2, corner_radius=0, height=34)
        hdr.grid(row=1, column=0, sticky="ew", padx=0)
        hdr.pack_propagate(False)
        hdr.columnconfigure(0, weight=0, minsize=90)
        hdr.columnconfigure(1, weight=0, minsize=90)
        hdr.columnconfigure(2, weight=0, minsize=160)
        hdr.columnconfigure(3, weight=1)
        hdr.columnconfigure(4, weight=0, minsize=80)
        for col, label in enumerate(["Date", "Amount", "Category", "Description", "Actions"]):
            ctk.CTkLabel(hdr, text=label,
                         font=ctk.CTkFont("Segoe UI", 11, "bold"),
                         text_color=TEXT_MUTED, fg_color=BG_SURFACE2
                         ).grid(row=0, column=col, sticky="w", padx=12, pady=8)

        # Scrollable list
        self._list_frame = ctk.CTkScrollableFrame(
            parent, fg_color=BG_SURFACE, corner_radius=0,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=ACCENT
        )
        self._list_frame.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        parent.rowconfigure(2, weight=1)

    # ── Sidebar rebuild ────────────────────────────────────────────────────

    def _rebuild_sidebar(self, totals: dict[str, float], budgets: dict[str, float],
                          cat_colors: dict[str, str]):
        for w in self._left.winfo_children():
            w.destroy()

        total_spent = sum(totals.values())
        total_budget = sum(budgets.values()) if budgets else 0

        # Total card
        card = ctk.CTkFrame(self._left, fg_color=BG_SURFACE, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(card, text="Total Spent",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_MUTED, fg_color=BG_SURFACE).pack(anchor="w", padx=14, pady=(12, 0))
        ctk.CTkLabel(card, text=f"${total_spent:,.2f}",
                     font=ctk.CTkFont("Segoe UI", 28, "bold"),
                     text_color=TEXT_PRIMARY, fg_color=BG_SURFACE).pack(anchor="w", padx=14)
        if total_budget:
            remaining = total_budget - total_spent
            r_color = GREEN if remaining >= 0 else RED
            ctk.CTkLabel(card, text=f"${remaining:,.2f} remaining of ${total_budget:,.0f} budget",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=r_color, fg_color=BG_SURFACE).pack(anchor="w", padx=14, pady=(2, 12))
        else:
            ctk.CTkLabel(card, text="No budget set — click Budgets to add limits",
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=TEXT_MUTED, fg_color=BG_SURFACE,
                         wraplength=260).pack(anchor="w", padx=14, pady=(2, 12))

        # Donut chart
        if totals:
            ctk.CTkLabel(self._left, text="Spending by Category",
                         font=ctk.CTkFont("Segoe UI", 12, "bold"),
                         text_color=TEXT_PRIMARY, fg_color=BG_BASE).pack(anchor="w", pady=(4, 2))
            donut_frame = ctk.CTkFrame(self._left, fg_color=BG_SURFACE, corner_radius=12,
                                        border_width=1, border_color=BORDER)
            donut_frame.pack(fill="x", pady=(0, 8))
            donut = DonutChart(donut_frame, totals, cat_colors, size=200)
            donut.pack(pady=10)
            # Legend
            for cat, val in sorted(totals.items(), key=lambda x: -x[1]):
                row = ctk.CTkFrame(donut_frame, fg_color=BG_SURFACE)
                row.pack(fill="x", padx=12, pady=1)
                dot_color = cat_colors.get(cat, ACCENT)
                ctk.CTkLabel(row, text="●", font=ctk.CTkFont("Segoe UI", 10),
                             text_color=dot_color, fg_color=BG_SURFACE).pack(side="left")
                ctk.CTkLabel(row, text=cat, font=ctk.CTkFont("Segoe UI", 11),
                             text_color=TEXT_SEC, fg_color=BG_SURFACE).pack(side="left", padx=4)
                ctk.CTkLabel(row, text=f"${val:,.2f}",
                             font=ctk.CTkFont("Segoe UI", 11, "bold"),
                             text_color=TEXT_PRIMARY, fg_color=BG_SURFACE).pack(side="right")

        # Bar chart
        if totals:
            ctk.CTkLabel(self._left, text="Category Bar Chart",
                         font=ctk.CTkFont("Segoe UI", 12, "bold"),
                         text_color=TEXT_PRIMARY, fg_color=BG_BASE).pack(anchor="w", pady=(8, 2))
            bar_frame = ctk.CTkFrame(self._left, fg_color=BG_SURFACE2, corner_radius=12,
                                      border_width=1, border_color=BORDER)
            bar_frame.pack(fill="x", pady=(0, 8))
            bar = MiniBarChart(bar_frame, totals, cat_colors, budgets,
                               width=290, height=180)
            bar.pack(padx=8, pady=8)
            if budgets:
                legend = ctk.CTkFrame(bar_frame, fg_color=BG_SURFACE2)
                legend.pack(fill="x", padx=10, pady=(0, 8))
                ctk.CTkLabel(legend, text="─── Budget limit",
                             font=ctk.CTkFont("Segoe UI", 9),
                             text_color=ORANGE, fg_color=BG_SURFACE2).pack(side="left")
                ctk.CTkLabel(legend, text="  ■ Over budget",
                             font=ctk.CTkFont("Segoe UI", 9),
                             text_color=RED, fg_color=BG_SURFACE2).pack(side="left", padx=8)

        # Budget progress bars
        if budgets:
            ctk.CTkLabel(self._left, text="Budget Progress",
                         font=ctk.CTkFont("Segoe UI", 12, "bold"),
                         text_color=TEXT_PRIMARY, fg_color=BG_BASE).pack(anchor="w", pady=(8, 2))
            prog_frame = ctk.CTkFrame(self._left, fg_color=BG_SURFACE, corner_radius=12,
                                       border_width=1, border_color=BORDER)
            prog_frame.pack(fill="x", pady=(0, 8))
            for cat, limit in budgets.items():
                spent = totals.get(cat, 0)
                pct   = min(spent / limit, 1.0) if limit else 0
                over  = spent > limit
                bar_color = RED if over else (ORANGE if pct > 0.8 else GREEN)
                row = ctk.CTkFrame(prog_frame, fg_color=BG_SURFACE)
                row.pack(fill="x", padx=12, pady=4)
                top = ctk.CTkFrame(row, fg_color=BG_SURFACE)
                top.pack(fill="x")
                ctk.CTkLabel(top, text=cat, font=ctk.CTkFont("Segoe UI", 11),
                             text_color=TEXT_PRIMARY, fg_color=BG_SURFACE).pack(side="left")
                status = f"${spent:,.2f} / ${limit:,.0f}"
                if over:
                    status += " ⚠ OVER"
                ctk.CTkLabel(top, text=status,
                             font=ctk.CTkFont("Segoe UI", 10),
                             text_color=bar_color, fg_color=BG_SURFACE).pack(side="right")
                bar_bg = ctk.CTkFrame(row, fg_color=BG_SURFACE2, corner_radius=4, height=6)
                bar_bg.pack(fill="x", pady=(2, 0))
                bar_bg.pack_propagate(False)
                ctk.CTkFrame(bar_bg, fg_color=bar_color, corner_radius=4, height=6
                             ).place(relx=0, rely=0, relwidth=pct, relheight=1)

    # ── List rebuild ───────────────────────────────────────────────────────

    def _rebuild_list(self, expenses: list[dict], cat_colors: dict[str, str]):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._expense_rows = expenses

        if not expenses:
            ctk.CTkLabel(self._list_frame,
                         text="No expenses found. Click '＋ Add Expense' to get started.",
                         font=ctk.CTkFont("Segoe UI", 13),
                         text_color=TEXT_MUTED, fg_color=BG_SURFACE).pack(pady=60)
            return

        for exp in expenses:
            row = ctk.CTkFrame(self._list_frame, fg_color=BG_SURFACE,
                               corner_radius=0, height=42)
            row.pack(fill="x")
            row.pack_propagate(False)
            row.columnconfigure(3, weight=1)

            # Hover effect
            def _enter(e, r=row): r.configure(fg_color=BG_SURFACE2)
            def _leave(e, r=row): r.configure(fg_color=BG_SURFACE)
            row.bind("<Enter>", _enter)
            row.bind("<Leave>", _leave)

            ctk.CTkLabel(row, text=exp["date"],
                         font=ctk.CTkFont("Segoe UI", 12),
                         text_color=TEXT_SEC, fg_color="transparent",
                         width=90).grid(row=0, column=0, sticky="w", padx=12)
            ctk.CTkLabel(row, text=f"${exp['amount']:,.2f}",
                         font=ctk.CTkFont("Segoe UI", 12, "bold"),
                         text_color=TEXT_PRIMARY, fg_color="transparent",
                         width=90).grid(row=0, column=1, sticky="w", padx=4)

            dot_color = cat_colors.get(exp["category"], ACCENT)
            cat_frame = ctk.CTkFrame(row, fg_color="transparent")
            cat_frame.grid(row=0, column=2, sticky="w", padx=4)
            ctk.CTkLabel(cat_frame, text="●",
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=dot_color, fg_color="transparent").pack(side="left")
            ctk.CTkLabel(cat_frame, text=exp["category"],
                         font=ctk.CTkFont("Segoe UI", 12),
                         text_color=TEXT_SEC, fg_color="transparent",
                         width=140, anchor="w").pack(side="left", padx=3)

            ctk.CTkLabel(row, text=exp["description"] or "—",
                         font=ctk.CTkFont("Segoe UI", 12),
                         text_color=TEXT_MUTED, fg_color="transparent",
                         anchor="w").grid(row=0, column=3, sticky="ew", padx=4)

            act = ctk.CTkFrame(row, fg_color="transparent")
            act.grid(row=0, column=4, sticky="e", padx=12)
            ctk.CTkButton(act, text="✏", width=28, height=26, corner_radius=6,
                          fg_color=ACCENT_LIGHT, hover_color=ACCENT, text_color=TEXT_PRIMARY,
                          command=lambda e=exp: self._edit_expense(e)).pack(side="left", padx=2)
            ctk.CTkButton(act, text="🗑", width=28, height=26, corner_radius=6,
                          fg_color=RED_LIGHT, hover_color=RED, text_color=TEXT_PRIMARY,
                          command=lambda e=exp: self._delete_expense(e)).pack(side="left", padx=2)

            # Separator
            ctk.CTkFrame(self._list_frame, fg_color=BORDER, height=1).pack(fill="x")

    # ── Actions ────────────────────────────────────────────────────────────

    def _refresh(self):
        y, m = self._current_month.split("-")
        self._month_lbl.configure(text=f"{date(int(y), int(m), 1).strftime('%B %Y')}")

        cats      = self.db.get_categories()
        cat_names = [c["name"] for c in cats]
        cat_colors = {c["name"]: c["color"] for c in cats}
        budgets   = self.db.get_budgets()
        totals    = self.db.get_monthly_totals(self._current_month)
        expenses  = self.db.get_expenses(month=self._current_month,
                                          category=self._filter_cat if self._filter_cat != "All" else None)

        self._rebuild_sidebar(totals, budgets, cat_colors)
        self._rebuild_list(expenses, cat_colors)

        # Refresh filter menu
        all_cats = ["All"] + cat_names
        self._filter_menu.configure(values=all_cats)

    def _prev_month(self):
        y, m = map(int, self._current_month.split("-"))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        self._current_month = f"{y:04d}-{m:02d}"
        self._refresh()

    def _next_month(self):
        y, m = map(int, self._current_month.split("-"))
        m += 1
        if m == 13:
            m, y = 1, y + 1
        self._current_month = f"{y:04d}-{m:02d}"
        self._refresh()

    def _on_filter_change(self, value: str):
        self._filter_cat = value
        self._refresh()

    def _add_expense(self):
        cats = [c["name"] for c in self.db.get_categories()]
        dlg  = ExpenseDialog(self, cats)
        self.wait_window(dlg)
        if dlg.result:
            self.db.add_expense(**dlg.result)
            self._refresh()

    def _edit_expense(self, exp: dict):
        cats = [c["name"] for c in self.db.get_categories()]
        dlg  = ExpenseDialog(self, cats, expense=exp)
        self.wait_window(dlg)
        if dlg.result:
            self.db.update_expense(exp["id"], **dlg.result)
            self._refresh()

    def _delete_expense(self, exp: dict):
        if messagebox.askyesno("Delete", f"Delete ${exp['amount']:.2f} — {exp['category']}?", parent=self):
            self.db.delete_expense(exp["id"])
            self._refresh()

    def _open_budgets(self):
        cats    = [c["name"] for c in self.db.get_categories()]
        budgets = self.db.get_budgets()
        dlg     = BudgetDialog(self, cats, budgets)
        self.wait_window(dlg)
        if hasattr(dlg, "result"):
            for cat, limit in dlg.result.items():
                self.db.set_budget(cat, limit)
            self._refresh()

    def _export_csv(self):
        y, m = self._current_month.split("-")
        default = f"expenses_{y}_{m}.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self.db.export_csv(path, month=self._current_month)
            messagebox.showinfo("Exported", f"Expenses saved to:\n{path}", parent=self)


# ── Entry ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ExpenseTracker()
    app.mainloop()
