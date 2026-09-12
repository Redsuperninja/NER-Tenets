"""
etl/run_pipeline.py

Orchestrates the ETL pipeline end to end: extract -> transform -> load.
Each stage (extract.py, transform.py, load.py) already logs its own row
counts in/out, so a full run is auditable from the console output alone.

Run directly:
    python etl/run_pipeline.py --target dev
    python etl/run_pipeline.py --target snowflake
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl import extract, load, transform

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def run_pipeline(target: str) -> None:
    log.info("=== EXTRACT ===")
    extract.extract_all()

    log.info("=== TRANSFORM ===")
    transform.transform_all()

    log.info("=== LOAD (target=%s) ===", target)
    load.load_all(target)

    log.info("Pipeline complete (target=%s).", target)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=list(load.LOADERS),
        default=os.environ.get("LOAD_TARGET", "dev"),
        help="Which raw schema to load into (default: $LOAD_TARGET or 'dev').",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_pipeline(_parse_args().target)


#  var extract = Extract()
# var transform = Transform(extract)
# Load(transform)


# Load(transform(Extract())) 