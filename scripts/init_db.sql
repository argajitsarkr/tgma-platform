-- TGMA Platform: PostgreSQL-specific initialization
-- Run this AFTER the SQLAlchemy tables are created (via init_db.py or flask db upgrade)

-- Enable trigram extension for fuzzy duplicate detection
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create indexes for trigram-based fuzzy search
CREATE INDEX IF NOT EXISTS ix_participants_name_trgm ON participants USING gin (full_name gin_trgm_ops);

-- Grant statement for production (adjust username as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tgma_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tgma_user;
