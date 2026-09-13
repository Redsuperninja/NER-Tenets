"""
etl/run_query.py

Runs a single .sql file (e.g. dev/sql/queries/*.sql) against either load
target and prints the results as a simple padded table. Both targets share
the same analytics.vw_net_effective_rent shape (see sql/03_analytics.sql /
dev/sql/analytics.sql), so the same query file works against either one.

Run directly:
    python etl/run_query.py dev/sql/queries/NER_BY_VALUE.sql --target snowflake
    python etl/run_query.py dev/sql/queries/NER_BY_VALUE.sql --target dev
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl.connectors import CONNECTORS, connect

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _print_table(columns: list[str], rows: list[tuple]) -> None:
    if not rows:
        print("(no rows)")
        return

    widths = [
        max(len(str(col)), *(len(str(row[i])) for row in rows))
        for i, col in enumerate(columns)
    ]
    def fmt(values: list) -> str:
        return " | ".join(str(v).ljust(w) for v, w in zip(values, widths))

    print(fmt(columns))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(fmt(list(row)))


def run_query(target: str, sql_path: Path) -> None:
    query = sql_path.read_text()

    conn = connect(target)
    try:
        cur = conn.cursor()
        try:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
        finally:
            cur.close()
    finally:
        conn.close()

    log.info("Ran %s against target=%s, %d row(s)", sql_path, target, len(rows))
    _print_table(columns, rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql_file", type=Path, help="Path to a .sql file to run.")
    parser.add_argument(
        "--target",
        choices=list(CONNECTORS),
        default="dev",
        help="Which target to query (default: dev).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if not args.sql_file.exists():
        raise FileNotFoundError(f"{args.sql_file} not found")
    run_query(args.target, args.sql_file)
