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
