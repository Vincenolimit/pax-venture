import hashlib


def compute_seed(player_id: str, month: int, seq: int) -> int:
    """Stable 32-bit seed derived from deterministic tuple content."""
    material = f"{player_id}:{month}:{seq}".encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:4], byteorder="big", signed=False)


def derive_seed(player_id: str, month: int, seq: int) -> int:
    # Backward-compatible alias used across existing routes/services.
    return compute_seed(player_id, month, seq)
