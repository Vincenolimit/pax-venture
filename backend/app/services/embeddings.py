import numpy as np
from sqlalchemy import select

from app.models import Decision, DecisionEmbedding


async def embed(_session, text: str) -> bytes:
    rng = np.random.default_rng(abs(hash(text)) % (2**32))
    vec = rng.random(512, dtype=np.float32)
    return vec.astype("<f4").tobytes()


async def retrieve(session, player_id: str, query_text: str, k: int = 3, min_importance: float = 0.4):
    query = np.frombuffer(await embed(session, query_text), dtype="<f4")
    rows = (await session.execute(select(DecisionEmbedding, Decision).join(Decision, Decision.id == DecisionEmbedding.decision_id).where(DecisionEmbedding.player_id == player_id, Decision.importance >= min_importance))).all()
    if len(rows) < 3:
        return []
    scored = []
    for emb, dec in rows:
        v = np.frombuffer(emb.vector, dtype="<f4")
        sim = float(np.dot(query, v) / (np.linalg.norm(query) * np.linalg.norm(v)))
        scored.append((sim, dec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"decision_id": d.id, "similarity": s, "decision_text": d.decision_text, "narrative": d.narrative} for s, d in scored[:k]]
