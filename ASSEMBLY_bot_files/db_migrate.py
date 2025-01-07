"""
Script to migrate `notes` column in `play_keys` from old JSON-list format
to the new structured JSON with `notes`, `offenses`, and `warnings`.
"""
import json
import re
import logging
from typing import List, Dict, Optional
import mysql.connector
from mysql.connector import MySQLConnection
from dateutil import parser
from ASSEMBLY_botSettings import *

# ─── CONFIGURATION ──────────────────────────────────────────────────────────────
DB_CONFIG = {
        'host': DATABASE_IP,
        'user': DATABASE_USER,
        'password': DATABASE_PASS,
        'database': DATABASE_NAME
    }
ISO_DATE_PATTERN   = re.compile(r'Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[^,)]*)')
SHORT_DATE_PATTERN = re.compile(r'\((\d{1,2}/\d{1,2}/\d{2,4})\)')
# ────────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def extract_timestamp(note_text: str) -> Optional[int]:
    """
    Extract a UNIX timestamp from note_text.
    Supports ISO-style dates after 'Date:' or short dates in parentheses.
    """
    m = ISO_DATE_PATTERN.search(note_text)
    if m:
        return int(parser.parse(m.group(1)).timestamp())

    m = SHORT_DATE_PATTERN.search(note_text)
    if m:
        return int(parser.parse(m.group(1)).timestamp())

    return None


def migrate_old_notes(old_notes: List[Dict]) -> List[Dict]:
    """
    Convert old-format notes (list of {"id":…, "note":…})
    to new-format entries [{'timestamp':…, 'note':…}, …].
    """
    migrated: List[Dict] = []
    for entry in old_notes:
        text = entry.get('note', '').strip()
        ts = extract_timestamp(text)
        if ts is not None:
            migrated.append({'timestamp': ts, 'note': text})
    return migrated


def fetch_play_keys(conn: MySQLConnection) -> List[Dict]:
    """Retrieve all `id, notes` rows from play_keys."""
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, notes FROM play_keys")
    rows = cur.fetchall()
    cur.close()
    return rows


def update_notes_column(conn: MySQLConnection, pk_id: int, payload: str) -> None:
    """Update the `notes` JSON for a single play_keys record."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE play_keys SET notes = %s WHERE id = %s",
        (payload, pk_id)
    )
    cur.close()


def main():
    """Main migration orchestration."""
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        rows = fetch_play_keys(conn)
        logging.info(f"Fetched {len(rows)} rows")

        for row in rows:
            pk_id = row['id']
            blob = row['notes']
            if not blob:
                continue  # skip NULL or empty

            try:
                data = json.loads(blob)
            except json.JSONDecodeError as e:
                logging.warning(f"Row {pk_id}: invalid JSON ({e}), skipping")
                continue

            # skip if already migrated
            if isinstance(data, dict) and 'notes' in data:
                logging.debug(f"Row {pk_id}: already new format")
                continue

            if not isinstance(data, list):
                logging.warning(f"Row {pk_id}: unexpected structure, skipping")
                continue

            new_notes = migrate_old_notes(data)
            new_struct = {'notes': new_notes, 'offenses': [], 'warnings': []}
            payload = json.dumps(new_struct, ensure_ascii=False)

            update_notes_column(conn, pk_id, payload)
            logging.info(f"Row {pk_id}: migrated {len(new_notes)} notes")

        conn.commit()
        logging.info("All done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
