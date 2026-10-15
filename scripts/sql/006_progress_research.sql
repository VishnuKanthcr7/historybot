-- Module progress, research instruments (questionnaires) and pre/post pairing (additive only).
-- Apply with: node backend/scripts/migrate-006.mjs   (mysqldump backup first)
-- Column additions and CHECK widening on existing tables are done by migrate-006.mjs, idempotently:
--   analytics_events.idempotency_key (UNIQUE) and new event types
--   quiz_attempts.end_reason ('submitted' | 'timed_out')
--   quizzes.pre_quiz_id (post-test linked to its pre-test), quizzes.source_econtent_id (module checkpoint)
--   quiz_questions.status adds 'needs_review'

-- One row per student per learning module. Opening or downloading is NOT completion.
-- completed_at is set only by an explicit "Mark complete" or by submitting the module's checkpoint quiz.
CREATE TABLE IF NOT EXISTS module_progress (
  user_id CHAR(36) NOT NULL,
  econtent_id CHAR(36) NOT NULL,
  first_opened_at DATETIME(3) NULL,
  last_opened_at DATETIME(3) NULL,
  open_count INT NOT NULL DEFAULT 0,
  pdf_downloads INT NOT NULL DEFAULT 0,
  completed_at DATETIME(3) NULL,
  completion_method VARCHAR(12) NULL,
  PRIMARY KEY (user_id, econtent_id),
  INDEX idx_module_progress_done (completed_at),
  CONSTRAINT chk_mp_method CHECK (completion_method IS NULL OR completion_method IN ('explicit', 'checkpoint')),
  CONSTRAINT fk_mp_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_mp_econtent FOREIGN KEY (econtent_id) REFERENCES econtent_documents (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Questionnaires (Likert). Items marked requires_approval are placeholders and block publishing.
CREATE TABLE IF NOT EXISTS research_instruments (
  id CHAR(36) NOT NULL,
  seed_key VARCHAR(64) NULL,
  title VARCHAR(160) NOT NULL,
  construct VARCHAR(120) NOT NULL,
  description VARCHAR(1000) NULL,
  scale_min TINYINT NOT NULL DEFAULT 1,
  scale_max TINYINT NOT NULL DEFAULT 5,
  scale_labels_json JSON NULL,
  min_answered_ratio DECIMAL(3,2) NOT NULL DEFAULT 0.50,
  phase VARCHAR(8) NOT NULL DEFAULT 'none',
  pre_instrument_id CHAR(36) NULL,
  available_from DATETIME(3) NULL,
  available_until DATETIME(3) NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'draft',
  approval_note VARCHAR(500) NULL,
  approved_by CHAR(36) NULL,
  approved_at DATETIME(3) NULL,
  created_by CHAR(36) NULL,
  published_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id),
  UNIQUE KEY uq_research_instruments_seed (seed_key),
  CONSTRAINT chk_ri_status CHECK (status IN ('draft', 'published', 'archived')),
  CONSTRAINT chk_ri_phase CHECK (phase IN ('none', 'pre', 'post')),
  CONSTRAINT chk_ri_scale CHECK (scale_min >= 0 AND scale_max > scale_min AND scale_max <= 10),
  CONSTRAINT fk_ri_pre FOREIGN KEY (pre_instrument_id) REFERENCES research_instruments (id) ON DELETE SET NULL,
  CONSTRAINT fk_ri_created_by FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT fk_ri_approved_by FOREIGN KEY (approved_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS research_items (
  id CHAR(36) NOT NULL,
  instrument_id CHAR(36) NOT NULL,
  position INT NOT NULL,
  text VARCHAR(500) NOT NULL,
  subscale VARCHAR(80) NOT NULL DEFAULT 'Total',
  reverse_scored TINYINT(1) NOT NULL DEFAULT 0,
  requires_approval TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  INDEX idx_research_items_instrument (instrument_id, position),
  CONSTRAINT fk_rit_instrument FOREIGN KEY (instrument_id) REFERENCES research_instruments (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- One response per student per instrument. A NULL item value means "not answered" (missing), never zero.
CREATE TABLE IF NOT EXISTS research_responses (
  id CHAR(36) NOT NULL,
  instrument_id CHAR(36) NOT NULL,
  user_id CHAR(36) NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'in_progress',
  started_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  submitted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_research_response (instrument_id, user_id),
  INDEX idx_research_responses_user (user_id),
  CONSTRAINT chk_rr_status CHECK (status IN ('in_progress', 'submitted')),
  CONSTRAINT fk_rr_instrument FOREIGN KEY (instrument_id) REFERENCES research_instruments (id) ON DELETE CASCADE,
  CONSTRAINT fk_rr_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS research_response_items (
  response_id CHAR(36) NOT NULL,
  item_id CHAR(36) NOT NULL,
  value TINYINT NULL,
  PRIMARY KEY (response_id, item_id),
  INDEX idx_rri_item (item_id),
  CONSTRAINT fk_rri_response FOREIGN KEY (response_id) REFERENCES research_responses (id) ON DELETE CASCADE,
  CONSTRAINT fk_rri_item FOREIGN KEY (item_id) REFERENCES research_items (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
