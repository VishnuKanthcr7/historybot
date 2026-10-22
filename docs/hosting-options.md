# Hosting options for HistoryBot (updated 22 Oct 2026)

Nothing has been bought, signed up for or activated. All prices below were read on 22 Oct 2026 from provider pages or recent
price trackers (links at the end) and must be re-checked at checkout. Conversions use the RBI reference rate of 22 Oct 2026:
**US$1 = ₹94.71, €1 = ₹106.28**. Indian cards usually add a 2–3.5% foreign-currency markup, which is not included.
**GST:** foreign cloud providers normally charge 18% IGST to Indian customers; it is included in the "total" columns.

## What actually has to run (measured on the laptop, 22 Oct 2026)

| Part | Measured | Needed in production? |
|---|---|---|
| Frontend | Netlify (free) | Keep Netlify; only `VITE_API_BASE_URL` changes. |
| Node backend (:3000) | ~80 MB private memory | Yes. |
| Python RAG service (:8000, ChromaDB + ReportLab) | ~580 MB private memory | Yes. Internal only (never public). |
| Ollama + `nomic-embed-text` (274 MB model) | ~320 MB when the model is loaded | Yes, unless embeddings are changed (see below). |
| MySQL 8 | ~110–400 MB (depends on buffer settings); database dump 2.4 MB | Yes. Internal only. |
| Data on disk | `data/` (Chroma index, textbooks, images, fonts) 58 MB | Yes. |
| Answer model | OpenAI Responses API (paid per use, already in use) | Unchanged. llama3/llama3.2 are NOT needed in production. |

**Total:** about 1.3–1.6 GB RAM in steady use plus the OS. A **2 GB** server works only with swap and a small MySQL buffer;
**4 GB** is comfortable. Disk: 20 GB is plenty.

### Is Ollama needed in production?
Every question is embedded with `nomic-embed-text` to search the ChromaDB index, so *something* must produce the same
embeddings. Options, honestly:
1. **Keep Ollama with only `nomic-embed-text`** (recommended): ~320 MB RAM, no code change, no re-indexing, ₹0 per query.
2. Run the same model through a Python library (e.g. sentence-transformers/fastembed) inside the RAG process: saves the
   Ollama process but needs a code change and a check that vectors match the existing index. Not done.
3. Switch to a paid embeddings API (e.g. OpenAI): needs a full re-index, a new paid call on every question, and new
   retrieval testing. Not recommended.

## Options compared (backend + RAG + MySQL on one server; Netlify frontend stays free)

| Option | Spec | Price | Approx. ₹/month incl. 18% GST | Notes |
|---|---|---|---|---|
| **Oracle Cloud Always Free (Ampere A1)** | up to 2 OCPU / 12 GB RAM (Arm), 200 GB block storage | ₹0 | **₹0** | Limits were cut in Jul 2026 from 4 OCPU/24 GB to 2 OCPU/12 GB — still far more than needed. Needs a card for identity verification. Must be in the home region; **Mumbai/Hyderabad A1 capacity is often "out of host capacity"** and launching can take days of retries. Oracle may reclaim idle Always Free instances. No SLA. Backups must be your own (cron mysqldump to the free block/object storage). Realistic ₹0 if an instance can be created. |
| **Hetzner Cloud CX23** (Germany/Finland) | 2 vCPU / 4 GB / 40 GB NVMe / 20 TB | €5.99 incl. IPv4 (+20% for backups = €1.10) | **≈ ₹750** (≈ ₹890 with backups) | Cheapest reliable paid option found. Prices rose on 15 Jun 2026. Europe only for this plan (≈150 ms from India — fine for chat). Stock of EU CX/CAX plans was reported "not available" on 21 Oct 2026; check before planning. |
| Contabo Cloud VPS 4 (EU) | 4 vCPU / 8 GB / 100 GB SSD | €5.50/month on a 1-month term | ≈ ₹690 | Lots of RAM; 200 Mbit/s port; slower support; no Indian GST invoice. |
| Contabo Cloud VPS 4 (Navi Mumbai) | same | €5.50 + €2.40 India location fee; auto-backup €1.65 | ≈ ₹990 (≈ ₹1,200 with backups) | Lowest latency in this list. |
| DigitalOcean Basic, Bangalore 2 GB | 1 vCPU / 2 GB / 50 GB | US$12 (+20% backups) | ≈ ₹1,340 (≈ ₹1,610 with backups) | Works only with swap; tight. |
| DigitalOcean Basic, Bangalore 4 GB | 2 vCPU / 4 GB / 80 GB | US$24 (+20% backups) | ≈ ₹2,680 (≈ ₹3,220 with backups) | The option the guide quoted; comfortable but the most expensive here. |
| Railway (Hobby) | usage-based: $10 per GB RAM-month, $20 per vCPU-month, volumes $0.15/GB | $5 plan includes $5 usage | ≈ ₹1,700–2,300 | ~1.5 GB always-on RAM across backend, RAG, Ollama and MySQL ≈ $15–20/month. Free plan (0.5 GB per service, $1 credit) cannot run the stack. |

