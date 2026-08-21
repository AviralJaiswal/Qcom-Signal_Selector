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


NON_TELECOM_KEYWORDS = {
    "furniture", "table", "chair", "sofa", "bed", "desk", "wardrobe", "dining", "decor",
    "food", "recipe", "cook", "biryani", "pizza", "burger", "restaurant",
    "gym", "fitness", "workout", "diet", "nutrition", "health",
    "car", "bike", "vehicle", "flight", "hotel", "train",
    "loan", "insurance", "credit card", "bank", "gold",
    "movie ticket", "cricket", "football", "sports", "weather",
    "clothing", "shoes", "fashion", "dress", "shopping", "house plan", "building plan"
}

PLAN_PRICING_INQUIRY_KEYWORDS = {
    "price", "pricing", "cost", "package", "packages", "rates", "tariff",
    "which plan", "recommend a plan", "show plans", "available plans", "best plan", "compare plans"
}

IDENTITY_GREETING_KEYWORDS = {
    "who are you", "who r u", "who's this", "what is your name", "what's your name",
    "what are you", "hi", "hello", "hey", "good morning", "good afternoon", "good evening", "namaste"
}


def is_identity_or_greeting_query(query: str) -> bool:
    """Detect conversational greetings or identity queries (e.g. 'who are you', 'hi')."""
    q_low = query.lower().strip()
    words = re.findall(r'\w+', q_low)
    if any(k in q_low for k in ["who are you", "who r u", "your name", "what are you", "who is this"]):
        return True
    if len(words) <= 3 and any(w in {"hi", "hello", "hey", "greetings"} for w in words):
        return True
    return False


def is_plan_pricing_inquiry(query: str) -> bool:
    """Detect if query asks for specific plan recommendations or pricing details."""
    q_low = query.lower()
    return any(k in q_low for k in PLAN_PRICING_INQUIRY_KEYWORDS)


def is_out_of_scope_query(query: str) -> bool:
    """Detect non-broadband queries."""
    q_lower = query.lower()
    for kw in NON_TELECOM_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", q_lower):
            return True
    return False


def query_faq_collection(query: str, top_k: int = 3) -> List[str]:
    """Retrieve top matching FAQ chunks from ChromaDB collection using pure LangChain vector store interface or fallback."""
    if is_identity_or_greeting_query(query) or is_out_of_scope_query(query):
        return []

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
        logger.warning("ChromaDB query failed: %s. Using keyword fallback.", exc)

    # 2. Fallback keyword ranker over markdown chunks
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
    """Pure LangChain RAG synthesis grounded on telecom knowledge base via model prompt instructions."""
    if is_identity_or_greeting_query(user_query):
        prompt = (
            f"The user asked: '{user_query}'. Introduce yourself warmly as Signal Selector's AI Broadband Assistant. "
            "Explain that you assist with broadband fiber plans, router specs, technical support, and coverage checks. "
            "Invite them to ask questions or share their 6-digit area PIN code to check local availability."
        )
        res = generate(prompt, temperature=0.8)
        return res or "⚠️ LLM API Key Required: Please provide a valid GEMINI_API_KEY (starts with AIzaSy...) or OPENROUTER_API_KEY (starts with sk-or-...) in your .env file to enable live AI responses."

    if is_plan_pricing_inquiry(user_query):
        prompt = (
            f"The user asked about pricing/plans: '{user_query}'. "
            "Explain in 1-2 friendly sentences that regional fiber plans and pricing depend on location coverage, "
            "and ask them to share their 6-digit area PIN code and street address to see active plans."
        )
        res = generate(prompt, temperature=0.7)
        return res or "⚠️ LLM API Key Required: Please provide a valid GEMINI_API_KEY (starts with AIzaSy...) or OPENROUTER_API_KEY (starts with sk-or-...) in your .env file to enable live AI responses."

    if is_out_of_scope_query(user_query) or not retrieved_chunks:
        prompt = (
            f"The user asked an out-of-scope or general query: '{user_query}'. "
            "State warmly as Signal Selector AI that you specialize in fiber broadband, technical setup, and coverage. "
            "Ask how you can help with broadband or invite them to share their 6-digit PIN code."
        )
        res = generate(prompt, temperature=0.7)
        return res or "⚠️ LLM API Key Required: Please provide a valid GEMINI_API_KEY (starts with AIzaSy...) or OPENROUTER_API_KEY (starts with sk-or-...) in your .env file to enable live AI responses."

    context = "\n---\n".join(retrieved_chunks)

    prompt = f"""You are Signal Selector's AI Telecom Specialist answering general telecom FAQs.
Your answers must come STRICTLY from the provided knowledge base context below.

CRITICAL SCOPE RESTRICTION:
- Do NOT discuss, compare, or recommend specific regional pricing plans or dollar/rupee packages.
- If asked about specific regional plans or package prices, direct the user to provide their street address and 6-digit PIN code.

Knowledge Base Context:
{context}

User Question: {user_query}

Provide a clear, grounded answer in 2 concise bullet points followed by a line asking if they would like to share their PIN code and address to check local fiber availability."""

    answer_text = None
    try:
        answer_text = generate(prompt, temperature=0.3, timeout=6)
    except Exception as exc:
        logger.warning("Grounded RAG synthesis warning: %s", exc)

    if not answer_text:
        return "⚠️ LLM API Key Required: Please provide a valid GEMINI_API_KEY (starts with AIzaSy...) or OPENROUTER_API_KEY (starts with sk-or-...) in your .env file to enable live AI responses."

    return answer_text.strip()








