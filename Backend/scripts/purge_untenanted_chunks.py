"""
Purge Untenanted Chunks Script
One-time cleanup script that scans the Qdrant vector database and deletes
every point lacking a verified user_id payload.
Does NOT assign orphans to any user account.
Requires the --confirm flag to execute actual point deletion.
"""

import argparse
import sys
import os

# Add parent directory (Backend) to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qdrant_client.http import models as qmodels
from app.core.config import settings
from app.services.vector_store import vector_store


def main():
    parser = argparse.ArgumentParser(description="Purge untenanted Qdrant chunks lacking user_id.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete untenanted chunks from Qdrant. Without this flag, runs in dry-run mode."
    )
    args = parser.parse_args()

    client = vector_store.client
    collection_name = vector_store.collection_name
    target_location = settings.QDRANT_URL if (settings.QDRANT_URL and str(settings.QDRANT_URL).strip()) else f"Local storage at {settings.QDRANT_PATH}"

    print("==================================================")
    print(f"Target Qdrant Location: {target_location}")
    print(f"Target Collection:      {collection_name}")
    print("==================================================")

    try:
        col_info = client.get_collection(collection_name=collection_name)
        total_points_estimate = col_info.points_count or 0
        print(f"Total points in collection (approx): {total_points_estimate}")
    except Exception as e:
        print(f"Error accessing collection '{collection_name}': {e}")
        sys.exit(1)

    print("Scanning points to identify untenanted chunks (missing or empty user_id)...")
    scroll_cursor = None
    all_orphan_ids = []
    total_scanned = 0
    tenanted_count = 0

    while True:
        records, next_cursor = client.scroll(
            collection_name=collection_name,
            limit=250,
            offset=scroll_cursor,
            with_payload=True,
            with_vectors=False
        )
        if not records:
            break

        for record in records:
            total_scanned += 1
            payload = record.payload or {}
            user_id = payload.get("user_id")
            if not user_id or not str(user_id).strip():
                all_orphan_ids.append(record.id)
            else:
                tenanted_count += 1

        if next_cursor is None:
            break
        scroll_cursor = next_cursor

    orphan_count = len(all_orphan_ids)
    print("\n--- BEFORE AUDIT SUMMARY ---")
    print(f"Total Points Scanned:     {total_scanned}")
    print(f"Tenanted Points (kept):    {tenanted_count}")
    print(f"Untenanted Points (found): {orphan_count}")
    print("----------------------------\n")

    if orphan_count == 0:
        print("No untenanted chunks found. Vector database is completely clean and isolated!")
        return

    if not args.confirm:
        print("DRY-RUN MODE: No points were deleted.")
        print("To permanently delete the untenanted points, re-run this script with the --confirm flag:")
        print("    python scripts/purge_untenanted_chunks.py --confirm")
        return

    print(f"Confirmed! Proceeding to delete {orphan_count} untenanted points in batches...")
    batch_size = 200
    deleted_count = 0

    for i in range(0, len(all_orphan_ids), batch_size):
        batch = all_orphan_ids[i:i + batch_size]
        client.delete(
            collection_name=collection_name,
            points_selector=qmodels.PointIdsList(points=batch)
        )
        deleted_count += len(batch)
        print(f"Deleted batch {i // batch_size + 1}: {deleted_count}/{orphan_count} points...")

    # Count after purge
    col_info_after = client.get_collection(collection_name=collection_name)
    points_after = col_info_after.points_count or 0

    print("\n--- AFTER PURGE SUMMARY ---")
    print(f"Untenanted Points Deleted: {deleted_count}")
    print(f"Remaining Collection Points: {points_after}")
    print("---------------------------\n")
    print("Untenanted chunks successfully purged!")


if __name__ == "__main__":
    main()