OpenAI usage is billed separately as today and is the same on every option.

## Recommendation
1. **Try Oracle Always Free first (₹0).** It is the only genuinely free option that can run the whole stack with data
   persistence. The risk is availability (capacity errors, possible reclaim), not features.
2. **If Oracle cannot create an instance within a few days, use Hetzner CX23 (≈ ₹750–890/month)**, or Contabo Mumbai
   (≈ ₹990–1,200) if lower latency in India matters more.
3. Keep the Netlify site; point `VITE_API_BASE_URL` at the new `https://api.<domain>` (or a stable Cloudflare named tunnel,
   which is free) and redeploy only after the new backend is verified.

## Security and migration plan (nothing done yet; needs your approval)
- Firewall: allow only 22 (SSH, key-only, no password login) and 443. MySQL (3306), RAG (8000) and Ollama (11434) bind to
  127.0.0.1 only. Never exposed.
- HTTPS via Caddy/nginx with Let's Encrypt, or a Cloudflare named tunnel (free, no open ports).
- CORS: `FRONTEND_ORIGIN=https://historybot-vsku.netlify.app` only. Rate limits already in the backend.
- Secrets: a `.env` created on the server by hand (never committed, never pasted in chat).
- Data: `mysqldump` on the laptop → copy over SSH → restore → compare row counts per table → run tests on the server copy
  → switch the frontend → keep the laptop backend running until the server is verified. Daily `mysqldump` cron with
  14-day retention, plus a weekly copy off the server.
- Apply migration 007 (roll numbers) on the production database only with approval, after a backup.

## Sources (checked 22 Oct 2026)
- Hetzner price adjustment, 15 Jun 2026: https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
- Oracle Always Free resources: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Oracle A1 allocation change (Jul 2026): https://community.oracle.com/customerconnect/discussion/970310/oci-always-free-updated-ampere-a1-compute-allocation
- DigitalOcean Droplet pricing: https://www.digitalocean.com/pricing/droplets
- Railway pricing: https://railway.com/pricing and https://docs.railway.com/pricing
- Contabo prices and India location fee (third-party reviews of the configurator, Oct 2026): https://technicaladda.in/contabo-vps-review/ , https://comparehost.in/best-cheap-vps-under-1000-india-2026/
- RBI reference rates: https://www.msei.in/markets/currency/historical-data/rbireferenceratearchives

---

*The 15 Oct 2026 assessment below is kept for reference; where it differs, the update above is current.*

# Hosting options for the HistoryBot backend (assessment only, 15 Oct 2026)

Nothing has been bought or signed up for. Prices are monthly, in USD, before tax (GST may be added for Indian billing).
- **"verified":** read from the provider's pricing page on 15 Oct 2026.
- **"unverified":** the pricing page did not render its prices or was not checked; confirm before buying.

## What has to be hosted

