#app/utils.py
def clean_metadata(metadata: dict) -> dict:
    """
    Clean metadata dictionary to remove None values or unsupported types
    before ingestion to Vector DB.
    """
    cleaned = {}
    for k, v in metadata.items():
        if v is None:
            continue
        # Convert bools, ints, floats, and strings properly
        if isinstance(v, (bool, int, float, str)):
            cleaned[k] = v
        else:
            # Fallback: convert other types to string
            cleaned[k] = str(v)
    return cleaned
