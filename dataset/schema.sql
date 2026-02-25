CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE categories (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE games (
    id       SERIAL PRIMARY KEY,
    air_date DATE NOT NULL,
    season   SMALLINT,
    source   TEXT NOT NULL DEFAULT 'regular',
    notes    TEXT,
    UNIQUE (air_date, source)
);

CREATE TABLE clues (
    id                 SERIAL PRIMARY KEY,
    game_id            INT NOT NULL REFERENCES games(id),
    round              SMALLINT NOT NULL,
    category_id        INT NOT NULL REFERENCES categories(id),
    clue_value         INT NOT NULL,
    daily_double_value INT,
    answer             TEXT NOT NULL,
    question           TEXT NOT NULL,
    comments           TEXT
);

CREATE TABLE game_contestants (
    id              SERIAL PRIMARY KEY,
    game_id         INT NOT NULL REFERENCES games(id),
    contestant_name TEXT NOT NULL,
    podium_position SMALLINT NOT NULL,
    score_single    INT,
    score_double    INT,
    score_final     INT,
    coryat_score    INT,
    correct_count   SMALLINT,
    wrong_count     SMALLINT,
    UNIQUE (game_id, podium_position)
);

CREATE INDEX idx_clues_game_id ON clues(game_id);
CREATE INDEX idx_clues_category_id ON clues(category_id);
CREATE INDEX idx_clues_answer_trgm ON clues USING gin (answer gin_trgm_ops);
CREATE INDEX idx_clues_question_trgm ON clues USING gin (question gin_trgm_ops);
CREATE INDEX idx_games_air_date ON games(air_date);
CREATE INDEX idx_games_season ON games(season);
CREATE INDEX idx_game_contestants_name ON game_contestants(contestant_name);

-- Generic agent observability tables (reusable for future agent features)
CREATE TABLE agent_runs (
    id              BIGSERIAL PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    run_type        TEXT NOT NULL,
    agent_name      TEXT NOT NULL,
    agent_version   TEXT NOT NULL,
    policy_version  TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('started', 'completed', 'failed')),
    model           TEXT,
    prompt_version  TEXT,
    input_payload   JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_payload  JSONB,
    guardrail_flags JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message   TEXT,
    prompt_tokens   INT,
    completion_tokens INT,
    total_tokens    INT,
    latency_ms      INT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

CREATE TABLE agent_run_events (
    id           BIGSERIAL PRIMARY KEY,
    agent_run_id BIGINT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    event_type   TEXT NOT NULL,
    level        TEXT NOT NULL CHECK (level IN ('info', 'warn', 'error')),
    message      TEXT NOT NULL,
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_run_artifacts (
    id            BIGSERIAL PRIMARY KEY,
    agent_run_id  BIGINT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    content       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Answer + appeal workflow tables
CREATE TABLE answer_attempts (
    id                         BIGSERIAL PRIMARY KEY,
    clue_id                    INT NOT NULL REFERENCES clues(id),
    user_response              TEXT NOT NULL,
    expected_response_snapshot TEXT NOT NULL,
    fuzzy_correct              BOOLEAN NOT NULL,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE answer_appeals (
    id                 BIGSERIAL PRIMARY KEY,
    answer_attempt_id  BIGINT NOT NULL UNIQUE REFERENCES answer_attempts(id) ON DELETE CASCADE,
    agent_run_id       BIGINT REFERENCES agent_runs(id),
    status             TEXT NOT NULL CHECK (status IN ('pending', 'decided', 'error')),
    user_justification TEXT,
    overturn           BOOLEAN,
    final_correct      BOOLEAN,
    reason_code        TEXT,
    reason_text        TEXT,
    confidence         NUMERIC(4, 3),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at         TIMESTAMPTZ
);

CREATE INDEX idx_agent_runs_trace_id ON agent_runs(trace_id);
CREATE INDEX idx_agent_runs_run_type ON agent_runs(run_type);
CREATE INDEX idx_agent_events_run_id ON agent_run_events(agent_run_id);
CREATE INDEX idx_agent_artifacts_run_id ON agent_run_artifacts(agent_run_id);
CREATE INDEX idx_answer_attempts_clue_id ON answer_attempts(clue_id);
CREATE INDEX idx_answer_attempts_created_at ON answer_attempts(created_at);
CREATE INDEX idx_answer_appeals_status ON answer_appeals(status);

-- New grading source-of-truth table (manual appeal flow is deprecated)
CREATE TABLE answer_grading_events (
    id BIGSERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL,
    challenge_date DATE,
    player_token TEXT,
    clue_id INT NOT NULL REFERENCES clues(id),
    user_response_raw TEXT NOT NULL,
    expected_response_snapshot TEXT NOT NULL,
    user_response_normalized TEXT NOT NULL,
    expected_response_normalized TEXT NOT NULL,
    deterministic_stage TEXT NOT NULL CHECK (
        deterministic_stage IN ('exact', 'normalized', 'variant', 'none')
    ),
    deterministic_decision TEXT NOT NULL CHECK (
        deterministic_decision IN ('accept', 'reject', 'defer_to_llm')
    ),
    similarity_score REAL,
    token_overlap_score REAL,
    has_parenthetical_or BOOLEAN NOT NULL DEFAULT FALSE,
    looks_like_person_name BOOLEAN NOT NULL DEFAULT FALSE,
    llm_invoked BOOLEAN NOT NULL DEFAULT FALSE,
    llm_run_id BIGINT REFERENCES agent_runs(id),
    llm_confidence NUMERIC(4, 3),
    llm_reason_code TEXT,
    llm_reason_text TEXT,
    final_decision TEXT NOT NULL CHECK (final_decision IN ('correct', 'incorrect')),
    decision_source TEXT NOT NULL CHECK (decision_source IN ('deterministic', 'llm')),
    overturn_of_event_id BIGINT REFERENCES answer_grading_events(id),
    latency_ms_total INT NOT NULL,
    latency_ms_deterministic INT NOT NULL,
    latency_ms_llm INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_age_clue_created ON answer_grading_events(clue_id, created_at DESC);
CREATE INDEX idx_age_player_date ON answer_grading_events(challenge_date, player_token);
CREATE INDEX idx_age_final_source ON answer_grading_events(final_decision, decision_source);
CREATE INDEX idx_age_llm_invoked ON answer_grading_events(llm_invoked);

-- Daily challenge mode tables
CREATE TABLE daily_challenges (
    challenge_date DATE PRIMARY KEY,
    single_category_name TEXT NOT NULL,
    single_clue_ids INT[] NOT NULL,
    double_category_name TEXT NOT NULL,
    double_clue_ids INT[] NOT NULL,
    final_category_name TEXT NOT NULL,
    final_clue_id INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE daily_player_progress (
    id BIGSERIAL PRIMARY KEY,
    challenge_date DATE NOT NULL REFERENCES daily_challenges(challenge_date) ON DELETE CASCADE,
    player_token TEXT NOT NULL,
    current_score INT NOT NULL DEFAULT 0,
    answers_json JSONB NOT NULL,
    final_attempt_id BIGINT,
    final_wager INT,
    final_response TEXT,
    final_correct BOOLEAN,
    final_expected_response TEXT,
    final_score_delta INT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (challenge_date, player_token)
);

CREATE INDEX idx_daily_progress_token ON daily_player_progress(player_token);
CREATE INDEX idx_daily_progress_challenge_date ON daily_player_progress(challenge_date);
