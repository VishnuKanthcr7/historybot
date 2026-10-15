-- Quizzes, learning activities and learner analytics (additive; no existing table is dropped or rebuilt).
-- Apply with: node backend/scripts/migrate-quiz.mjs   (backs up the database with mysqldump first)

CREATE TABLE IF NOT EXISTS schema_migrations (
  id VARCHAR(64) NOT NULL,
  applied_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Question bank. A question is gradable only for the types below.
CREATE TABLE IF NOT EXISTS quiz_questions (
  id CHAR(36) NOT NULL,
  seed_key VARCHAR(64) NULL,
  qtype VARCHAR(16) NOT NULL,
  prompt TEXT NOT NULL,
  options_json JSON NULL,
  answer_json JSON NOT NULL,
  explanation TEXT NULL,
  topic VARCHAR(120) NOT NULL,
  difficulty VARCHAR(8) NOT NULL DEFAULT 'medium',
  source_document VARCHAR(255) NULL,
  textbook_page INT NULL,
  source_chunk_id VARCHAR(128) NULL,
  source_excerpt VARCHAR(1000) NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'draft',
  origin VARCHAR(16) NOT NULL DEFAULT 'teacher',
  created_by CHAR(36) NULL,
  reviewed_by CHAR(36) NULL,
  reviewed_at DATETIME(3) NULL,
  review_note VARCHAR(500) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id),
  UNIQUE KEY uq_quiz_questions_seed (seed_key),
  INDEX idx_quiz_questions_status_topic (status, topic),
  CONSTRAINT chk_qq_type CHECK (qtype IN ('mcq', 'true_false', 'match', 'order', 'fill_blank')),
  CONSTRAINT chk_qq_status CHECK (status IN ('draft', 'published', 'archived')),
  CONSTRAINT chk_qq_difficulty CHECK (difficulty IN ('easy', 'medium', 'hard')),
  CONSTRAINT fk_qq_created_by FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT fk_qq_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quizzes (
  id CHAR(36) NOT NULL,
  seed_key VARCHAR(64) NULL,
  title VARCHAR(160) NOT NULL,
  description VARCHAR(500) NULL,
  topic VARCHAR(120) NOT NULL,
  difficulty VARCHAR(8) NOT NULL DEFAULT 'mixed',
  mode VARCHAR(12) NOT NULL DEFAULT 'practice',
  activity_type VARCHAR(24) NOT NULL DEFAULT 'quiz',
  assessment_phase VARCHAR(8) NOT NULL DEFAULT 'none',
  time_limit_sec INT NULL,
  max_attempts INT NULL,
  reveal_answers VARCHAR(16) NOT NULL DEFAULT 'after_submit',
  available_from DATETIME(3) NULL,
  available_until DATETIME(3) NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'draft',
  owner_user_id CHAR(36) NULL,
  created_by CHAR(36) NULL,
  published_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  updated_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  PRIMARY KEY (id),
  UNIQUE KEY uq_quizzes_seed (seed_key),
  INDEX idx_quizzes_status (status, activity_type),
  INDEX idx_quizzes_owner (owner_user_id),
  CONSTRAINT chk_quiz_mode CHECK (mode IN ('practice', 'assessment')),
  CONSTRAINT chk_quiz_status CHECK (status IN ('draft', 'published', 'archived')),
  CONSTRAINT chk_quiz_phase CHECK (assessment_phase IN ('none', 'pre', 'post')),
  CONSTRAINT chk_quiz_reveal CHECK (reveal_answers IN ('after_submit', 'after_close', 'never')),
  CONSTRAINT chk_quiz_difficulty CHECK (difficulty IN ('easy', 'medium', 'hard', 'mixed')),
  CONSTRAINT fk_quiz_owner FOREIGN KEY (owner_user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_quiz_created_by FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quiz_items (
  quiz_id CHAR(36) NOT NULL,
  question_id CHAR(36) NOT NULL,
  position INT NOT NULL,
  points DECIMAL(6,2) NOT NULL DEFAULT 1,
  PRIMARY KEY (quiz_id, question_id),
  INDEX idx_quiz_items_question (question_id),
  CONSTRAINT fk_qi_quiz FOREIGN KEY (quiz_id) REFERENCES quizzes (id) ON DELETE CASCADE,
  CONSTRAINT fk_qi_question FOREIGN KEY (question_id) REFERENCES quiz_questions (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quiz_attempts (
  id CHAR(36) NOT NULL,
  quiz_id CHAR(36) NOT NULL,
  user_id CHAR(36) NOT NULL,
  attempt_no INT NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'in_progress',
  started_at DATETIME(3) NOT NULL DEFAULT (UTC_TIMESTAMP(3)),
  deadline_at DATETIME(3) NULL,
  submitted_at DATETIME(3) NULL,
  score_points DECIMAL(8,2) NULL,
  max_points DECIMAL(8,2) NULL,
  percent DECIMAL(5,2) NULL,
  duration_sec INT NULL,
  question_order_json JSON NOT NULL,
  autosave_json JSON NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_attempt_no (quiz_id, user_id, attempt_no),
  INDEX idx_attempts_user (user_id, submitted_at),
  INDEX idx_attempts_quiz (quiz_id, status),
  CONSTRAINT chk_attempt_status CHECK (status IN ('in_progress', 'submitted')),
  CONSTRAINT fk_attempt_quiz FOREIGN KEY (quiz_id) REFERENCES quizzes (id) ON DELETE CASCADE,
  CONSTRAINT fk_attempt_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quiz_answers (
  id CHAR(36) NOT NULL,
  attempt_id CHAR(36) NOT NULL,
  question_id CHAR(36) NOT NULL,
  response_json JSON NULL,
  is_correct TINYINT(1) NOT NULL DEFAULT 0,
  points DECIMAL(6,2) NOT NULL DEFAULT 0,
  max_points DECIMAL(6,2) NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uq_answer (attempt_id, question_id),
  INDEX idx_answers_question (question_id),
  CONSTRAINT fk_answer_attempt FOREIGN KEY (attempt_id) REFERENCES quiz_attempts (id) ON DELETE CASCADE,
  CONSTRAINT fk_answer_question FOREIGN KEY (question_id) REFERENCES quiz_questions (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- analytics_events gains a nullable user_id (added by migrate-quiz.mjs only if missing):
--   ALTER TABLE analytics_events ADD COLUMN user_id CHAR(36) NULL,
--     ADD INDEX idx_analytics_user (user_id, created_at), ADD INDEX idx_analytics_type (event_type, created_at);
-- The event-type CHECK is widened by migrate-quiz.mjs to add QUIZ_STARTED, QUIZ_SUBMITTED, ACTIVITY_CREATED.
-- Quiz/activity events store ids and scores only, never chat text.
