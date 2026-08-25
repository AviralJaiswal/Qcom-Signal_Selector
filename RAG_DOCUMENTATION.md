# Signal Selector - RAG Architecture & Dual-Flow Implementation Guide

This document defines the complete system architecture, intent classification matrix, vector database layout, and execution flows for the **Signal Selector AI Telecom Platform**.

---

## 1. System Architecture Overview

The system uses a **Supervisor Intent Routing Engine** to classify user inputs into two distinct operational flows: **Informational (RAG Flow)** and **Transactional (Order Flow)**.

```
===================================================================================
                       SIGNAL SELECTOR SYSTEM ARCHITECTURE
===================================================================================

                               [ USER CLIENT ]
                        (React 19 / Vite UI Layer)
                                     │
                                     │ POST /api/v1/chat/message
                                     ▼
                     ┌───────────────────────────────┐
                     │    LangGraph Supervisor Node  │
                     │  (Gemini Intent Classifier)   │
                     └───────────────┬───────────────┘
                                     │
              ┌──────────────────────┴──────────────────────┐
              │                                             │
   [ Informational Intent ]                        [ Transactional Intent ]
              │                                             │
              ▼                                             ▼
┌───────────────────────────────┐             ┌───────────────────────────────┐
│       RAG KNOWLEDGE NODE      │             │    TRANSACTIONAL API NODE     │
│   (ChromaDB + Gemini Flash)   │             │  (FastAPI Deterministic APIs) │
├───────────────────────────────┤             ├───────────────────────────────┤
│ • General FAQs                │             │ • Pincode Serviceability API  │
│ • Product & Hardware Specs    │             │ • Address Reverse Geocoding   │
│ • Installation Information    │             │ • Real-time Plan Catalog DB   │
│ • Company Policies (KYC, etc.)│             │ • Installation Slot Booking   │
│ • Technical Troubleshooting   │             │ • Payment Gateway Endpoint    │
│ • Conceptual Plan Guidance    │             │ • Orders & Account DB Records │
│ • Plan Recommendations/Compare│             │ • New Connection Booking      │
└──────────────┬────────────────┘             └──────────────┬────────────────┘
              │                                             │
              └──────────────────────┬──────────────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │   Unified Response Formatter  │
                     │  (Structured Payload & Text)  │
                     └───────────────┬───────────────┘
                                     │
                                     ▼
                              [ Client Stream ]
```

---

## 2. Intent Routing & Responsibility Matrix

| Feature / Query Category | Target Flow | System Layer | Execution Engine |
| :--- | :--- | :--- | :--- |
| **New Connection Requests** | `ORDER_FLOW` | Transactional API Node | Pincode / Address qualification |
| **Area Pincode Feasibility Check** | `ORDER_FLOW` | Transactional API Node | Database / OLA Maps Geocoding |
| **Full Street Address Verification** | `ORDER_FLOW` | Transactional API Node | OLA Maps / Nominatim API |
| **Broadband Plan Booking / Selection** | `ORDER_FLOW` | Transactional API Node | SQLAlchemy DB + State Store |
| **Installation Slot Booking** | `ORDER_FLOW` | Transactional API Node | Appointment Service API |
| **Payment Gateway & Order Confirmation**| `ORDER_FLOW` | Transactional API Node | Payment Service API |
| **Plan Recommendations & Suggestions** | `FAQ_FLOW` | RAG Knowledge Node | ChromaDB + Grounded Gemini |
| **Plan Comparisons & Explanations** | `FAQ_FLOW` | RAG Knowledge Node | ChromaDB + Grounded Gemini |
| **Router Specs & Hardware Features** | `FAQ_FLOW` | RAG Knowledge Node | ChromaDB (`faq_collection`) |
| **Installation Timelines & Charges** | `FAQ_FLOW` | RAG Knowledge Node | ChromaDB (`faq_collection`) |
| **KYC Documents & Refund Policies** | `FAQ_FLOW` | RAG Knowledge Node | ChromaDB (`faq_collection`) |
| **Technical Support / Troubleshooting** | `FAQ_FLOW` | RAG Knowledge Node | ChromaDB (`faq_collection`) |

---

## 3. Flow Specifications

### 3.1 Flow 1: ORDER FLOW (Transactional / Dynamic State Engine)
When a user asks for a **new connection** or initiates an order, the request enters the **Order Pipeline**:

1. **Pincode Verification (Step 2A):** Evaluates pincode against active regional coverage databases.
2. **Reverse Geocoding (Step 2B):** Qualifies full street address using **OLA Maps API** (with Nominatim fallback).
3. **Plan Presentation (Step 3):** Fetches real-time catalog broadband plans matching the telecom circle.
4. **Customer Details (Step 4):** Captures customer name, email, and 10-digit mobile number.
5. **Slot Booking (Step 5):** Displays available installation time slots and reserves the slot.
6. **Payment & Booking (Step 6-7):** Processes payment token and generates an official Order ID in `qcom.db`.

### 3.2 Flow 2: RAG KNOWLEDGE FLOW (Informational Vector Store Engine)
When a user asks for **plan recommendations, comparisons, advice, router specs, FAQs, or troubleshooting**:

1. **Query Intent Detection:** Supervisor router classifies query into `FAQ_FLOW`.
2. **Vector Retrieval:** Queries ChromaDB vector database (`faq_collection`) using sub-millisecond fast text vector embeddings (`top_k=3` relevant chunks).
3. **Grounded Gemini Synthesis:** Passes retrieved knowledge chunks to **Gemini Flash** with a strict grounding prompt.
4. **Follow-Up Transition:** Returns formatted Markdown answer with a seamless call-to-action inviting the user to provide their 6-digit PIN code to get started.

---

## 4. Code Implementation Architecture

### 4.1 Supervisor Router (`app/chat/graph.py`)
```python
def _classify_dual_flow(state: ConversationState, text: str) -> tuple[str, str]:
    # 1. Instant 0ms Keyword Filter for FAQs & Plan Questions
    faq_keywords = ["recommendation", "recommend", "suggest", "which plan", "best plan", "compare plans", "plan difference", ...]
    if any(kw in normalized for kw in faq_keywords):
        return ("FAQ_FLOW", "faq_rag")
    
    # 2. Gemini Classifier for nuanced intents
    # ORDER_FLOW -> New connection, pincode entry, slot booking, payment
    # FAQ_FLOW   -> Plan suggestions, router specs, policies, troubleshooting
```

### 4.2 Vector Database & RAG Synthesis (`app/rag/chroma_rag.py`)
* **Vector Store:** ChromaDB persistent storage (`./chroma_data`).
* **Dataset:** `data/faq_knowledge_base.md` sectioned by semantic headers.
* **Embedding:** `FastTextEmbeddingFunction` (0ms offline vector calculation).
* **Synthesis Engine:** `generate_grounded_faq_answer()` using Gemini Flash with `transport="rest"` for sub-second responses.

---

## 5. Summary of Responsibilities

* **RAG Flow:** Static knowledge, plan conceptual guidance, recommendations, FAQs, hardware specs, policies, troubleshooting.
* **Order Flow:** Dynamic transactional data, pincode feasibility, reverse geocoding, real-time database queries, appointment booking, order generation.
