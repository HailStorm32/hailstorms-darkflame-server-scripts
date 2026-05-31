"""
Replace one item LOT ID with another LOT ID in character inventory XML.

The script walks every row in `charxml`, parses the `xml_data` payload, and updates
matching inventory item `@l` values in the configured inventory containers. By
default, only the normal inventory (`@t="0"`) and vault inventory (`@t="1"`) are
processed.

Usage:
    python3 itemIdReplacer.py OLD_ITEM_ID NEW_ITEM_ID           # dry run
    python3 itemIdReplacer.py OLD_ITEM_ID NEW_ITEM_ID --commit  # write changes
"""
import argparse
import logging
from typing import Dict, Iterable, List, Tuple

import mysql.connector
from mysql.connector import MySQLConnection
import xmltodict

from contrabandCheckSettings import *


DB_CONFIG = {
    "host": DATABASE_IP,
    "user": DATABASE_USER,
    "password": DATABASE_PASS,
    "database": DATABASE_NAME,
}

TARGET_INVENTORY_TYPE_NAMES = ("Items", "Vault_Items")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def get_inventory_type_ids() -> Tuple[str, ...]:
    """Return main inventory and vault inventory IDs from contraband settings."""
    configured_inventory_types = globals().get("inventoryTypes", [])
    inventory_type_ids = [
        str(inventory_type["id"])
        for inventory_type in configured_inventory_types
        if inventory_type.get("name") in TARGET_INVENTORY_TYPE_NAMES
    ]

    if inventory_type_ids:
        return tuple(inventory_type_ids)

    return ("0", "1")


def as_list(value):
    """Normalize xmltodict values that may be a scalar, dict, list, or None."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def replace_item_ids(
    xml: str,
    old_item_id: int,
    new_item_id: int,
    inventory_type_ids: Iterable[str],
) -> Tuple[str, int]:
    """
    Replace item LOT IDs in configured inventory containers.

    Returns the rewritten XML and the number of individual inventory item entries
    changed. If no replacement is needed, the returned XML is the original string.
    """
    old_item_id = str(old_item_id)
    new_item_id = str(new_item_id)
    inventory_type_ids = set(
        str(inventory_type_id) for inventory_type_id in inventory_type_ids
    )

    xml_dict = xmltodict.parse(xml)
    replacements = 0

    inventory_types = as_list(
        xml_dict.get("obj", {}).get("inv", {}).get("items", {}).get("in")
    )
    for inventory_type in inventory_types:
        if not isinstance(inventory_type, dict):
            continue

        if inventory_type.get("@t") not in inventory_type_ids:
            continue

        for inventory_item in as_list(inventory_type.get("i")):
            if (
                isinstance(inventory_item, dict)
                and inventory_item.get("@l") == old_item_id
            ):
                inventory_item["@l"] = new_item_id
                replacements += 1

    if replacements == 0:
        return xml, 0

    has_xml_declaration = xml.lstrip().startswith("<?xml")
    return xmltodict.unparse(xml_dict, full_document=has_xml_declaration), replacements


def fetch_character_xml_rows(conn: MySQLConnection) -> List[Dict]:
    """Retrieve character XML rows with character names when available."""
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT charxml.id, charinfo.name, charxml.xml_data
        FROM charxml
        LEFT JOIN charinfo ON charinfo.id = charxml.id
        ORDER BY charxml.id
        """
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def update_character_xml(
    conn: MySQLConnection, character_id: int, xml_data: str
) -> None:
    """Update the XML payload for one character."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE charxml SET xml_data = %s WHERE id = %s",
        (xml_data, character_id),
    )
    cur.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replace one item LOT ID with another in inventory and vault inventory XML."
    )
    parser.add_argument("old_item_id", type=int, help="Item LOT ID to replace")
    parser.add_argument("new_item_id", type=int, help="Replacement item LOT ID")
    parser.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Write replacements to the database. Without this flag the "
            "script only reports what would change."
        ),
    )
    parser.add_argument(
        "--inventory-type",
        dest="inventory_type_ids",
        action="append",
        type=int,
        help=(
            "Inventory container type ID to process. Can be passed multiple "
            "times. Defaults to contrabandCheckSettings inventory types "
            "named Items and Vault_Items."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory_type_ids = (
        tuple(str(inventory_type_id) for inventory_type_id in args.inventory_type_ids)
        if args.inventory_type_ids
        else get_inventory_type_ids()
    )

    if args.old_item_id == args.new_item_id:
        logging.info("Old and new item IDs are identical; nothing to do.")
        return

    conn = mysql.connector.connect(**DB_CONFIG)
    changed_characters = 0
    total_replacements = 0

    try:
        rows = fetch_character_xml_rows(conn)
        logging.info(f"Fetched {len(rows)} character XML rows")
        logging.info(f"Searching inventory type IDs: {', '.join(inventory_type_ids)}")

        for row in rows:
            character_id = row["id"]
            character_name = row.get("name") or "<unknown>"
            xml = row.get("xml_data")
            if not xml:
                continue

            try:
                updated_xml, replacement_count = replace_item_ids(
                    xml,
                    args.old_item_id,
                    args.new_item_id,
                    inventory_type_ids,
                )
            except Exception as exc:
                logging.warning(
                    f"Character {character_id} ({character_name}): "
                    f"invalid XML ({exc}), skipping"
                )
                continue

            if replacement_count == 0:
                continue

            changed_characters += 1
            total_replacements += replacement_count
            logging.info(
                f"Character {character_id} ({character_name}): "
                f"replacing {replacement_count} item(s)"
            )

            if args.commit:
                update_character_xml(conn, character_id, updated_xml)

        if args.commit:
            conn.commit()
            logging.info(
                f"Committed {total_replacements} replacement(s) across "
                f"{changed_characters} character(s)."
            )
        else:
            conn.rollback()
            logging.info(
                f"Dry run complete: {total_replacements} replacement(s) "
                f"across {changed_characters} character(s)."
            )
            logging.info("Re-run with --commit to write these changes.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
