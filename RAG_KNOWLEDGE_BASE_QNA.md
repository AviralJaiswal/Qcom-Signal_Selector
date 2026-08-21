# Signal Selector - RAG Knowledge Base & Short Q&A Catalog

This document defines the complete RAG Knowledge Base dataset, query domain boundaries, and concise Q&A mappings for the **Signal Selector AI Telecom Platform**.

---

## 1. System Domain Boundaries (RAG vs. Transactional API)

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           SYSTEM ARCHITECTURE BOUNDARIES                         │
├───────────────────────────────────────────────────┬───────────────────────────────┤
│           INFORMATIONAL RAG FLOW                  │     TRANSACTIONAL API FLOW    │
│            (ChromaDB + Gemini)                    │    (FastAPI + DB + OLA Maps)  │
├───────────────────────────────────────────────────┼───────────────────────────────┤
│ • General FAQs (timelines, deposits, billing)    │ • Pincode Coverage Check      │
│ • Product & Hardware Specs (Wi-Fi 6, Mesh, Ports) │ • Address Reverse Geocoding   │
│ • Installation Process & On-site e-KYC            │ • Dynamic Live Plan Catalog   │
│ • Company Policies (14-day refund, SLA, terms)    │ • Slot Reservation Calendar   │
│ • Technical Troubleshooting (Red light, Ping)     │ • Payment Processing Endpoint │
│ • General Plan Guidance & Comparisons             │ • Order Creation & Receipts   │
└───────────────────────────────────────────────────┴───────────────────────────────┘
```

---

## 2. Concise Q&A Knowledge Catalog

All answers in the RAG flow are engineered to be **short, crisp, to the point (2-3 lines max)** with a clean call-to-action to provide a 6-digit PIN code to check local coverage or start an order.

---

### Category 1: General FAQs

#### Q1: How long does broadband installation take?
* **Short Answer:** Standard installation is completed within **24 to 48 hours** after order placement. Express same-day installation within **6 hours** is available in major metro circles for orders placed before 12:00 PM.
* **Transition:** *To check express availability in your area, share your 6-digit area PIN code!*

#### Q2: Is there an installation fee or security deposit?
* **Short Answer:** Installation is **100% free** on 6-month or 12-month advance plans. For monthly plans, a standard ₹500 setup fee applies. **Zero refundable security deposit** is required for the Wi-Fi 6 router.
* **Transition:** *Share your 6-digit area PIN code to view zero-installation fee options!*

#### Q3: What billing cycles are available?
* **Short Answer:** We offer Monthly, 6-Month, and 12-Month subscription plans. Advance plans (6 & 12 months) include free installation and complimentary premium OTT bundles (Netflix, Prime Video, Hotstar).
* **Transition:** *Want to compare billing plans? Share your 6-digit PIN code to view regional rates!*

---

### Category 2: Product & Hardware Specifications

#### Q4: What router hardware is provided with the connection?
* **Short Answer:** All plans include a high-performance **Dual-Band Wi-Fi 6 (802.11ax) Gigabit ONT Router** featuring 4 high-gain antennas, 4 Gigabit Ethernet LAN ports, WPA3 encryption, and MU-MIMO support.
* **Transition:** *Ready to power your home with Wi-Fi 6? Share your 6-digit PIN code to check coverage!*

#### Q5: What is the difference between 2.4 GHz and 5 GHz Wi-Fi frequencies?
* **Short Answer:** **5 GHz** provides ultra-fast speeds (up to 2402 Mbps) and low ping for gaming and 4K streaming near the router. **2.4 GHz** offers longer range through thick walls at lower speeds (up to 574 Mbps).
* **Transition:** *Share your 6-digit area PIN code to check regional fiber speeds for your home!*

#### Q6: How do Mesh Wi-Fi extenders work?
* **Short Answer:** Wi-Fi 6 Mesh Extenders (available for ₹199/month) pair with your main router to eliminate Wi-Fi dead zones in large or multi-story homes under a single network name (SSID).
* **Transition:** *To add Mesh coverage to a new fiber line, share your 6-digit PIN code!*

---

### Category 3: Installation & Verification

#### Q7: What is the physical installation process?
* **Short Answer:** A certified technician runs an optical fiber drop cable from the nearest street Fiber Distribution Hub (FDH) box into your home, sets up the Wi-Fi 6 ONT router, and conducts live on-site speed verification.
* **Transition:** *To schedule a technician visit, share your 6-digit area PIN code!*

#### Q8: What documents are required for KYC verification?
* **Short Answer:** Any ONE valid government identity/address proof: **Aadhaar Card, Passport, Voter ID, or Driving License**. Digital e-KYC is completed on-site by the technician in 2 minutes.
* **Transition:** *Ready to set up your account? Share your 6-digit PIN code to check serviceability!*

---

### Category 4: Company Policies & SLA

#### Q9: What is the refund policy if I am unsatisfied?
* **Short Answer:** We offer a **14-Day 100% Money-Back Guarantee**. If service quality or speed does not meet SLA standards in the first 14 days, you receive a full refund upon equipment return.
* **Transition:** *To get started risk-free, share your 6-digit PIN code!*

#### Q10: What is the network Uptime SLA?
* **Short Answer:** We guarantee **99.9% network availability** supported by redundant optical fiber ring architecture and 24/7 automated network monitoring.
* **Transition:** *Share your 6-digit PIN code to check high-availability fiber coverage in your sector!*

---

### Category 5: Troubleshooting & Support

#### Q11: What should I do if the LOS indicator light is blinking red on my router?
* **Short Answer:** A blinking red **LOS light** indicates physical fiber signal loss. Verify that the thin yellow optical patch cord is tightly connected to the router. If it remains red, perform a 30-second power restart or request a technician dispatch.
* **Transition:** *Need a technician visit or a new connection? Share your 6-digit PIN code!*

#### Q12: How can I fix slow speeds or high ping in online gaming?
* **Short Answer:** 
  1. Connect your PC/Console via Cat6 Ethernet cable directly to the router's Gigabit LAN port.
  2. If using Wi-Fi, connect to the 5GHz SSID (`SignalSelector_5G`).
  3. Perform a 30-second power cycle restart.
* **Transition:** *Ready for dedicated high-speed gaming fiber? Share your 6-digit PIN code!*

---

### Category 6: General Plan Guidance & Explanations

#### Q13: Which plan should I choose for work-from-home and video calls?
* **Short Answer:** Our **200 Mbps Plan** is ideal for 3-4 users holding simultaneous HD Zoom/Teams calls, VPN access, and heavy cloud uploads with zero buffering.
* **Transition:** *Share your 6-digit area PIN code to view 200 Mbps plan pricing for your location!*

#### Q14: Which plan is best for 4K streaming and heavy gaming?
* **Short Answer:** Our **300 Mbps or 1 Gbps Plans** provide low ping (<5ms), symmetrical speeds, and bundled premium OTT apps (Netflix, Amazon Prime, Hotstar).
* **Transition:** *Share your 6-digit area PIN code to check 300 Mbps & 1 Gbps plan offers!*

---

## 3. Seamless Order Flow Transition Rule

Whenever a user in the **RAG Flow** expresses intent to book a connection, upgrade, or check regional feasibility (e.g., *"I want to book this"*, *"Is this available in my area?"*, or provides a 6-digit PIN code like `500081`), the **Supervisor Router** immediately transitions the user into the **Transactional Order Flow**:

1. **Pincode Qualified:** Feasibility & circle verified via Database.
2. **Address Qualified:** Exact address qualified via OLA Maps Geocoding API.
3. **Plan Selected & Booked:** Interactive plan card selection, technician calendar slot reserved, payment processed.
