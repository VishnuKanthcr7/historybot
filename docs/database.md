# HistoryBot database

**Database name:** `historybot`  
**Engine:** MySQL 8.0.42 (Windows service `MySQL80`)  
**Character set:** `utf8mb4`  
**Collation:** `utf8mb4_unicode_ci` (English + Kannada)  
**Timestamps:** `DATETIME(3)` stored in **UTC** via `UTC_TIMESTAMP(3)`. The UI may convert to local time later.

This schema is isolated from Odoo, Infomax POS, and `PostgreSQL_For_Odoo`. Do not use those instances.

## Privacy

`anonymous_sessions` is **not** a student identity. No name, phone, email, school, student ID, photos, or precise GPS. `user_agent_hash` is optional and must be a hash, not the raw UA string if you want extra caution. `metadata_json` must not store PII. `topic_text` is capped at 255 characters.

## Tables

### anonymous_sessions

Anonymous browser session (`CHAR(36)` UUID). `language` is `en` or `kn`.

### conversations

One session has many conversations. `session_id` → `anonymous_sessions.id` **ON DELETE CASCADE**. Index: `(session_id, updated_at)`.

### messages

Chat turns. `role` is only `user` or `assistant` (student-visible). An internal/system role was **not** added so hidden prompts are not stored as chat content. `source_pages` and `chunk_ids` are JSON. `conversation_id` → `conversations.id` **ON DELETE CASCADE**. Index: `(conversation_id, created_at)`.

### analytics_events

Anonymous events: `SESSION_STARTED`, `QUESTION_ASKED`, `ANSWER_GENERATED`, `LANGUAGE_CHANGED`, `E_CONTENT_GENERATED`, `PDF_DOWNLOADED`, `NEW_CHAT`.  
`session_id` → sessions **ON DELETE CASCADE**. `conversation_id` → conversations **ON DELETE SET NULL**. Indexes: `(event_type, created_at)`, `session_id`.

### econtent_documents

Structured E-content JSON (PDF is generated later from this; **no PDF BLOB**). `session_id` required **ON DELETE CASCADE**. `conversation_id` nullable **ON DELETE SET NULL**.

### verified_images

Image **metadata only**. `verification_status`: `verified` | `unverified` | `rejected`. Students must only see `verified` rows in later phases.

## Relationships

```
anonymous_sessions
  ├── conversations
  │     └── messages
  ├── analytics_events
  └── econtent_documents
        └── (optional) conversations
```

## Migration

From a MySQL client that can create databases:

```text
mysql -h localhost -P 3306 -u <user> -p < scripts/sql/001_initial_schema.sql
```

File contains **no passwords**. Uses `CREATE DATABASE IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` (no `DROP DATABASE` / `DROP TABLE`).

## Environment (local)

Set in `.env` (never commit):

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE=historybot`
