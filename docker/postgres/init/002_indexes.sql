CREATE INDEX IF NOT EXISTS idx_sessions_mode_started
    ON sessions (mode, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON messages (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_memory_facts_mode_key
    ON memory_facts (mode, key);

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_mode_created
    ON memory_embeddings (mode, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_vector
    ON memory_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_audit_logs_mode_created
    ON audit_logs (mode, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_model_scores_run_model
    ON model_scores (benchmark_run_id, model);
