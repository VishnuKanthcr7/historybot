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