| Part | Today (laptop) | Notes |
|---|---|---|
| Frontend (React/Vite) | Netlify site historybot-vsku | Already hosted; only `VITE_API_BASE_URL` changes. |
| Backend (Express, Node 22) | `node backend/src/server.js` on :3000 behind a Cloudflare *quick* tunnel | The quick-tunnel URL changes when it restarts, and the site is down whenever the laptop is off. |
| RAG service (Python, ChromaDB, ReportLab PDFs) | :8000, internal only | ChromaDB is about 9 MB on disk. PDFs need the bundled fonts in the image or VM. |
| Embeddings | Ollama `nomic-embed-text` (local) | Every query is embedded, so this must be available in production (see below). |
| Answer model | OpenAI (paid, via `LLM_PROVIDER`) or local llama3 via Ollama | llama3 (8B) needs about 6 GB RAM and is slow on CPU. Not realistic on a small VPS. |
| MySQL 8 | Local MySQL; the dump is about 2 MB | Holds student accounts, chats, quiz attempts and research data, which is personal data of minors. |

**Measured on the laptop (idle):**
- Node backend: about 65 MB working set.
- MySQL: about 90 MB.

**Not measured:** the RAG process under load. Estimate 300–600 MB with ChromaDB and the PDF renderer loaded.

## RAM needed

| Setup | RAM |
|---|---|
| Backend + RAG + MySQL + Ollama embeddings only (nomic-embed-text, about 0.3 GB loaded), answers from the OpenAI API | 2 GB is tight, **4 GB comfortable** |
| Same plus local llama3 answers | 8–16 GB and still slow without a GPU. Not recommended. |

## Embedding provider

Keep `nomic-embed-text` but run it with Ollama on the same server (CPU is fine for short queries). This needs no re-indexing, because the existing Chroma vectors were made with that model.

Switching to a hosted embedding API (e.g. OpenAI) would mean:
- re-embedding the whole corpus;
- a new Chroma collection;
- re-running the retrieval regressions;
- a new per-query cost.

**Recommendation:** keep Ollama embeddings on the server.

## Options

| Option | What you get | Approx. cost | Status |
|---|---|---|---|
| **DigitalOcean Droplet, Bangalore (BLR1)** | Basic 4 GiB / 2 vCPU / 80 GiB SSD / 4 TB transfer. One VM runs Node + RAG + Ollama embeddings + MySQL. | **$24/mo**, plus weekly backups at 20% (about $4.80) or daily backups at 30% (about $7.20) | Prices verified. The Bangalore region is confirmed on the same page. |
| DigitalOcean Droplet 2 GiB | 2 GiB / 1 vCPU | $12/mo | Verified, but tight for RAG + MySQL + embeddings. |
| **AWS Lightsail, Mumbai (ap-south-1)** | 4 GB / 2 vCPU / 80 GB SSD | **$24/mo**. Mumbai plans get half the listed transfer allowance (2 TB). Snapshots $0.05/GB-month. | Verified. |
| Lightsail managed MySQL (optional, instead of MySQL on the VM) | 1 GB standard plan (no encryption at rest) / 2 GB standard plan (encrypted) | $15 / $30 per month | Verified. Prefer the encrypted $30 plan if you use managed MySQL. |
| Hetzner Cloud (Germany/Finland/USA/Singapore; no India region) | Shared vCPU VMs, e.g. 4–8 GB | Typically €4–10/mo | **Unverified:** the pricing page did not render prices. Data would sit outside India (Singapore is the nearest). |
| Render (web service + private service) | 2 GB "1 CPU" instance at $25 each for the backend and RAG, plus a disk at $0.25/GB. **No managed MySQL**, so an external MySQL is needed. | About $50+/mo before the database | Verified. More expensive and needs an external DB and more moving parts. |
| Railway | Usage-based containers + MySQL template | Unverified | Not checked. |
| Oracle Cloud Always Free (Ampere A1, up to 24 GB ARM; Mumbai/Hyderabad regions) | Free VM | $0 | **Unverified.** Free-tier capacity is often unavailable, and idle instances can be reclaimed. Not reliable for a school service. |
| Indian providers (e.g. E2E Networks, a local VPS) | India-resident VMs | Not checked | Unverified. |

## Security checklist (any option)

