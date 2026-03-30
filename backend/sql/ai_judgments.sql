CREATE TABLE IF NOT EXISTS ai_judgments (
    id UUID PRIMARY KEY,
    plant_id VARCHAR(50) NULL REFERENCES plants(id),
    fruit_id VARCHAR(50) NULL REFERENCES fruits(id),
    zone_id VARCHAR(50) NULL REFERENCES zones(id),
    judgment_type VARCHAR(30) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    raw_label VARCHAR(100) NOT NULL,
    canonical_code VARCHAR(100) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    risk_level VARCHAR(20) NULL,
    recommended_action_code VARCHAR(50) NOT NULL DEFAULT 'NONE',
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    image_url VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_ai_judgments_judgment_type ON ai_judgments (judgment_type);
CREATE INDEX IF NOT EXISTS ix_ai_judgments_canonical_code ON ai_judgments (canonical_code);
CREATE INDEX IF NOT EXISTS ix_ai_judgments_plant_id ON ai_judgments (plant_id);
CREATE INDEX IF NOT EXISTS ix_ai_judgments_fruit_id ON ai_judgments (fruit_id);
CREATE INDEX IF NOT EXISTS ix_ai_judgments_zone_id ON ai_judgments (zone_id);
CREATE INDEX IF NOT EXISTS ix_ai_judgments_created_at ON ai_judgments (created_at);
