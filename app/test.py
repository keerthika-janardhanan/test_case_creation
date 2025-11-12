# app/test.py
from app.vector_db import VectorDBClient

def check_vector_db_by_source_or_type(limit: int = 5):
    db = VectorDBClient()

    try:
        # fetch all docs (max 10000)
        all_docs = db.list_all(limit=10000)
    except Exception as e:
        print(f"❌ Error fetching Vector DB documents: {e}")
        return

    total_count = len(all_docs)
    print(f"\n📊 Total documents in Vector DB: {total_count}")

    # Breakdown by artifact_type
    counts_by_type = {}
    for doc in all_docs:
        meta = doc.get("metadata", {})
        dtype = meta.get("artifact_type", "unknown")
        counts_by_type[dtype] = counts_by_type.get(dtype, 0) + 1

    print("\n📂 Breakdown by type:")
    for dtype, count in counts_by_type.items():
        print(f"  - {dtype}: {count}")

    # Breakdown by source
    counts_by_source = {}
    for doc in all_docs:
        meta = doc.get("metadata", {})
        source = meta.get("source", "unknown")
        counts_by_source[source] = counts_by_source.get(source, 0) + 1

    print("\n🗂 Breakdown by source:")
    for source, count in counts_by_source.items():
        print(f"  - {source}: {count}")

    # Show sample docs per type or source
    print(f"\n🔎 Sample documents by type/source (limit={limit} each):\n")
    for dtype in counts_by_type:
        print(f"--- Type: {dtype} ---")
        type_docs = [d for d in all_docs if d.get("metadata", {}).get("artifact_type") == dtype]
        for doc in type_docs[:limit]:
            meta = doc.get("metadata", {})
            print(f"  ID={doc.get('id')} | source={meta.get('source')} | title={meta.get('title', meta.get('flow_name', ''))}")
        print()

    for source in counts_by_source:
        print(f"--- Source: {source} ---")
        src_docs = [d for d in all_docs if d.get("metadata", {}).get("source") == source]
        for doc in src_docs[:limit]:
            meta = doc.get("metadata", {})
            print(f"  ID={doc.get('id')} | type={meta.get('artifact_type')} | title={meta.get('title', meta.get('flow_name', ''))}")
        print()


if __name__ == "__main__":
    check_vector_db_by_source_or_type(limit=5)
