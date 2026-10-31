-- StatCage database: the 4 clean tables built by statcage.ingest.build.
-- The rules mirror statcage/ingest/validate.py, so Postgres also refuses bad rows.
-- Docker runs this file automatically the first time the database starts empty.

CREATE TABLE events (
    event_id  TEXT PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    date      DATE NOT NULL CHECK (date >= '1993-11-12'),
    location  TEXT NOT NULL,
    country   TEXT NOT NULL
);

CREATE TABLE fighters (
    fighter_id  TEXT PRIMARY KEY,
    name        TEXT NOT NULL CHECK (name <> ''),
    alt_name    TEXT,
    nickname    TEXT,
    height_in   SMALLINT CHECK (height_in BETWEEN 48 AND 96),
    weight_lbs  SMALLINT CHECK (weight_lbs BETWEEN 100 AND 800),
    reach_in    SMALLINT CHECK (reach_in BETWEEN 48 AND 96),
    stance      TEXT,
    dob         DATE CHECK (dob >= '1900-01-01')
);

CREATE TABLE fights (
    fight_id          TEXT PRIMARY KEY,
    event_id          TEXT NOT NULL REFERENCES events,
    fighter_a_id      TEXT NOT NULL REFERENCES fighters,
    fighter_b_id      TEXT NOT NULL REFERENCES fighters,
    result            TEXT NOT NULL CHECK (result IN ('win', 'draw', 'no_contest')),
    winner_id         TEXT REFERENCES fighters,
    method            TEXT NOT NULL,
    method_detail     TEXT,
    end_round         SMALLINT NOT NULL CHECK (end_round BETWEEN 1 AND 5),
    end_time_s        INTEGER NOT NULL CHECK (end_time_s > 0),
    -- Regulation rounds only: early UFC fights could go to overtime past this.
    scheduled_rounds  SMALLINT,
    fight_time_s      INTEGER NOT NULL CHECK (fight_time_s BETWEEN end_time_s AND 2400),
    weight_class      TEXT,
    womens            BOOLEAN NOT NULL,
    title_fight       BOOLEAN NOT NULL,
    interim           BOOLEAN NOT NULL,
    tournament        BOOLEAN NOT NULL,
    referee           TEXT,

    CHECK (fighter_a_id <> fighter_b_id),
    CHECK ((result = 'win') = (winner_id IS NOT NULL)),
    CHECK (winner_id IN (fighter_a_id, fighter_b_id))
);

-- One row per fighter per round.
CREATE TABLE fight_stats (
    fight_id            TEXT NOT NULL REFERENCES fights,
    fighter_id          TEXT NOT NULL REFERENCES fighters,
    round               SMALLINT NOT NULL CHECK (round BETWEEN 1 AND 5),
    kd                  SMALLINT NOT NULL CHECK (kd >= 0),
    sig_landed          SMALLINT NOT NULL CHECK (sig_landed >= 0),
    sig_attempted       SMALLINT NOT NULL,
    total_landed        SMALLINT NOT NULL CHECK (total_landed >= 0),
    total_attempted     SMALLINT NOT NULL,
    td_landed           SMALLINT NOT NULL CHECK (td_landed >= 0),
    td_attempted        SMALLINT NOT NULL,
    head_landed         SMALLINT NOT NULL CHECK (head_landed >= 0),
    head_attempted      SMALLINT NOT NULL,
    body_landed         SMALLINT NOT NULL CHECK (body_landed >= 0),
    body_attempted      SMALLINT NOT NULL,
    leg_landed          SMALLINT NOT NULL CHECK (leg_landed >= 0),
    leg_attempted       SMALLINT NOT NULL,
    distance_landed     SMALLINT NOT NULL CHECK (distance_landed >= 0),
    distance_attempted  SMALLINT NOT NULL,
    clinch_landed       SMALLINT NOT NULL CHECK (clinch_landed >= 0),
    clinch_attempted    SMALLINT NOT NULL,
    ground_landed       SMALLINT NOT NULL CHECK (ground_landed >= 0),
    ground_attempted    SMALLINT NOT NULL,
    sub_att             SMALLINT NOT NULL CHECK (sub_att >= 0),
    rev                 SMALLINT NOT NULL CHECK (rev >= 0),
    -- Unknown for some early fights, which is different from 0.
    ctrl_s              SMALLINT CHECK (ctrl_s BETWEEN 0 AND 1860),

    PRIMARY KEY (fight_id, fighter_id, round),
    CHECK (sig_landed <= sig_attempted AND total_landed <= total_attempted
           AND td_landed <= td_attempted AND head_landed <= head_attempted
           AND body_landed <= body_attempted AND leg_landed <= leg_attempted
           AND distance_landed <= distance_attempted AND clinch_landed <= clinch_attempted
           AND ground_landed <= ground_attempted),
    CHECK (sig_landed <= total_landed AND sig_attempted <= total_attempted),
    CHECK (head_landed + body_landed + leg_landed = sig_landed),
    CHECK (head_attempted + body_attempted + leg_attempted = sig_attempted),
    CHECK (distance_landed + clinch_landed + ground_landed = sig_landed),
    CHECK (distance_attempted + clinch_attempted + ground_attempted = sig_attempted)
);

-- The agent's most common question is "every fight of fighter X", so index those lookups.
CREATE INDEX fights_event_id_idx ON fights (event_id);
CREATE INDEX fights_fighter_a_id_idx ON fights (fighter_a_id);
CREATE INDEX fights_fighter_b_id_idx ON fights (fighter_b_id);
CREATE INDEX fight_stats_fighter_id_idx ON fight_stats (fighter_id);
