-- Persistent per-account daily AI usage counter (chat answers and learning modules).
-- Additive and idempotent: creates one new table only if it does not exist.
-- It does not change or drop any existing table.
-- Apply it with: node backend/scripts/migrate-ai-usage.mjs  (backs up the database first)

CREATE TABLE IF NOT EXISTS ai_usage (
  user_id CHAR(36) NOT NULL,
  usage_day DATE NOT NULL,
  request_count INT UNSIGNED NOT NULL DEFAULT 0,
  updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (user_id, usage_day),
  CONSTRAINT fk_ai_usage_user
    FOREIGN KEY (user_id) REFERENCES users (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
