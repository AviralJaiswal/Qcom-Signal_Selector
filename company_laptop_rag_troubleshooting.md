# Corporate Laptop RAG & LLM Diagnostic Guide

## 🔍 Root Cause Analysis: Why it works locally vs. fails on the Company Laptop

| Checkpoint | Personal PC (Working) | Company Laptop (Failing / Hardcoded Loop) |
| :--- | :--- | :--- |
| **API Key (`.env`)** | `GEMINI_API_KEY` is loaded and valid. | `GEMINI_API_KEY` is missing, empty, or has extra quotes/spaces in `.env`. |
| **Corporate SSL Proxy** | Direct connection to `generativeai.googleapis.com`. | Zscaler / Netskope proxy intercepts SSL, causing `SSLCertVerificationError` that silently triggers the backend fallback. |
| **Model Name** | `LLM_MODEL=gemini-3.6-flash` | `.env` has old `LLM_MODEL=gemini-2.5-flash` (which returns 404 Not Found from Google). |
| **Git / Server State** | Latest `main` commit with SSL bypass and persistent session ID. | Old backend code running in an un-restarted `uvicorn` process or un-pulled git branch. |

---

## 🛠️ Step-by-step Solution for the Company Laptop

### Step 1: Verify `.env` File Content on Company Laptop
Open `qcom/.env` on the company laptop and ensure it matches this exact format (no quotes around keys):

```ini
GEMINI_API_KEY=AIzaSy...your_active_key_here...
LLM_MODEL=gemini-3.6-flash
DATABASE_URL=sqlite:///./signal_selector.db
PORT=8000
```

> [!IMPORTANT]
> Make sure `LLM_MODEL` is set to **`gemini-3.6-flash`** (not `gemini-2.5-flash` or `gemini-1.5-flash`, which return API 404 errors).

---

### Step 2: Run the Diagnostic Test Script on Company Laptop
Copy and run this 1-line command in PowerShell / Terminal inside `Signal Selector\qcom`:

```powershell
python -c "import os, ssl, urllib3; urllib3.disable_warnings(); ssl._create_default_https_context = ssl._create_unverified_context; import google.generativeai as genai; from app.config import get_settings; s = get_settings(); print('1. API KEY PRESENT:', bool(s.gemini_api_key)); print('2. MODEL:', s.llm_model); genai.configure(api_key=s.gemini_api_key, transport='rest'); m = genai.GenerativeModel(s.llm_model); res = m.generate_content('Say HELLO'); print('3. GEMINI RESPONSE:', res.text.strip())"
```

#### What the output means:
- ✅ If it prints `3. GEMINI RESPONSE: HELLO`, the Gemini API connection is **100% working**.
- ❌ If it prints `SSLCertVerificationError` or `ProxyError`: Your corporate Zscaler proxy is blocking Google API calls.
- ❌ If it prints `404 Not Found`: Update `LLM_MODEL=gemini-3.6-flash` in `.env`.
- ❌ If it prints `API KEY PRESENT: False`: Your `.env` file is missing or `GEMINI_API_KEY` is empty.

---

### Step 3: Hard Restart Backend & Frontend on Company Laptop

1. Stop all running servers in terminal:
   ```powershell
   # Kill any frozen python/uvicorn processes
   Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
   ```

2. Pull latest fixes from GitHub:
   ```powershell
   git pull origin main
   ```

3. Start backend:
   ```powershell
   uvicorn app.main:app --reload
   ```

4. Hard-refresh browser tab:
   Press **`Ctrl + Shift + R`** (or `Ctrl + F5`) to clear browser cache.

---

## 💬 Diagnostic Prompt to Share with IT / AI Assistant on Company Laptop

If you need to prompt an AI assistant or IT engineer directly on the company laptop, copy and paste this exact prompt:

```text
PROMPT FOR COMPANY LAPTOP ENVIRONMENT:

"I am running a FastAPI + LangGraph RAG telecom assistant application locally on this corporate laptop. 
The application works perfectly on personal non-corporate machines, but on this company laptop, submitting a valid pincode (e.g. 201012) or asking plan questions keeps returning a static fallback message: 
'I am Signal Selector's AI Broadband Assistant. I only assist with telecom...' instead of invoking the Gemini LLM + RAG engine.

Please check and fix the following 3 corporate environment issues:

1. Corporate Proxy SSL Interception: Ensure urllib3/requests SSL verification bypass (PYTHONHTTPSVERIFY=0 and unverified SSL context) is active and transport='rest' is explicitly set in google.generativeai.configure() so Zscaler/Netskope corporate proxy firewalls do not drop LLM requests.
2. .env Configuration: Verify that GEMINI_API_KEY is populated and LLM_MODEL is set to 'gemini-3.6-flash' (avoiding deprecated gemini-2.5-flash which yields HTTP 404).
3. Session State & Routing: Ensure build_graph(db).invoke(state) completes without unhandled network exceptions so app/api/rag.py does not catch exceptions and fall back to _deterministic_answer().

Run a test script using `python -c` to verify that GenerativeModel('gemini-3.6-flash').generate_content() returns a live response via REST transport behind the corporate proxy."
```
