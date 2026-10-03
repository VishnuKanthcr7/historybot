-- HistoryBot initial schema
-- MySQL 8. Safe to re-run for CREATE DATABASE IF NOT EXISTS.
-- Does NOT drop databases or tables.
-- No passwords in this file.

CREATE DATABASE IF NOT EXISTS historybot
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE historybot;

-- Timestamps: DATETIME stored as UTC via UTC_TIMESTAMP().
-- Application must send/read UTC. UI may convert to local time.

CREATE TABLE IF NOT EXISTS anonymous_sessions (
  id CHAR(36) NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  last_seen_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  language CHAR(2) NOT NULL DEFAULT 'en',
  user_agent_hash CHAR(64) NULL,
  PRIMARY KEY (id),
  CONSTRAINT chk_anonymous_sessions_language CHECK (language IN ('en', 'kn')),
  INDEX idx_anonymous_sessions_last_seen (last_seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS conversations (
  id CHAR(36) NOT NULL,
  session_id CHAR(36) NOT NULL,
  title VARCHAR(255) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id),
  CONSTRAINT fk_conversations_session
    FOREIGN KEY (session_id) REFERENCES anonymous_sessions (id)
    ON DELETE CASCADE,
  INDEX idx_conversations_session_updated (session_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS messages (
  id CHAR(36) NOT NULL,
  conversation_id CHAR(36) NOT NULL,
  role VARCHAR(16) NOT NULL,
  content TEXT NOT NULL,
  language CHAR(2) NOT NULL DEFAULT 'en',
  source_pages JSON NULL,
  chunk_ids JSON NULL,
  retrieval_ok TINYINT(1) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id),
  CONSTRAINT fk_messages_conversation
    FOREIGN KEY (conversation_id) REFERENCES conversations (id)
    ON DELETE CASCADE,
  CONSTRAINT chk_messages_role CHECK (role IN ('user', 'assistant')),
  CONSTRAINT chk_messages_language CHECK (language IN ('en', 'kn')),
  INDEX idx_messages_conversation_created (conversation_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS analytics_events (
  id CHAR(36) NOT NULL,
  session_id CHAR(36) NULL,
  conversation_id CHAR(36) NULL,
  event_type VARCHAR(64) NOT NULL,
  topic_text VARCHAR(255) NULL,
  language CHAR(2) NULL,
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id),
  CONSTRAINT fk_analytics_session
    FOREIGN KEY (session_id) REFERENCES anonymous_sessions (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_analytics_conversation
    FOREIGN KEY (conversation_id) REFERENCES conversations (id)
    ON DELETE SET NULL,
  CONSTRAINT chk_analytics_event_type CHECK (event_type IN (
    'SESSION_STARTED',
    'QUESTION_ASKED',
    'ANSWER_GENERATED',
    'LANGUAGE_CHANGED',
    'E_CONTENT_GENERATED',
    'PDF_DOWNLOADED',
    'NEW_CHAT'
  )),
  CONSTRAINT chk_analytics_language CHECK (language IS NULL OR language IN ('en', 'kn')),
  INDEX idx_analytics_event_created (event_type, created_at),
  INDEX idx_analytics_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS econtent_documents (
  id CHAR(36) NOT NULL,
  session_id CHAR(36) NOT NULL,
  conversation_id CHAR(36) NULL,
  topic VARCHAR(255) NOT NULL,
  language CHAR(2) NOT NULL DEFAULT 'en',
  body_json JSON NOT NULL,
  source_pages JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id),
  CONSTRAINT fk_econtent_session
    FOREIGN KEY (session_id) REFERENCES anonymous_sessions (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_econtent_conversation
    FOREIGN KEY (conversation_id) REFERENCES conversations (id)
    ON DELETE SET NULL,
  CONSTRAINT chk_econtent_language CHECK (language IN ('en', 'kn')),
  INDEX idx_econtent_session_created (session_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS verified_images (
  id CHAR(36) NOT NULL,
  topic VARCHAR(255) NOT NULL,
  person_name VARCHAR(255) NULL,
  file_path VARCHAR(1024) NOT NULL,
  caption VARCHAR(512) NULL,
  source VARCHAR(512) NULL,
  license VARCHAR(255) NULL,
  verification_status VARCHAR(16) NOT NULL DEFAULT 'unverified',
  verified_by VARCHAR(255) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id),
  CONSTRAINT chk_images_status CHECK (verification_status IN ('verified', 'unverified', 'rejected')),
  INDEX idx_images_topic (topic),
  INDEX idx_images_status (verification_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
