"""SQLite persistence for normalized submissions.

The MVP stores per-entity DataFrames as tables in a single local SQLite
database — zero-config and fully offline. PostgreSQL remains the documented
production target (see phases.md); nothing here is SQLite-specific beyond
the connection URL.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd
from sqlalchemy import create_engine

TABLE_NAMES = (
    "cse_metadata",
    "alerts",
    "investigations",
    "escalations",
    "cases",
    "assets",
)

DEFAULT_DB = Path("data/sat_sa.db")


def get_engine(db_path: Union[str, Path] = DEFAULT_DB):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}")


def _serialize_containers(df: pd.DataFrame) -> pd.DataFrame:
    """JSON-encode dict/list cells (SQLite cannot bind containers).

    Canonical models hold real dicts/lists; storage is the serialization
    boundary.
    """
    df = df.copy()
    for col in df.columns:
        mask = df[col].map(lambda v: isinstance(v, (dict, list)))
        if mask.any():
            df.loc[mask, col] = df.loc[mask, col].map(json.dumps)
    return df


def save_frames(
    frames: Dict[str, pd.DataFrame],
    db_path: Union[str, Path] = DEFAULT_DB,
    if_exists: str = "replace",
) -> Dict[str, int]:
    """Write per-entity frames to SQLite. Returns table -> row counts."""
    engine = get_engine(db_path)
    counts: Dict[str, int] = {}
    with engine.begin() as conn:
        for name in TABLE_NAMES:
            df = frames.get(name)
            if df is None:
                continue
            _serialize_containers(df).to_sql(name, conn, if_exists=if_exists, index=False)
            counts[name] = len(df)
    return counts


def load_table(
    name: str,
    db_path: Union[str, Path] = DEFAULT_DB,
    cse_id: Optional[str] = None,
) -> pd.DataFrame:
    """Read one table back; optionally filter to a single CSE."""
    engine = get_engine(db_path)
    query = f"SELECT * FROM {name}"  # noqa: S608 (name from TABLE_NAMES only)
    params = {}
    if cse_id is not None:
        query += " WHERE cse_id = :cse_id"
        params["cse_id"] = cse_id
    return pd.read_sql(query, engine, params=params)


def table_counts(db_path: Union[str, Path] = DEFAULT_DB) -> Dict[str, int]:
    engine = get_engine(db_path)
    counts: Dict[str, int] = {}
    with engine.connect() as conn:
        for name in TABLE_NAMES:
            try:
                counts[name] = int(pd.read_sql(f"SELECT COUNT(*) AS n FROM {name}", conn)["n"][0])  # noqa: E501, S608
            except Exception:
                counts[name] = 0
    return counts
