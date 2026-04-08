# Expense Tracker

A full-featured personal budget tracker with category limits, visual charts, and CSV export. Built with CustomTkinter and SQLite — fully local, no accounts required.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-6C63FF) ![SQLite](https://img.shields.io/badge/Storage-SQLite-green)

## Features

- **Add / Edit / Delete** expenses with date, amount, category, and description
- **10 default categories** (Housing, Food, Transportation, etc.) with color coding
- **Monthly budget limits** — set per-category spending caps
- **Visual charts** — donut chart by category + bar chart with budget limit lines
- **Budget progress bars** — see exactly how close you are to each limit, with over-budget warnings
- **Month navigation** — browse any past or future month
- **Category filter** — view expenses for a single category
- **CSV export** — export the current month's expenses to a spreadsheet
- **SQLite storage** — all data saved locally in `expenses.db`

## Installation

```bash
pip install customtkinter pillow
```

## Usage

```bash
python expense_tracker.py
```

## Data

All data is stored in `expenses.db` in the same folder as the script. To back up your data, just copy that file.

## CSV Export

Click **Export CSV** in the header to save the current month's expenses as a `.csv` file — importable into Excel, Google Sheets, or any spreadsheet app.