- **TLS:**
  - Use a fixed domain (e.g. api.example.org).
  - Caddy or nginx + Let's Encrypt, or a *named* Cloudflare Tunnel (stable URL, no open inbound ports).
  - Drop the quick tunnel.
- **Firewall:**
  - Allow only 443 (and 22 restricted to your IP or key-only SSH).
  - Keep MySQL (3306), RAG (8000) and Ollama (11434) bound to 127.0.0.1 and never publicly reachable.
- **Secrets:**
  - Store `.env` on the server only (chmod 600), or in the platform's secret store.
  - Rotate the JWT secret and DB password when moving.
  - Never put them in the frontend bundle (the pre-deploy check already greps for this).
  - Keep the OpenAI key out of git, with a spending limit set in the OpenAI dashboard.
- **Backups:**
  - Nightly `mysqldump` (already scripted for migrations), plus provider snapshots.
  - Copy backups off the VM.
  - Test a restore once.
- **Student data (DPDP Act 2023):**
  - Students are minors, so verifiable parental consent and purpose limitation apply.
  - Keep data in an India region (DO Bangalore or Lightsail Mumbai) to avoid cross-border questions.
  - Keep the existing pseudonymous exports.
  - Define retention and deletion.
  - Have the school or institution act as the data fiduciary. This is not legal advice; confirm with the institution.
- **Updates:** unattended security upgrades for the OS; `npm audit` and `pip` updates at each deploy.

## Code / config changes needed

1. **Backend env vars:**
   - `PORT`;
   - `FRONTEND_ORIGIN=https://historybot-vsku.netlify.app` (CORS);
   - DB host, user and password;
   - JWT secret;
   - `RAG_INTERNAL_URL=http://127.0.0.1:8000`;
   - `LLM_PROVIDER` and the OpenAI key if used.
2. **RAG env:** `OLLAMA_BASE_URL=http://127.0.0.1:11434`, Chroma path, embed model name. Pull `nomic-embed-text` on the server.
3. **Frontend:** rebuild with `VITE_API_BASE_URL=https://<api-domain>` and redeploy to Netlify. After that the URL no longer changes with each tunnel restart.
4. **PDF fonts:** copy the fonts used by `rag/pdf/render.py` with the repo (check they are committed), and install `fonts-dejavu`/Noto as a fallback on Linux. Verify one PDF by eye after the move.
5. **Process manager:** systemd units (or pm2) for the backend, RAG and Ollama, with restart on failure. Health checks at `/api/v1/health`.
6. **Windows → Linux paths:** check any hard-coded Windows paths in scripts. The runtime code uses relative paths.

## Migration and data-transfer plan

1. Provision the VM in an India region and harden it (SSH keys, firewall, unattended upgrades).
2. Install Node 22, Python 3.10+, MySQL 8 and Ollama, then `ollama pull nomic-embed-text`.
3. `git clone`, then `npm ci` and `pip install -r requirements`.
4. Copy the files that are not in git (`.env` values, `data/chroma`, verified images) over SSH (scp/rsync).
5. Take a fresh `mysqldump` on the laptop, copy it over, `mysql < dump.sql`, and compare row counts table by table.
6. Start the services, run the smoke, privacy and quiz-test suites against the server, and test one PDF.
7. Point a DNS name at it with TLS, rebuild the frontend with the new API URL, deploy, and verify the live site.
8. Keep the laptop instance read-only for a week as a fallback, then retire the quick tunnel.

## Recommendation

**Primary:** one **DigitalOcean 4 GiB Droplet in Bangalore** (about $24 + $5–7 backups ≈ **$29–31/mo**, verified).
- It runs Node, RAG, Ollama embeddings (no re-indexing) and MySQL on one machine.
- Data stays in India.
- It uses a fixed domain with Caddy/Let's Encrypt or a named Cloudflare Tunnel.

**Equivalent alternative:** AWS Lightsail 4 GB in Mumbai at $24/mo (verified), if the institution prefers AWS. Add Lightsail managed MySQL ($30, encrypted) only if you want the database managed separately.

**Answers:** keep the paid OpenAI chat model with a hard spending cap (cost depends on usage, not estimated here). Local llama3 needs a much larger, more expensive machine.
