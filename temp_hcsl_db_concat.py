#!/usr/bin/env python3
"""Merge account and play key data from one database into another.

This script copies rows from the ``accounts`` and ``play_keys`` tables of a
source database into a destination database while keeping the relationships
between the two tables intact.  All migrated identifiers are assigned from a
configurable offset (default: 2000) so that imported rows are easy to recognize
in the destination database and do not collide with existing records.

Both databases are expected to expose a MySQL-compatible interface.  The
script relies on :mod:`mysql.connector` which is provided by the
``mysql-connector-python`` package.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Sequence, Set, Tuple

try:
    import mysql.connector
    from mysql.connector.connection import MySQLConnection
    from mysql.connector.cursor import MySQLCursorDict
except ImportError as exc:  # pragma: no cover - import guard
    print(
        "This script requires the 'mysql-connector-python' package.\n"
        "Install it with 'pip install mysql-connector-python' and try again.",
        file=sys.stderr,
    )
    raise


@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Update these constants to match your local environment.  The script will
# connect to the ``SOURCE_DB`` and copy the ``accounts`` and ``play_keys``
# tables into ``DESTINATION_DB`` while applying the offset defined by
# ``ID_OFFSET``.
SOURCE_DB = DBConfig(
    host="localhost",
    port=3306,
    user="darkflame",
    password="passwordHERE",
    database="darkflame",
)

DESTINATION_DB = DBConfig(
    host="localhost",
    port=3306,
    user="darkflame",
    password="passwordHERE",
    database="darkflameBLU",
)

# All migrated identifiers will be allocated starting from this value to make
# it easy to spot the imported rows.
ID_OFFSET = 2000

# Set to ``True`` to preview the number of rows that would be inserted without
# modifying the destination database.
DRY_RUN = False


@contextmanager
def connect_db(config: DBConfig) -> Iterator[MySQLConnection]:
    connection = mysql.connector.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        autocommit=False,
    )
    try:
        yield connection
    finally:
        connection.close()


def fetch_all(cursor: MySQLCursorDict, query: str) -> List[dict]:
    cursor.execute(query)
    return list(cursor.fetchall())


class IDAllocator:
    """Allocate unique identifiers starting from a given offset."""

    def __init__(self, taken: Set[int], start: int) -> None:
        self._taken = set(taken)
        self._next_candidate = start

    def allocate(self) -> int:
        while self._next_candidate in self._taken:
            self._next_candidate += 1

        new_id = self._next_candidate
        self._taken.add(new_id)
        self._next_candidate += 1
        return new_id


def build_play_key_plan(
    src_rows: Sequence[dict],
    dest_rows: Sequence[dict],
    offset: int,
) -> Tuple[List[Tuple], Dict[int, int]]:
    dest_ids = {row["id"] for row in dest_rows}
    allocator = IDAllocator(dest_ids, offset)
    dest_key_lookup = {row["key_string"]: row["id"] for row in dest_rows}

    planned_rows: List[Tuple] = []
    id_map: Dict[int, int] = {}

    for row in src_rows:
        existing_id = dest_key_lookup.get(row["key_string"])
        if existing_id is not None:
            id_map[row["id"]] = existing_id
            continue

        new_id = allocator.allocate()

        planned_rows.append(
            (
                new_id,
                row["key_string"],
                row["key_uses"],
                row["created_at"],
                row["active"],
            )
        )
        id_map[row["id"]] = new_id
        dest_key_lookup[row["key_string"]] = new_id

    return planned_rows, id_map


def _normalize_account_name(name: str) -> str:
    """Return a normalized representation of an account name.

    MySQL's default collations compare ``VARCHAR`` columns case-insensitively,
    which means values such as ``"Foo"`` and ``"foo"`` are considered the same
    when constrained by a unique index.  Without applying the same
    normalization in Python we may attempt to insert a duplicate name even when
    the destination table already contains a matching record with different
    casing.  Trimming whitespace mirrors how MySQL handles equality checks on
    ``VARCHAR`` columns in most collations.
    """

    return name.strip().casefold()


def build_account_plan(
    src_rows: Sequence[dict],
    dest_rows: Sequence[dict],
    offset: int,
    play_key_id_map: Dict[int, int],
) -> Tuple[List[Tuple], Dict[int, int]]:
    dest_ids = {row["id"] for row in dest_rows}
    allocator = IDAllocator(dest_ids, offset)
    dest_names = {_normalize_account_name(row["name"]): row["id"] for row in dest_rows}

    planned_rows: List[Tuple] = []
    id_map: Dict[int, int] = {}

    for row in src_rows:
        normalized_name = _normalize_account_name(row["name"])

        if normalized_name in dest_names:
            existing_id = dest_names[normalized_name]
            id_map[row["id"]] = existing_id
            print(
                f"Skipping account '{row['name']}' because it already exists in the destination (id={existing_id})."
            )
            continue

        new_id = allocator.allocate()

        play_key_id = row["play_key_id"]
        if play_key_id in play_key_id_map:
            mapped_play_key_id = play_key_id_map[play_key_id]
        elif play_key_id in (0, None):
            mapped_play_key_id = play_key_id
        else:
            raise ValueError(
                f"Account '{row['name']}' references play_key_id={play_key_id}, but that key was not copied."
            )

        planned_rows.append(
            (
                new_id,
                row["name"],
                row["password"],
                row["gm_level"],
                row["locked"],
                row["banned"],
                mapped_play_key_id,
                row["created_at"],
                row["mute_expire"],
            )
        )
        id_map[row["id"]] = new_id
        dest_names[normalized_name] = new_id

    return planned_rows, id_map


def insert_rows(cursor: MySQLCursorDict, query: str, rows: Iterable[Tuple]) -> None:
    if not rows:
        return
    cursor.executemany(query, list(rows))


def main() -> int:
    with connect_db(SOURCE_DB) as src_conn, connect_db(DESTINATION_DB) as dest_conn:
        src_cur = src_conn.cursor(dictionary=True)
        dest_cur = dest_conn.cursor(dictionary=True)

        src_play_keys = fetch_all(src_cur, "SELECT * FROM play_keys")
        src_accounts = fetch_all(src_cur, "SELECT * FROM accounts")

        dest_play_keys = fetch_all(dest_cur, "SELECT * FROM play_keys")
        dest_accounts = fetch_all(dest_cur, "SELECT * FROM accounts")

        play_key_plan, play_key_id_map = build_play_key_plan(src_play_keys, dest_play_keys, ID_OFFSET)
        account_plan, _ = build_account_plan(src_accounts, dest_accounts, ID_OFFSET, play_key_id_map)

        print(f"Prepared to insert {len(play_key_plan)} play_keys and {len(account_plan)} accounts.")
        if DRY_RUN:
            print("Dry run requested – no changes were made.")
            return 0

        try:
            insert_rows(
                dest_cur,
                """
                INSERT INTO play_keys (id, key_string, key_uses, created_at, active)
                VALUES (%s, %s, %s, %s, %s)
                """,
                play_key_plan,
            )

            insert_rows(
                dest_cur,
                """
                INSERT INTO accounts (id, name, password, gm_level, locked, banned, play_key_id, created_at, mute_expire)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                account_plan,
            )

            dest_conn.commit()
        except Exception:
            dest_conn.rollback()
            raise

    print("Merge completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())