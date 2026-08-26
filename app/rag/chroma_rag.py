import logging
import re
from pathlib import Path
from typing import List, Dict, Any

from app.config import get_settings
from app.assistant.llm import generate

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FAQ_FILE = DATA_DIR / "faq_knowledge_base.md"

COLLECTION_NAME = "faq_collection"


def load_and_chunk_faq_md() -> List[Dict[str, Any]]:
    """Parse data/faq_knowledge_base.md into semantic chunks based on headers."""
    if not FAQ_FILE.exists():
        logger.warning("faq_knowledge_base.md not found at %s", FAQ_FILE)
        return []

    content = FAQ_FILE.read_text(encoding="utf-8")
    sections = re.split(r'\n(?=##\s+)', content)
    chunks = []

    for idx, section in enumerate(sections):
        section_str = section.strip()
        if not section_str:
            continue
        lines = section_str.splitlines()
        header = lines[0].replace("#", "").strip() if lines else f"Section {idx+1}"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else section_str
        chunks.append({
            "id": f"faq_chunk_{idx+1}",
            "header": header,
            "text": f"{header}\n{body}",
            "metadata": {"header": header, "chunk_index": idx+1}
        })
    return chunks


class FastTextEmbeddingFunction:
    """Fast, self-contained vector embedding function for ChromaDB without external network downloads."""
    def name(self) -> str:
        return "fast_text_embedding"

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self(input)

    def embed_query(self, input: list[str] | str) -> list[list[float]]:
        if isinstance(input, str):
            input = [input]
        return self(input)

    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings = []
        for doc in input:
            vec = [0.0] * 128
            for word in re.findall(r'\w+', doc.lower()):
                idx = abs(hash(word)) % 128
                vec[idx] += 1.0
            norm = (sum(x * x for x in vec) ** 0.5) or 1.0
            embeddings.append([x / norm for x in vec])
        return embeddings


def _get_collection(client, embed_fn):
    try:
        return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)
    except ValueError:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)


def init_faq_chroma() -> bool:
    """Initialize ChromaDB and load/chunk faq_knowledge_base.md into 'faq_collection'."""
    settings = get_settings()
    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_path)
        embed_fn = FastTextEmbeddingFunction()
        collection = _get_collection(client, embed_fn)

        chunks = load_and_chunk_faq_md()
        if chunks:
            ids = [c["id"] for c in chunks]
            documents = [c["text"] for c in chunks]
            metadatas = [c["metadata"] for c in chunks]
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info("Successfully loaded %d chunks into ChromaDB collection '%s'", len(chunks), COLLECTION_NAME)
            return True
    except Exception as exc:
        logger.exception("Failed to initialize ChromaDB collection '%s': %s", COLLECTION_NAME, exc)
    return False


def query_faq_collection(query: str, top_k: int = 3) -> List[str]:
    """Retrieve top matching FAQ chunks from ChromaDB vector collection."""
    settings = get_settings()

    # 1. Try ChromaDB retrieval
    try:
        import chromadb
        client = chromadb.PersistentClient(path=settings.chroma_path)
        embed_fn = FastTextEmbeddingFunction()
        collection = _get_collection(client, embed_fn)

        if collection.count() == 0:
            init_faq_chroma()
            collection = _get_collection(client, embed_fn)

        res = collection.query(query_texts=[query], n_results=min(top_k, max(1, collection.count())))
        docs = (res.get("documents") or [[]])[0]
        if docs:
            return docs
    except Exception as exc:
        logger.warning("ChromaDB query failed: %s. Using markdown chunk fallback.", exc)

    # 2. Fallback ranker over markdown chunks
    all_chunks = load_and_chunk_faq_md()
    q_words = set(re.findall(r'\w+', query.lower()))
    scored = []
    for c in all_chunks:
        text_lower = c["text"].lower()
        score = sum(1 for w in q_words if w in text_lower and len(w) > 2)
        scored.append((score, c["text"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [text for score, text in scored[:top_k] if score > 0]


def generate_grounded_faq_answer(user_query: str, retrieved_chunks: List[str]) -> str:
    """Dynamic RAG synthesis grounded on telecom knowledge base via model prompt instructions."""
    if not retrieved_chunks:
        prompt = f"""You are Signal Selector's AI Broadband Specialist. Keep answers clear, conversational, and under 50 words.
- Greetings/identity: Introduce yourself briefly and offer help with broadband plans, pricing, speeds, or coverage.
- Plan/pricing questions: Provide details on our standard India-wide plans (Basic 40M @ ₹499/mo, Standard 100M @ ₹799/mo, Entertainment 200M @ ₹999/mo, Professional 300M @ ₹1,499/mo, Infinity 1G @ ₹3,999/mo). Do NOT ask for address or location unless explicitly requested.
- Support/Issues: Direct them to customer.support@qcom.com.
- If the customer explicitly asks to check coverage, switch plans, or buy a new connection, ask for their complete street address (including house/flat number, building name, street, area, and pincode). Do NOT ask for just a 6-digit PIN code alone.

User: {user_query}"""
    else:
        context = "\n---\n".join(retrieved_chunks)
        prompt = f"""You are Signal Selector's AI Broadband Specialist. Answer directly from the context below. Keep it concise, friendly, and helpful.
Guidelines:
- Answer questions about plans, pricing, speeds, routers, installation, OTT bundles, and recommendations directly from the context without asking for an address or location.
- If the customer explicitly asks to check coverage, switch plans, or buy/get a new connection, ask for their complete street address (including house/flat number, building name, street, area, and pincode). Do NOT ask for just a 6-digit PIN code alone.
- If asked about support or technical issues, provide customer.support@qcom.com.

Context:
{context}

User: {user_query}"""

    answer_text = None
    try:
        answer_text = generate(prompt, temperature=0.5, timeout=6, max_tokens=150)
    except Exception as exc:
        logger.warning("Grounded RAG synthesis warning: %s", exc)

    if not answer_text:
        return "⚠️ LLM API Key Required: Please provide a valid GEMINI_API_KEY (starts with AIzaSy...) or OPENROUTER_API_KEY (starts with sk-or-...) in your .env file to enable live AI responses."

    return answer_text.strip()








