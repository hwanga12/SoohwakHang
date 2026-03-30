-- AgriBot PostgreSQL schema 초안
-- Reference:
--   1) ERD_구조_예시.md
--   2) 수확해조_프로젝트_개발_계획_및_협업_가이드.md
--
-- Notes:
-- - PostgreSQL 16 기준 초안
-- - 빈 DB 또는 마이그레이션 초기 단계에서 실행하는 것을 권장
-- - timestamptz 사용으로 팀원 환경이 달라도 시간 해석이 일관되게 유지됨

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    CREATE TYPE robot_status_type AS ENUM (
        'IDLE',
        'PATROL',
        'OBSERVE',
        'HARVEST',
        'RETURN_HOME',
        'IOT_ACTION',
        'ERROR',
        'STOPPED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE mission_type AS ENUM (
        'PATROL',
        'HARVEST',
        'RETURN_HOME',
        'IOT_ACTION',
        'MANUAL_GOTO'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE mission_status_type AS ENUM (
        'PENDING',
        'RUNNING',
        'PAUSED',
        'COMPLETED',
        'FAILED',
        'CANCELED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE fruit_ripeness_type AS ENUM (
        'UNRIPE',
        'TURNING',
        'RIPE'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE fruit_status_type AS ENUM (
        'VISIBLE',
        'TARGETED',
        'HARVESTED',
        'LOST'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE device_type AS ENUM (
        'WATER_PUMP',
        'CURTAIN',
        'FAN',
        'NUTRIENT'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE device_control_mode_type AS ENUM (
        'AUTO',
        'MANUAL',
        'MANUAL_OVERRIDE',
        'DISABLED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE device_state_type AS ENUM (
        'IDLE',
        'OFF',
        'ON',
        'OPEN',
        'CLOSED',
        'PARTIAL',
        'RUNNING',
        'ERROR'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE recommendation_type AS ENUM (
        'WATERING',
        'CURTAIN',
        'FAN',
        'NUTRIENTS'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE recommendation_priority_type AS ENUM (
        'LOW',
        'MEDIUM',
        'HIGH'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE recommendation_status_type AS ENUM (
        'PENDING',
        'APPROVED',
        'REJECTED',
        'AUTO_EXECUTED',
        'EXPIRED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE request_source_type AS ENUM (
        'AUTO_RULE',
        'USER_BUTTON',
        'MISSION_FLOW',
        'API',
        'SCHEDULED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE actuation_command_type AS ENUM (
        'WATERING',
        'CURTAIN',
        'FAN',
        'NUTRIENTS',
        'STOP'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE actuation_command_status_type AS ENUM (
        'REQUESTED',
        'SENT',
        'ACKED',
        'COMPLETED',
        'FAILED',
        'CANCELED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE actuation_result_type AS ENUM (
        'SUCCESS',
        'FAILED',
        'TIMEOUT',
        'REJECTED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE alert_type AS ENUM (
        'DISEASE',
        'SENSOR_ERROR',
        'ROBOT_ERROR',
        'DEVICE_ERROR',
        'STOP'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE alert_severity_type AS ENUM (
        'INFO',
        'WARNING',
        'CRITICAL'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS zones (
    id              VARCHAR(50) PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    bounds          JSONB NOT NULL DEFAULT '{}'::jsonb,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE zones IS '비닐하우스 구역 정의';
COMMENT ON COLUMN zones.bounds IS '구역 좌표 범위 JSON';

CREATE TABLE IF NOT EXISTS plants (
    id                  VARCHAR(50) PRIMARY KEY,
    zone_id             VARCHAR(50) NOT NULL REFERENCES zones(id),
    crop_name           VARCHAR(50) NOT NULL,
    position            JSONB NOT NULL DEFAULT '{}'::jsonb,
    health_score        NUMERIC(4,3) CHECK (health_score BETWEEN 0 AND 1),
    growth_stage        NUMERIC(4,3) CHECK (growth_stage BETWEEN 0 AND 1),
    needs_water         BOOLEAN NOT NULL DEFAULT FALSE,
    ready_to_harvest    BOOLEAN NOT NULL DEFAULT FALSE,
    last_observed_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE plants IS '식물 현재 상태';
COMMENT ON COLUMN plants.position IS '식물 world 좌표 JSON';

CREATE TABLE IF NOT EXISTS fruits (
    id                  VARCHAR(50) PRIMARY KEY,
    plant_id            VARCHAR(50) NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    position            JSONB NOT NULL DEFAULT '{}'::jsonb,
    ripeness_stage      fruit_ripeness_type NOT NULL DEFAULT 'UNRIPE',
    ready_to_harvest    BOOLEAN NOT NULL DEFAULT FALSE,
    current_status      fruit_status_type NOT NULL DEFAULT 'VISIBLE',
    last_observed_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE fruits IS '토마토 개체 단위 추적';

CREATE TABLE IF NOT EXISTS robots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(100) NOT NULL UNIQUE,
    status              robot_status_type NOT NULL DEFAULT 'IDLE',
    battery_level       NUMERIC(5,2) CHECK (battery_level BETWEEN 0 AND 100),
    current_zone_id     VARCHAR(50) REFERENCES zones(id) ON DELETE SET NULL,
    current_pose        JSONB NOT NULL DEFAULT '{}'::jsonb,
    speed_mps           NUMERIC(6,3),
    error_message       TEXT,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE robots IS '로봇 현재 상태';

CREATE TABLE IF NOT EXISTS missions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id            UUID NOT NULL REFERENCES robots(id),
    mission_type        mission_type NOT NULL,
    target_zone_id      VARCHAR(50) REFERENCES zones(id) ON DELETE SET NULL,
    target_plant_id     VARCHAR(50) REFERENCES plants(id) ON DELETE SET NULL,
    target_fruit_id     VARCHAR(50) REFERENCES fruits(id) ON DELETE SET NULL,
    status              mission_status_type NOT NULL DEFAULT 'PENDING',
    current_step        VARCHAR(50),
    progress_percent    INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
    retry_count         INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE missions IS '순찰/수확/복귀 등 상위 작업';
COMMENT ON COLUMN missions.current_step IS 'SEARCH, APPROACH, PICK 같은 세부 단계';

CREATE TABLE IF NOT EXISTS iot_devices (
    id                  VARCHAR(50) PRIMARY KEY,
    zone_id             VARCHAR(50) NOT NULL REFERENCES zones(id),
    device_type         device_type NOT NULL,
    display_name        VARCHAR(100) NOT NULL,
    control_mode        device_control_mode_type NOT NULL DEFAULT 'AUTO',
    current_state       device_state_type NOT NULL DEFAULT 'OFF',
    current_value       NUMERIC(10,2),
    value_unit          VARCHAR(20),
    is_online           BOOLEAN NOT NULL DEFAULT FALSE,
    capabilities        JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_seen_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (zone_id, display_name)
);

COMMENT ON TABLE iot_devices IS '급수/커튼/환기팬/영양제 장치 메타데이터와 현재 상태';
COMMENT ON COLUMN iot_devices.control_mode IS 'AUTO, MANUAL, MANUAL_OVERRIDE, DISABLED';

CREATE TABLE IF NOT EXISTS crop_observations (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id                     VARCHAR(50) NOT NULL REFERENCES zones(id),
    plant_id                    VARCHAR(50) NOT NULL REFERENCES plants(id),
    fruit_id                    VARCHAR(50) REFERENCES fruits(id) ON DELETE SET NULL,
    mission_id                  UUID REFERENCES missions(id) ON DELETE SET NULL,
    class_name                  VARCHAR(50) NOT NULL,
    confidence                  NUMERIC(4,3) CHECK (confidence BETWEEN 0 AND 1),
    health_score                NUMERIC(4,3) CHECK (health_score BETWEEN 0 AND 1),
    growth_stage                NUMERIC(4,3) CHECK (growth_stage BETWEEN 0 AND 1),
    needs_water                 BOOLEAN NOT NULL DEFAULT FALSE,
    ready_to_harvest            BOOLEAN NOT NULL DEFAULT FALSE,
    observation_pose            JSONB NOT NULL DEFAULT '{}'::jsonb,
    image_path                  VARCHAR(255),
    observed_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE crop_observations IS '카메라/인지 노드 관측 이력';

CREATE TABLE IF NOT EXISTS environment_samples (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id             VARCHAR(50) NOT NULL REFERENCES zones(id),
    temperature         NUMERIC(6,2),
    humidity            NUMERIC(6,2) CHECK (humidity BETWEEN 0 AND 100),
    soil_moisture       NUMERIC(6,2) CHECK (soil_moisture BETWEEN 0 AND 100),
    light_level         NUMERIC(10,2),
    co2_level           NUMERIC(10,2),
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE environment_samples IS '구역별 환경 센서 시계열';

CREATE TABLE IF NOT EXISTS actuation_recommendations (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id                         VARCHAR(50) NOT NULL REFERENCES zones(id),
    plant_id                        VARCHAR(50) REFERENCES plants(id) ON DELETE SET NULL,
    device_id                       VARCHAR(50) REFERENCES iot_devices(id) ON DELETE SET NULL,
    source_observation_id           UUID REFERENCES crop_observations(id) ON DELETE SET NULL,
    source_environment_sample_id    UUID REFERENCES environment_samples(id) ON DELETE SET NULL,
    recommendation_type             recommendation_type NOT NULL,
    reason_code                     VARCHAR(50) NOT NULL,
    reason_text                     TEXT NOT NULL,
    suggested_value                 NUMERIC(10,2),
    value_unit                      VARCHAR(20),
    priority                        recommendation_priority_type NOT NULL DEFAULT 'MEDIUM',
    approval_required               BOOLEAN NOT NULL DEFAULT FALSE,
    status                          recommendation_status_type NOT NULL DEFAULT 'PENDING',
    reviewed_by                     VARCHAR(100),
    reviewed_at                     TIMESTAMPTZ,
    context_payload                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE actuation_recommendations IS '규칙 엔진이 만든 장치 제어 추천';
COMMENT ON COLUMN actuation_recommendations.approval_required IS '사용자 승인 필요 여부';

CREATE TABLE IF NOT EXISTS actuation_commands (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id   UUID REFERENCES actuation_recommendations(id) ON DELETE SET NULL,
    device_id           VARCHAR(50) NOT NULL REFERENCES iot_devices(id),
    zone_id             VARCHAR(50) NOT NULL REFERENCES zones(id),
    mission_id          UUID REFERENCES missions(id) ON DELETE SET NULL,
    requested_by        VARCHAR(100) NOT NULL,
    request_source      request_source_type NOT NULL,
    command_type        actuation_command_type NOT NULL,
    target_value        NUMERIC(10,2),
    value_unit          VARCHAR(20),
    command_payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    command_status      actuation_command_status_type NOT NULL DEFAULT 'REQUESTED',
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at             TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ
);

COMMENT ON TABLE actuation_commands IS '실제로 발행된 장치 제어 명령';
COMMENT ON COLUMN actuation_commands.request_source IS 'AUTO_RULE, USER_BUTTON, MISSION_FLOW 등';

CREATE TABLE IF NOT EXISTS actuation_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    command_id          UUID NOT NULL REFERENCES actuation_commands(id) ON DELETE CASCADE,
    device_id           VARCHAR(50) NOT NULL REFERENCES iot_devices(id),
    result              actuation_result_type NOT NULL,
    result_message      TEXT,
    state_after         device_state_type,
    actual_value        NUMERIC(10,2),
    value_unit          VARCHAR(20),
    result_payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at          TIMESTAMPTZ NOT NULL,
    finished_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

COMMENT ON TABLE actuation_logs IS '장치 실행 성공/실패 결과';

CREATE TABLE IF NOT EXISTS alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id            UUID REFERENCES robots(id) ON DELETE SET NULL,
    zone_id             VARCHAR(50) REFERENCES zones(id) ON DELETE SET NULL,
    plant_id            VARCHAR(50) REFERENCES plants(id) ON DELETE SET NULL,
    observation_id      UUID REFERENCES crop_observations(id) ON DELETE SET NULL,
    alert_type          alert_type NOT NULL,
    severity            alert_severity_type NOT NULL DEFAULT 'WARNING',
    message             TEXT NOT NULL,
    image_path          VARCHAR(255),
    acknowledged_by     VARCHAR(100),
    acknowledged_at     TIMESTAMPTZ,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE alerts IS '병해/센서/장치/로봇 오류 알림';
COMMENT ON COLUMN alerts.severity IS 'INFO, WARNING, CRITICAL';

CREATE TABLE IF NOT EXISTS harvest_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fruit_id            VARCHAR(50) REFERENCES fruits(id) ON DELETE SET NULL,
    plant_id            VARCHAR(50) NOT NULL REFERENCES plants(id),
    robot_id            UUID REFERENCES robots(id) ON DELETE SET NULL,
    mission_id          UUID REFERENCES missions(id) ON DELETE SET NULL,
    success             BOOLEAN NOT NULL,
    fail_reason         TEXT,
    basket_count        INTEGER NOT NULL DEFAULT 0 CHECK (basket_count >= 0),
    harvested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE harvest_events IS '수확 성공/실패 결과';
COMMENT ON COLUMN harvest_events.basket_count IS '이 이벤트 직후 바구니 누적 수량';

CREATE TABLE IF NOT EXISTS media_assets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    observation_id      UUID REFERENCES crop_observations(id) ON DELETE SET NULL,
    alert_id            UUID REFERENCES alerts(id) ON DELETE SET NULL,
    file_path           VARCHAR(255) NOT NULL UNIQUE,
    media_type          VARCHAR(50) NOT NULL DEFAULT 'image/jpeg',
    captured_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (observation_id IS NOT NULL OR alert_id IS NOT NULL)
);

COMMENT ON TABLE media_assets IS '관측/알림에 연결되는 이미지 파일 정보';

CREATE TRIGGER trg_zones_updated_at
BEFORE UPDATE ON zones
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_plants_updated_at
BEFORE UPDATE ON plants
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_fruits_updated_at
BEFORE UPDATE ON fruits
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_robots_updated_at
BEFORE UPDATE ON robots
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_missions_updated_at
BEFORE UPDATE ON missions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_iot_devices_updated_at
BEFORE UPDATE ON iot_devices
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_plants_zone_id
    ON plants (zone_id);

CREATE INDEX IF NOT EXISTS idx_fruits_plant_id
    ON fruits (plant_id);

CREATE INDEX IF NOT EXISTS idx_robots_current_zone_id
    ON robots (current_zone_id);

CREATE INDEX IF NOT EXISTS idx_missions_robot_status
    ON missions (robot_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_missions_target_zone_status
    ON missions (target_zone_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_crop_observations_plant_time
    ON crop_observations (plant_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_crop_observations_fruit_time
    ON crop_observations (fruit_id, observed_at DESC)
    WHERE fruit_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_environment_samples_zone_time
    ON environment_samples (zone_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_iot_devices_zone_type
    ON iot_devices (zone_id, device_type);

CREATE INDEX IF NOT EXISTS idx_actuation_recommendations_zone_status
    ON actuation_recommendations (zone_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_actuation_recommendations_device_status
    ON actuation_recommendations (device_id, status, priority);

CREATE INDEX IF NOT EXISTS idx_actuation_commands_device_time
    ON actuation_commands (device_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_actuation_commands_zone_status
    ON actuation_commands (zone_id, command_status, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_actuation_logs_command_time
    ON actuation_logs (command_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_detected_at
    ON alerts (detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_unacked_severity
    ON alerts (severity, detected_at DESC)
    WHERE acknowledged_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_alerts_zone_detected_at
    ON alerts (zone_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_harvest_events_time
    ON harvest_events (harvested_at DESC);

CREATE INDEX IF NOT EXISTS idx_harvest_events_fruit_time
    ON harvest_events (fruit_id, harvested_at DESC)
    WHERE fruit_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_media_assets_observation
    ON media_assets (observation_id)
    WHERE observation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_media_assets_alert
    ON media_assets (alert_id)
    WHERE alert_id IS NOT NULL;

COMMIT;
