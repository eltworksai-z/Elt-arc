import numpy as np


def to_blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes | None) -> np.ndarray | None:
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float32)


def cosine_scores(query: list[float], matrix: list[np.ndarray]) -> np.ndarray:
    if not matrix:
        return np.zeros(0)
    stacked = np.vstack(matrix)
    q = np.asarray(query, dtype=np.float32)
    denom = np.linalg.norm(stacked, axis=1) * (np.linalg.norm(q) or 1.0)
    return (stacked @ q) / np.where(denom == 0, 1.0, denom)
