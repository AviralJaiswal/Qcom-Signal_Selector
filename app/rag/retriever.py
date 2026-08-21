import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def retrieve_plans(query: str, plans: list[Any], limit: int = 5) -> list[Any]:
    """Use Chroma when available; fall back to a rank-matching algorithm over plan catalogs and activity logs."""
    try:
        from app.config import get_settings
        if not get_settings().chroma_enabled:
            raise RuntimeError("Chroma retrieval disabled for local demo")
        import chromadb
        client = chromadb.PersistentClient(path=get_settings().chroma_path)
        collection = client.get_or_create_collection("plans")
        if plans:
            collection.upsert(
                ids=[getattr(p, "plan_id", f"P-{idx}") for idx, p in enumerate(plans)],
                documents=[f"{getattr(p, 'name', '')} {getattr(p, 'type', '')} {getattr(p, 'speed_mbps', '')} Mbps" for p in plans]
            )
        result = collection.query(query_texts=[query], n_results=min(limit, len(plans)))
        ids = (result.get("ids") or [[]])[0]
        by_id = {getattr(p, "plan_id", ""): p for p in plans}
        ranked = [by_id[i] for i in ids if i in by_id]
        return ranked or plans[:limit]
    except Exception:
        words = set(query.lower().split())
        return sorted(
            plans,
            key=lambda p: (
                getattr(p, "type", "fiber").lower() in words or any(w in getattr(p, "name", "").lower() for w in words),
                getattr(p, "speed_mbps", 0)
            ),
            reverse=True
        )[:limit]


def search_knowledge_base(query: str, limit: int = 5) -> list[dict]:
    """Semantic search over faq_knowledge_base.md, plans_catalog.json, and activity.jsonl."""
    results = []
    q = query.lower()
    
    # 0. Search faq_knowledge_base.md
    faq_path = DATA_DIR / "faq_knowledge_base.md"
    if faq_path.exists():
        try:
            content = faq_path.read_text(encoding="utf-8")
            lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]
            for line in lines:
                l_lower = line.lower()
                matched = [w for w in q.split() if len(w) > 2 and w in l_lower]
                if matched or any(k in l_lower for k in ("work from home", "wfh", "video call", "gaming", "installation", "router", "charge", "deposit", "policy")):
                    results.append({
                        "source": "faq_knowledge_base.md",
                        "document": "faq_knowledge_base.md",
                        "content": line.lstrip("- *").strip(),
                        "score": len(matched) + (5 if "work from home" in l_lower and "work from home" in q else 0)
                    })
            results.sort(key=lambda x: x.get("score", 0), reverse=True)
        except Exception as exc:
            logger.warning("Failed to load faq_knowledge_base.md for RAG: %s", exc)

    # 1. Search plans_catalog.json
    catalog_path = DATA_DIR / "plans_catalog.json"
    if catalog_path.exists():
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            for p in catalog.get("plans", []):
                score = 0
                text = f"{p.get('name', '')} {p.get('description', '')} {' '.join(p.get('ott_bundle', []))}".lower()
                for word in q.split():
                    if word in text:
                        score += 1
                if score > 0 or any(k in q for k in ["plan", "fiber", "speed", "ott", "netflix", "prime", "price"]):
                    results.append({
                        "source": "plans_catalog.json",
                        "plan_id": p.get("plan_id"),
                        "name": p.get("name"),
                        "speed_mbps": p.get("speed_mbps"),
                        "price_inr": p.get("price_inr"),
                        "ott_bundle": p.get("ott_bundle", []),
                        "description": p.get("description", "")
                    })
        except Exception as exc:
            logger.warning("Failed to load plans_catalog.json for RAG: %s", exc)

    # 2. Search activity.jsonl
    activity_path = DATA_DIR / "activity.jsonl"
    if activity_path.exists():
        try:
            lines = activity_path.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(lines[-50:]):
                if not line.strip():
                    continue
                evt = json.loads(line)
                evt_str = json.dumps(evt).lower()
                if any(w in evt_str for w in q.split() if len(w) > 3):
                    results.append({
                        "source": "activity.jsonl",
                        "event_type": evt.get("event_type"),
                        "timestamp": evt.get("timestamp"),
                        "details": evt
                    })
        except Exception as exc:
            logger.warning("Failed to search activity.jsonl for RAG: %s", exc)

    return results[:limit]
