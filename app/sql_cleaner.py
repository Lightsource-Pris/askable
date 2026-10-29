#!/usr/bin/env python3
"""
sql_cleaner - Clean and normalize SQL dumps into SQLite
"""

import re
import sqlite3
from pathlib import Path

INPUT_FILE = Path("backup.sql")
OUTPUT_DB = Path("cleaned.db")
REPORT_FILE = Path("report.txt")

PREFIXES = ("sql_", "asp_", "dbo_")


def clean_name(name: str) -> str:
    """Currently only removes prefixes. Missing snake_case conversion."""
    original = name.strip().strip("[]`\"")
    lower = original.lower()
    for prefix in PREFIXES:
        if lower.startswith(prefix):
            original = original[len(prefix):]
            break
    return original   # <-- BUG: should also convert to snake_case


def parse_sql_dump(content: str):
    tables = {}

    # Very naive CREATE TABLE parsing
    create_pattern = re.compile(
        r'CREATE\s+TABLE\s+([`\[\]\w\.]+)\s*\((.*?)\)\s*;',
        re.IGNORECASE | re.DOTALL
    )

    for match in create_pattern.finditer(content):
        raw_table = match.group(1).strip()
        table_name = clean_name(raw_table.split(".")[-1])
        cols_block = match.group(2)

        columns = []
        for line in cols_block.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY", "KEY", "CONSTRAINT")):
                continue
            col_match = re.match(r'([`\[\]\w]+)', line)
            if col_match:
                # BUG: columns are not cleaned at all
                columns.append(col_match.group(1).strip("[]`\""))

        if columns:
            tables[table_name] = {"columns": columns, "rows": []}

    # Naive INSERT parsing (breaks on multi-line and many edge cases)
    insert_pattern = re.compile(
        r'INSERT\s+INTO\s+([`\[\]\w\.]+)\s*VALUES\s*(.*?);',
        re.IGNORECASE | re.DOTALL
    )

    for match in insert_pattern.finditer(content):
        raw_table = match.group(1).strip()
        table_name = clean_name(raw_table.split(".")[-1])
        if table_name not in tables:
            continue

        values_block = match.group(2).strip()
        # Extremely fragile split
        rows_raw = values_block.split("),")
        for r in rows_raw:
            r = r.strip().strip("()")
            values = [v.strip().strip("'\"") for v in r.split(",")]
            tables[table_name]["rows"].append(values)

    return tables


def main():
    content = INPUT_FILE.read_text(encoding="utf-8", errors="replace")
    tables = parse_sql_dump(content)

    if OUTPUT_DB.exists():
        OUTPUT_DB.unlink()

    conn = sqlite3.connect(OUTPUT_DB)
    cur = conn.cursor()

    report_lines = []
    total_tables = 0

    for table_name, data in tables.items():
        columns = data["columns"]
        rows = data["rows"]

        if not columns:
            continue

        total_tables += 1

        # BUG: does not add id primary key
        col_defs = [f'"{col}" TEXT' for col in columns]
        cur.execute(f'CREATE TABLE "{table_name}" ({", ".join(col_defs)})')

        # BUG: inserts everything, including rows that contain NULL
        for row in rows:
            placeholders = ", ".join(["?"] * len(row))
            cur.execute(
                f'INSERT INTO "{table_name}" VALUES ({placeholders})',
                row
            )

        # BUG: report is incomplete / incorrect
        report_lines.append(f"{table_name}: {len(rows)} rows")

    conn.commit()
    conn.close()

    report = [f"tables: {total_tables}"] + report_lines
    REPORT_FILE.write_text("\n".join(report) + "\n")


if __name__ == "__main__":
    main()