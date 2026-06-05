CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sessions (
    id uuid PRIMARY KEY,
    mode text NOT NULL,
    title text,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    summary text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS messages (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role text NOT NULL,
    content text NOT NULL,
    created_at timestamptz NOT NULL,
    token_count integer,
    model text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS memory_facts (
    id uuid PRIMARY KEY,
    mode text NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL,
    source_session_id uuid REFERENCES sessions(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE (mode, key)
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id uuid PRIMARY KEY,
    mode text NOT NULL,
    session_id uuid REFERENCES sessions(id) ON DELETE SET NULL,
    source_type text NOT NULL,
    source_id uuid,
    content text NOT NULL,
    embedding vector(768) NOT NULL,
    created_at timestamptz NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id uuid PRIMARY KEY,
    mode text,
    event_type text NOT NULL,
    event jsonb NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id uuid PRIMARY KEY,
    name text,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS model_scores (
    id uuid PRIMARY KEY,
    benchmark_run_id uuid REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    model text NOT NULL,
    task_id text NOT NULL,
    score numeric,
    verdict text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL
);
