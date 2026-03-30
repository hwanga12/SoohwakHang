--
-- PostgreSQL database dump
--

\restrict LCnUHV3T2zyBRwbpNsDkS1jGfLBk7YVyQKJB6r4KCgDTHJeo8dw9vm476SUzAFh

-- Dumped from database version 16.13 (Debian 16.13-1.pgdg13+1)
-- Dumped by pg_dump version 16.13 (Debian 16.13-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.robots DROP CONSTRAINT IF EXISTS robots_current_zone_id_fkey;
ALTER TABLE IF EXISTS ONLY public.plants DROP CONSTRAINT IF EXISTS plants_zone_id_fkey;
ALTER TABLE IF EXISTS ONLY public.missions DROP CONSTRAINT IF EXISTS missions_target_zone_id_fkey;
ALTER TABLE IF EXISTS ONLY public.missions DROP CONSTRAINT IF EXISTS missions_target_plant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.missions DROP CONSTRAINT IF EXISTS missions_target_fruit_id_fkey;
ALTER TABLE IF EXISTS ONLY public.missions DROP CONSTRAINT IF EXISTS missions_robot_id_fkey;
ALTER TABLE IF EXISTS ONLY public.iot_devices DROP CONSTRAINT IF EXISTS iot_devices_zone_id_fkey;
ALTER TABLE IF EXISTS ONLY public.harvest_events DROP CONSTRAINT IF EXISTS harvest_events_robot_id_fkey;
ALTER TABLE IF EXISTS ONLY public.harvest_events DROP CONSTRAINT IF EXISTS harvest_events_plant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.harvest_events DROP CONSTRAINT IF EXISTS harvest_events_mission_id_fkey;
ALTER TABLE IF EXISTS ONLY public.harvest_events DROP CONSTRAINT IF EXISTS harvest_events_fruit_id_fkey;
ALTER TABLE IF EXISTS ONLY public.fruits DROP CONSTRAINT IF EXISTS fruits_plant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.environment_samples DROP CONSTRAINT IF EXISTS environment_samples_zone_id_fkey;
ALTER TABLE IF EXISTS ONLY public.crop_observations DROP CONSTRAINT IF EXISTS crop_observations_robot_id_fkey;
ALTER TABLE IF EXISTS ONLY public.crop_observations DROP CONSTRAINT IF EXISTS crop_observations_plant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.crop_observations DROP CONSTRAINT IF EXISTS crop_observations_mission_id_fkey;
ALTER TABLE IF EXISTS ONLY public.crop_observations DROP CONSTRAINT IF EXISTS crop_observations_fruit_id_fkey;
ALTER TABLE IF EXISTS ONLY public.alerts DROP CONSTRAINT IF EXISTS alerts_zone_id_fkey;
ALTER TABLE IF EXISTS ONLY public.alerts DROP CONSTRAINT IF EXISTS alerts_robot_id_fkey;
ALTER TABLE IF EXISTS ONLY public.alerts DROP CONSTRAINT IF EXISTS alerts_plant_id_fkey;
ALTER TABLE IF EXISTS ONLY public.alerts DROP CONSTRAINT IF EXISTS alerts_observation_id_fkey;
ALTER TABLE IF EXISTS ONLY public.actuation_logs DROP CONSTRAINT IF EXISTS actuation_logs_device_id_fkey;
ALTER TABLE IF EXISTS ONLY public.actuation_logs DROP CONSTRAINT IF EXISTS actuation_logs_command_id_fkey;
ALTER TABLE IF EXISTS ONLY public.actuation_commands DROP CONSTRAINT IF EXISTS actuation_commands_zone_id_fkey;
ALTER TABLE IF EXISTS ONLY public.actuation_commands DROP CONSTRAINT IF EXISTS actuation_commands_observation_id_fkey;
ALTER TABLE IF EXISTS ONLY public.actuation_commands DROP CONSTRAINT IF EXISTS actuation_commands_mission_id_fkey;
ALTER TABLE IF EXISTS ONLY public.actuation_commands DROP CONSTRAINT IF EXISTS actuation_commands_device_id_fkey;
DROP INDEX IF EXISTS public.ix_zones_id;
DROP INDEX IF EXISTS public.ix_plants_id;
DROP INDEX IF EXISTS public.ix_iot_devices_id;
DROP INDEX IF EXISTS public.ix_fruits_id;
ALTER TABLE IF EXISTS ONLY public.zones DROP CONSTRAINT IF EXISTS zones_pkey;
ALTER TABLE IF EXISTS ONLY public.robots DROP CONSTRAINT IF EXISTS robots_pkey;
ALTER TABLE IF EXISTS ONLY public.robots DROP CONSTRAINT IF EXISTS robots_name_key;
ALTER TABLE IF EXISTS ONLY public.plants DROP CONSTRAINT IF EXISTS plants_pkey;
ALTER TABLE IF EXISTS ONLY public.missions DROP CONSTRAINT IF EXISTS missions_pkey;
ALTER TABLE IF EXISTS ONLY public.iot_devices DROP CONSTRAINT IF EXISTS iot_devices_pkey;
ALTER TABLE IF EXISTS ONLY public.harvest_events DROP CONSTRAINT IF EXISTS harvest_events_pkey;
ALTER TABLE IF EXISTS ONLY public.fruits DROP CONSTRAINT IF EXISTS fruits_pkey;
ALTER TABLE IF EXISTS ONLY public.environment_samples DROP CONSTRAINT IF EXISTS environment_samples_pkey;
ALTER TABLE IF EXISTS ONLY public.crop_observations DROP CONSTRAINT IF EXISTS crop_observations_pkey;
ALTER TABLE IF EXISTS ONLY public.alerts DROP CONSTRAINT IF EXISTS alerts_pkey;
ALTER TABLE IF EXISTS ONLY public.actuation_logs DROP CONSTRAINT IF EXISTS actuation_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.actuation_commands DROP CONSTRAINT IF EXISTS actuation_commands_pkey;
DROP TABLE IF EXISTS public.zones;
DROP TABLE IF EXISTS public.robots;
DROP TABLE IF EXISTS public.plants;
DROP TABLE IF EXISTS public.missions;
DROP TABLE IF EXISTS public.iot_devices;
DROP TABLE IF EXISTS public.harvest_events;
DROP TABLE IF EXISTS public.fruits;
DROP TABLE IF EXISTS public.environment_samples;
DROP TABLE IF EXISTS public.crop_observations;
DROP TABLE IF EXISTS public.alerts;
DROP TABLE IF EXISTS public.actuation_logs;
DROP TABLE IF EXISTS public.actuation_commands;
SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: actuation_commands; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.actuation_commands (
    id uuid NOT NULL,
    device_id character varying(50) NOT NULL,
    zone_id character varying(50) NOT NULL,
    mission_id uuid,
    observation_id uuid,
    command_type character varying(30) NOT NULL,
    command_status character varying(30) NOT NULL,
    target_value double precision,
    value_unit character varying(20),
    requested_by character varying(100),
    request_source character varying(50),
    requested_at timestamp without time zone NOT NULL
);


ALTER TABLE public.actuation_commands OWNER TO agribot;

--
-- Name: actuation_logs; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.actuation_logs (
    id uuid NOT NULL,
    command_id uuid NOT NULL,
    device_id character varying(50) NOT NULL,
    result character varying(20) NOT NULL,
    result_message text,
    state_after character varying(30),
    actual_value double precision,
    value_unit character varying(20),
    started_at timestamp without time zone NOT NULL,
    finished_at timestamp without time zone
);


ALTER TABLE public.actuation_logs OWNER TO agribot;

--
-- Name: alerts; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.alerts (
    id uuid NOT NULL,
    robot_id uuid,
    zone_id character varying(50),
    plant_id character varying(50),
    observation_id uuid,
    alert_type character varying(30) NOT NULL,
    severity character varying(20) NOT NULL,
    message text NOT NULL,
    image_url character varying(255),
    acknowledged_at timestamp without time zone,
    acknowledged_by character varying(100),
    detected_at timestamp without time zone NOT NULL
);


ALTER TABLE public.alerts OWNER TO agribot;

--
-- Name: crop_observations; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.crop_observations (
    id uuid NOT NULL,
    robot_id uuid,
    mission_id uuid,
    plant_id character varying(50) NOT NULL,
    fruit_id character varying(50),
    finding_label character varying(100) NOT NULL,
    confidence double precision NOT NULL,
    recommended_action character varying(255),
    evidence text,
    image_url character varying(255),
    observed_at timestamp without time zone NOT NULL
);


ALTER TABLE public.crop_observations OWNER TO agribot;

--
-- Name: environment_samples; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.environment_samples (
    id uuid NOT NULL,
    zone_id character varying(50) NOT NULL,
    temperature double precision,
    humidity double precision,
    soil_moisture double precision,
    recorded_at timestamp without time zone NOT NULL
);


ALTER TABLE public.environment_samples OWNER TO agribot;

--
-- Name: fruits; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.fruits (
    id character varying(50) NOT NULL,
    plant_id character varying(50) NOT NULL,
    "position" jsonb NOT NULL,
    ripeness_stage character varying(30) NOT NULL,
    ready_to_harvest boolean NOT NULL,
    current_status character varying(30) NOT NULL,
    last_observed_at timestamp without time zone
);


ALTER TABLE public.fruits OWNER TO agribot;

--
-- Name: harvest_events; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.harvest_events (
    id uuid NOT NULL,
    plant_id character varying(50) NOT NULL,
    fruit_id character varying(50),
    robot_id uuid NOT NULL,
    mission_id uuid,
    success boolean NOT NULL,
    fail_reason text,
    basket_count integer,
    harvested_at timestamp without time zone NOT NULL
);


ALTER TABLE public.harvest_events OWNER TO agribot;

--
-- Name: iot_devices; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.iot_devices (
    id character varying(50) NOT NULL,
    zone_id character varying(50) NOT NULL,
    device_type character varying(30) NOT NULL,
    display_name character varying(100) NOT NULL,
    control_mode character varying(30) NOT NULL,
    current_state character varying(30) NOT NULL,
    current_value double precision,
    value_unit character varying(20),
    is_online boolean NOT NULL,
    last_seen_at timestamp without time zone
);


ALTER TABLE public.iot_devices OWNER TO agribot;

--
-- Name: missions; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.missions (
    id uuid NOT NULL,
    robot_id uuid NOT NULL,
    mission_type character varying(50) NOT NULL,
    target_zone_id character varying(50),
    target_plant_id character varying(50),
    target_fruit_id character varying(50),
    status character varying(50) NOT NULL,
    progress_percent integer,
    started_at timestamp without time zone,
    completed_at timestamp without time zone
);


ALTER TABLE public.missions OWNER TO agribot;

--
-- Name: plants; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.plants (
    id character varying(50) NOT NULL,
    zone_id character varying(50) NOT NULL,
    crop_name character varying(50) NOT NULL,
    "position" jsonb NOT NULL,
    needs_water boolean NOT NULL,
    ready_to_harvest boolean NOT NULL,
    needs_nutrition boolean NOT NULL,
    last_observed_at timestamp without time zone
);


ALTER TABLE public.plants OWNER TO agribot;

--
-- Name: robots; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.robots (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    status character varying(50) NOT NULL,
    battery_level double precision,
    current_zone_id character varying(50),
    current_pose jsonb,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.robots OWNER TO agribot;

--
-- Name: zones; Type: TABLE; Schema: public; Owner: agribot
--

CREATE TABLE public.zones (
    id character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    bounds jsonb NOT NULL,
    description character varying(255)
);


ALTER TABLE public.zones OWNER TO agribot;

--
-- Data for Name: actuation_commands; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.actuation_commands VALUES ('75305446-fb23-5d12-a4da-74583797a13a', 'sprinkler_1', 'farm_01', '22222222-2222-2222-2222-222222222222', 'aca92f6a-b264-52fd-887a-7e74dbe60239', 'SPRAY_PESTICIDE', 'COMPLETED', 3, 'sec', 'backend:demo-seed', 'AI_CONFIRMATION', '2026-03-30 00:12:47');
INSERT INTO public.actuation_commands VALUES ('17d08119-26d7-5ae6-9f52-5656ab8d620c', 'sprinkler_2', 'farm_01', '22222222-2222-2222-2222-222222222222', '661ef036-cb18-5bbb-836b-141beb739e6d', 'SPRAY_PESTICIDE', 'COMPLETED', 3.5, 'sec', 'backend:demo-seed', 'AI_CONFIRMATION', '2026-03-30 00:21:47');
INSERT INTO public.actuation_commands VALUES ('3f1a60c0-b3ca-507c-a796-5ef29cb77b8d', 'sprinkler_1', 'farm_01', '22222222-2222-2222-2222-222222222222', '3f36d4f0-9d50-57f4-8d79-6e6c14980e30', 'SPRAY_CALCIUM_SOLUTION', 'COMPLETED', 2.5, 'sec', 'backend:demo-seed', 'AI_CONFIRMATION', '2026-03-30 00:28:47');
INSERT INTO public.actuation_commands VALUES ('15b178b4-83b5-45d3-8635-567c740d4f96', 'sprinkler_1', 'farm_01', NULL, 'ee3ce987-585e-4172-ba14-a3f083328b1f', 'SPRAY_PESTICIDE', 'DISPATCHED', 3, 'sec', 'frontend-demo', 'AI_CONFIRMATION', '2026-03-30 00:58:18.04462');


--
-- Data for Name: actuation_logs; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.actuation_logs VALUES ('d679ff1d-160a-5590-8df7-59460cef060f', '75305446-fb23-5d12-a4da-74583797a13a', 'sprinkler_1', 'SUCCESS', '약제 살포 완료', 'ON', 3, 'sec', '2026-03-30 00:12:47', '2026-03-30 00:12:57');
INSERT INTO public.actuation_logs VALUES ('4ea3753f-6440-5d35-bed9-b601ab262842', '17d08119-26d7-5ae6-9f52-5656ab8d620c', 'sprinkler_2', 'SUCCESS', '약제 살포 완료', 'ON', 3.5, 'sec', '2026-03-30 00:21:47', '2026-03-30 00:21:57');
INSERT INTO public.actuation_logs VALUES ('74cb8fb2-e649-5eb6-8560-6b792b308e0b', '3f1a60c0-b3ca-507c-a796-5ef29cb77b8d', 'sprinkler_1', 'SUCCESS', '칼슘액비 살포 완료', 'ON', 2.5, 'sec', '2026-03-30 00:28:47', '2026-03-30 00:28:57');
INSERT INTO public.actuation_logs VALUES ('b97522b0-9d91-4f40-8ad3-d199e1695166', '15b178b4-83b5-45d3-8635-567c740d4f96', 'sprinkler_1', 'SUCCESS', 'Published IoTCommand 67b79024-6617-4bf2-b76f-ae7f10715402 to /iot/commands/auto for sprinkler:sprinkler_1 (subscribers=1).', 'ON', 3, 'sec', '2026-03-30 00:58:18.04462', '2026-03-30 00:58:18.04462');


--
-- Data for Name: alerts; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.alerts VALUES ('de52bf65-97fa-5362-a038-51a2f07e963c', '11111111-1111-1111-1111-111111111111', 'farm_01', 'farm01_plant_06', 'aca92f6a-b264-52fd-887a-7e74dbe60239', 'DISEASE', 'CRITICAL', '토마토 식물 06 에서 tomato_powdery_mildew 이 감지되었습니다.', '/mock-images/disease-closeup.png', NULL, NULL, '2026-03-30 00:11:17');
INSERT INTO public.alerts VALUES ('7071e06f-1316-57fc-9025-8e2f8bba3a70', '11111111-1111-1111-1111-111111111111', 'farm_01', 'farm01_plant_15', '661ef036-cb18-5bbb-836b-141beb739e6d', 'DISEASE', 'CRITICAL', '토마토 식물 15 에서 tomato_gray_mold 이 감지되었습니다.', '/mock-images/disease-closeup.png', NULL, NULL, '2026-03-30 00:20:17');
INSERT INTO public.alerts VALUES ('6381b8a1-089c-5528-98f4-64734d8753d9', '11111111-1111-1111-1111-111111111111', 'farm_01', 'farm01_plant_22', '3f36d4f0-9d50-57f4-8d79-6e6c14980e30', 'DISEASE', 'WARNING', '토마토 식물 22 에서 tomato_blossom_end_rot 이 감지되었습니다.', '/mock-images/disease-closeup.png', NULL, NULL, '2026-03-30 00:27:17');
INSERT INTO public.alerts VALUES ('4fd23cec-3d8d-4f98-ad97-55ebb07ad8b7', '11111111-1111-1111-1111-111111111111', 'farm_01', 'farm01_plant_18', 'ee3ce987-585e-4172-ba14-a3f083328b1f', 'DISEASE', 'CRITICAL', 'farm01_plant_18 에서 tomato_powdery_mildew_disease 감지', '/home/ssafy/Desktop/pjt/S14P21A602/artifacts/runtime/backend/20260330/67b79024-6617-4bf2-b76f-ae7f10715402.jpg', NULL, NULL, '2026-03-30 00:58:18.04462');


--
-- Data for Name: crop_observations; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.crop_observations VALUES ('e68c5c6c-17e4-5f08-8547-6ce777f33615', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_01', 'farm01_plant_01_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:05:47');
INSERT INTO public.crop_observations VALUES ('2c46e1c3-eb10-513e-ae08-05008beb0910', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_02', 'farm01_plant_02_tomato_01', 'ripe_tomato', 0.94, '수확 요청 가능', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:06:47');
INSERT INTO public.crop_observations VALUES ('b27d2cec-6fd7-5b86-8e67-9c1999541a33', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_03', 'farm01_plant_03_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:07:47');
INSERT INTO public.crop_observations VALUES ('6bd5e2c8-be7f-5b2c-b3cc-888abaf437ac', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_04', 'farm01_plant_04_tomato_01', 'ripe_tomato', 0.94, '수확 요청 가능', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:08:47');
INSERT INTO public.crop_observations VALUES ('edd72473-fc09-5571-b779-51faf2e850bc', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_05', 'farm01_plant_05_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:09:47');
INSERT INTO public.crop_observations VALUES ('aca92f6a-b264-52fd-887a-7e74dbe60239', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_06', 'farm01_plant_06_tomato_01', 'tomato_powdery_mildew', 0.97, '약제 살포', '잎 표면 흰가루 패턴과 가장자리 변색이 확인되었습니다.', '/mock-images/disease-closeup.png', '2026-03-30 00:10:47');
INSERT INTO public.crop_observations VALUES ('432c78f2-0c44-57c5-a43a-5e3220c1b276', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_07', 'farm01_plant_07_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:11:47');
INSERT INTO public.crop_observations VALUES ('b0cbdfca-5305-58ed-8676-330406d109a5', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_08', 'farm01_plant_08_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:12:47');
INSERT INTO public.crop_observations VALUES ('2ff8de68-7553-5577-b7c8-dde8dd432061', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_09', 'farm01_plant_09_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:13:47');
INSERT INTO public.crop_observations VALUES ('72a37b9e-da9a-5ddf-8101-ab4d2e830b65', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_10', 'farm01_plant_10_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:14:47');
INSERT INTO public.crop_observations VALUES ('da045e2b-6e17-5d82-ad19-e836b83ed50c', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_11', 'farm01_plant_11_tomato_01', 'ripe_tomato', 0.94, '수확 요청 가능', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:15:47');
INSERT INTO public.crop_observations VALUES ('55f35eea-e4fb-5212-b3c5-9b2267b4c809', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_12', 'farm01_plant_12_tomato_01', 'ripe_tomato', 0.94, '수확 요청 가능', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:16:47');
INSERT INTO public.crop_observations VALUES ('670f273e-e7e8-5840-8316-05ca8e6f6ff3', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_13', 'farm01_plant_13_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:17:47');
INSERT INTO public.crop_observations VALUES ('37a6a2bc-8777-538d-9e68-4bad0c738052', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_14', 'farm01_plant_14_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:18:47');
INSERT INTO public.crop_observations VALUES ('661ef036-cb18-5bbb-836b-141beb739e6d', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_15', 'farm01_plant_15_tomato_01', 'tomato_gray_mold', 0.97, '약제 살포', '과실 주변 회색 곰팡이성 패턴이 확인되었습니다.', '/mock-images/disease-closeup.png', '2026-03-30 00:19:47');
INSERT INTO public.crop_observations VALUES ('e23c27c7-a064-50e3-88c8-7b653bbd8c08', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_16', 'farm01_plant_16_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:20:47');
INSERT INTO public.crop_observations VALUES ('d58f1c7e-f120-5dfc-86da-ecabc75a9a56', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_17', 'farm01_plant_17_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:21:47');
INSERT INTO public.crop_observations VALUES ('88c18c57-2895-5c8f-87ce-02372425cb59', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_18', 'farm01_plant_18_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:22:47');
INSERT INTO public.crop_observations VALUES ('398c423a-3d17-5f04-848e-c7a967316f27', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_19', 'farm01_plant_19_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:23:47');
INSERT INTO public.crop_observations VALUES ('49461e57-9cad-59ba-9b8c-18c09ea3f70a', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_20', 'farm01_plant_20_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:24:47');
INSERT INTO public.crop_observations VALUES ('a47ef075-1997-5cf3-bea4-1dff7d1e7e3d', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_21', 'farm01_plant_21_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:25:47');
INSERT INTO public.crop_observations VALUES ('3f36d4f0-9d50-57f4-8d79-6e6c14980e30', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_22', 'farm01_plant_22_tomato_01', 'tomato_blossom_end_rot', 0.97, '칼슘액비 살포', '과실 하단 흑변과 칼슘 결핍 패턴이 확인되었습니다.', '/mock-images/disease-closeup.png', '2026-03-30 00:26:47');
INSERT INTO public.crop_observations VALUES ('01095cac-b51d-5bb0-b56d-c62c201ac3b5', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_23', 'farm01_plant_23_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:27:47');
INSERT INTO public.crop_observations VALUES ('155cde98-0835-5c65-bd51-71ea949267cd', '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'farm01_plant_24', 'farm01_plant_24_tomato_01', 'healthy_leaf', 0.94, '추가 관찰 유지', '정상 생육 패턴이 확인되었습니다.', '/mock-images/healthy-default.jpg', '2026-03-30 00:28:47');
INSERT INTO public.crop_observations VALUES ('ee3ce987-585e-4172-ba14-a3f083328b1f', '11111111-1111-1111-1111-111111111111', NULL, 'farm01_plant_18', 'farm01_plant_18_tomato_01', 'tomato_powdery_mildew_disease', 0.5186818838119507, '약재 살포', 'preliminary=tomato_powdery_mildew_disease, final=tomato_powdery_mildew_disease, confidence=0.52, treatment_reason=Nearest sprinkler selected for the actionable disease.', '/home/ssafy/Desktop/pjt/S14P21A602/artifacts/runtime/backend/20260330/67b79024-6617-4bf2-b76f-ae7f10715402.jpg', '2026-03-30 00:58:18.04462');


--
-- Data for Name: environment_samples; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.environment_samples VALUES ('a51164e5-e7ab-5951-b1c0-6ec044d1daaa', 'farm_01', 24.2, 57.5, 28, '2026-03-30 00:05:47');
INSERT INTO public.environment_samples VALUES ('6a6facd6-5196-53b9-91b6-18de43e89469', 'farm_01', 24.599999999999998, 58.7, 28.8, '2026-03-30 00:10:47');
INSERT INTO public.environment_samples VALUES ('1bf1137d-18b7-5ba1-8591-9732008d6edd', 'farm_01', 25, 59.9, 29.6, '2026-03-30 00:15:47');
INSERT INTO public.environment_samples VALUES ('4f78d5c3-a532-5c7b-ba96-e8d782284e57', 'farm_01', 25.4, 61.1, 30.4, '2026-03-30 00:20:47');
INSERT INTO public.environment_samples VALUES ('e38eed1c-7591-5285-98b9-dff24bdd0cfe', 'farm_01', 25.8, 62.3, 31.2, '2026-03-30 00:25:47');
INSERT INTO public.environment_samples VALUES ('6cdc680b-36b3-55e8-bc5c-8cbfba05809e', 'farm_01', 26.2, 63.5, 32, '2026-03-30 00:30:47');


--
-- Data for Name: fruits; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.fruits VALUES ('farm01_plant_01_tomato_01', 'farm01_plant_01', '{"x": -6.0, "y": -6.0, "z": 1.05}', 'RIPE', false, 'HARVESTED', '2026-03-30 00:05:47');
INSERT INTO public.fruits VALUES ('farm01_plant_02_tomato_01', 'farm01_plant_02', '{"x": -2.0, "y": -6.0, "z": 1.05}', 'RIPE', true, 'VISIBLE', '2026-03-30 00:06:47');
INSERT INTO public.fruits VALUES ('farm01_plant_03_tomato_01', 'farm01_plant_03', '{"x": 2.0, "y": -6.0, "z": 1.05}', 'RIPE', false, 'HARVESTED', '2026-03-30 00:07:47');
INSERT INTO public.fruits VALUES ('farm01_plant_04_tomato_01', 'farm01_plant_04', '{"x": 6.0, "y": -6.0, "z": 1.05}', 'RIPE', true, 'VISIBLE', '2026-03-30 00:08:47');
INSERT INTO public.fruits VALUES ('farm01_plant_05_tomato_01', 'farm01_plant_05', '{"x": -6.0, "y": -4.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:09:47');
INSERT INTO public.fruits VALUES ('farm01_plant_06_tomato_01', 'farm01_plant_06', '{"x": -2.0, "y": -4.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:10:47');
INSERT INTO public.fruits VALUES ('farm01_plant_07_tomato_01', 'farm01_plant_07', '{"x": 2.0, "y": -4.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:11:47');
INSERT INTO public.fruits VALUES ('farm01_plant_08_tomato_01', 'farm01_plant_08', '{"x": 6.0, "y": -4.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:12:47');
INSERT INTO public.fruits VALUES ('farm01_plant_09_tomato_01', 'farm01_plant_09', '{"x": -6.0, "y": -2.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:13:47');
INSERT INTO public.fruits VALUES ('farm01_plant_10_tomato_01', 'farm01_plant_10', '{"x": -2.0, "y": -2.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:14:47');
INSERT INTO public.fruits VALUES ('farm01_plant_11_tomato_01', 'farm01_plant_11', '{"x": 2.0, "y": -2.0, "z": 1.05}', 'RIPE', true, 'VISIBLE', '2026-03-30 00:15:47');
INSERT INTO public.fruits VALUES ('farm01_plant_12_tomato_01', 'farm01_plant_12', '{"x": 6.0, "y": -2.0, "z": 1.05}', 'RIPE', true, 'VISIBLE', '2026-03-30 00:16:47');
INSERT INTO public.fruits VALUES ('farm01_plant_13_tomato_01', 'farm01_plant_13', '{"x": -6.0, "y": 2.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:17:47');
INSERT INTO public.fruits VALUES ('farm01_plant_14_tomato_01', 'farm01_plant_14', '{"x": -2.0, "y": 2.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:18:47');
INSERT INTO public.fruits VALUES ('farm01_plant_15_tomato_01', 'farm01_plant_15', '{"x": 2.0, "y": 2.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:19:47');
INSERT INTO public.fruits VALUES ('farm01_plant_16_tomato_01', 'farm01_plant_16', '{"x": 6.0, "y": 2.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:20:47');
INSERT INTO public.fruits VALUES ('farm01_plant_17_tomato_01', 'farm01_plant_17', '{"x": -6.0, "y": 4.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:21:47');
INSERT INTO public.fruits VALUES ('farm01_plant_19_tomato_01', 'farm01_plant_19', '{"x": 2.0, "y": 4.0, "z": 1.05}', 'RIPE', false, 'LOST', '2026-03-30 00:23:47');
INSERT INTO public.fruits VALUES ('farm01_plant_20_tomato_01', 'farm01_plant_20', '{"x": 6.0, "y": 4.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:24:47');
INSERT INTO public.fruits VALUES ('farm01_plant_21_tomato_01', 'farm01_plant_21', '{"x": -6.0, "y": 6.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:25:47');
INSERT INTO public.fruits VALUES ('farm01_plant_22_tomato_01', 'farm01_plant_22', '{"x": -2.0, "y": 6.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:26:47');
INSERT INTO public.fruits VALUES ('farm01_plant_23_tomato_01', 'farm01_plant_23', '{"x": 2.0, "y": 6.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:27:47');
INSERT INTO public.fruits VALUES ('farm01_plant_24_tomato_01', 'farm01_plant_24', '{"x": 6.0, "y": 6.0, "z": 1.05}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:28:47');
INSERT INTO public.fruits VALUES ('farm01_plant_18_tomato_01', 'farm01_plant_18', '{"x": 0.0, "y": 4.0, "z": 0.0}', 'TURNING', false, 'VISIBLE', '2026-03-30 00:58:18.04462');


--
-- Data for Name: harvest_events; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.harvest_events VALUES ('85076b30-6957-5841-9d19-953f3b01ce7e', 'farm01_plant_01', 'farm01_plant_01_tomato_01', '11111111-1111-1111-1111-111111111111', '80f68e88-6bc5-5c17-b98c-9fdc3fceb4ed', true, NULL, 1, '2026-03-30 00:09:47');
INSERT INTO public.harvest_events VALUES ('f9c8bb12-e3aa-5f9c-8004-b8e675bf8fc6', 'farm01_plant_03', 'farm01_plant_03_tomato_01', '11111111-1111-1111-1111-111111111111', '8996d722-a600-5820-97b4-97ff2837e050', true, NULL, 2, '2026-03-30 00:11:47');
INSERT INTO public.harvest_events VALUES ('87b167a0-2490-5976-b5a2-3b4e7dcaccf7', 'farm01_plant_19', 'farm01_plant_19_tomato_01', '11111111-1111-1111-1111-111111111111', 'c77264f1-fde4-5526-bf86-1491c8b387de', false, 'target_lost', 2, '2026-03-30 00:27:47');


--
-- Data for Name: iot_devices; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.iot_devices VALUES ('farm_01_curtain', 'farm_01', 'CURTAIN', 'Farm 01 Ceiling Curtain', 'AUTO', 'CLOSED', 0, 'percent', true, '2026-03-30 00:30:47');
INSERT INTO public.iot_devices VALUES ('farm_01_fan', 'farm_01', 'FAN', 'Farm 01 Ventilation Fan', 'AUTO', 'OFF', 0, 'level', true, '2026-03-30 00:30:47');
INSERT INTO public.iot_devices VALUES ('farm_01_nutrient', 'farm_01', 'NUTRIENT', 'Farm 01 Nutrient Dispenser', 'AUTO', 'OFF', 0, 'ml', true, '2026-03-30 00:30:47');
INSERT INTO public.iot_devices VALUES ('farm_01_watering', 'farm_01', 'WATER_PUMP', 'Farm 01 Watering Pump', 'AUTO', 'OFF', 0, 'ml', true, '2026-03-30 00:30:47');
INSERT INTO public.iot_devices VALUES ('sprinkler_0', 'farm_01', 'SPRINKLER', 'Farm 01 Sprinkler 0', 'AUTO', 'OFF', 0, 'sec', true, '2026-03-30 00:30:47');
INSERT INTO public.iot_devices VALUES ('sprinkler_1', 'farm_01', 'SPRINKLER', 'Farm 01 Sprinkler 1', 'AUTO', 'OFF', 0, 'sec', true, '2026-03-30 00:30:47');
INSERT INTO public.iot_devices VALUES ('sprinkler_2', 'farm_01', 'SPRINKLER', 'Farm 01 Sprinkler 2', 'AUTO', 'OFF', 0, 'sec', true, '2026-03-30 00:30:47');
INSERT INTO public.iot_devices VALUES ('sprinkler_3', 'farm_01', 'SPRINKLER', 'Farm 01 Sprinkler 3', 'AUTO', 'OFF', 0, 'sec', true, '2026-03-30 00:30:47');


--
-- Data for Name: missions; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.missions VALUES ('22222222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'PATROL', 'farm_01', NULL, NULL, 'RUNNING', 68, '2026-03-30 00:12:47', NULL);
INSERT INTO public.missions VALUES ('80f68e88-6bc5-5c17-b98c-9fdc3fceb4ed', '11111111-1111-1111-1111-111111111111', 'HARVEST', 'farm_01', 'farm01_plant_01', 'farm01_plant_01_tomato_01', 'COMPLETED', 100, '2026-03-30 00:07:47', '2026-03-30 00:09:47');
INSERT INTO public.missions VALUES ('8996d722-a600-5820-97b4-97ff2837e050', '11111111-1111-1111-1111-111111111111', 'HARVEST', 'farm_01', 'farm01_plant_03', 'farm01_plant_03_tomato_01', 'COMPLETED', 100, '2026-03-30 00:09:47', '2026-03-30 00:11:47');
INSERT INTO public.missions VALUES ('c77264f1-fde4-5526-bf86-1491c8b387de', '11111111-1111-1111-1111-111111111111', 'HARVEST', 'farm_01', 'farm01_plant_19', 'farm01_plant_19_tomato_01', 'FAILED', 72, '2026-03-30 00:25:47', '2026-03-30 00:27:47');


--
-- Data for Name: plants; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.plants VALUES ('farm01_plant_01', 'farm_01', 'tomato', '{"x": -6.0, "y": -6.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:05:47');
INSERT INTO public.plants VALUES ('farm01_plant_02', 'farm_01', 'tomato', '{"x": -2.0, "y": -6.0, "z": 0.75, "yaw": 0.0}', false, true, false, '2026-03-30 00:06:47');
INSERT INTO public.plants VALUES ('farm01_plant_03', 'farm_01', 'tomato', '{"x": 2.0, "y": -6.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:07:47');
INSERT INTO public.plants VALUES ('farm01_plant_04', 'farm_01', 'tomato', '{"x": 6.0, "y": -6.0, "z": 0.75, "yaw": 0.0}', false, true, false, '2026-03-30 00:08:47');
INSERT INTO public.plants VALUES ('farm01_plant_05', 'farm_01', 'tomato', '{"x": -6.0, "y": -4.0, "z": 0.75, "yaw": 0.0}', true, false, false, '2026-03-30 00:09:47');
INSERT INTO public.plants VALUES ('farm01_plant_06', 'farm_01', 'tomato', '{"x": -2.0, "y": -4.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:10:47');
INSERT INTO public.plants VALUES ('farm01_plant_07', 'farm_01', 'tomato', '{"x": 2.0, "y": -4.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:11:47');
INSERT INTO public.plants VALUES ('farm01_plant_08', 'farm_01', 'tomato', '{"x": 6.0, "y": -4.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:12:47');
INSERT INTO public.plants VALUES ('farm01_plant_09', 'farm_01', 'tomato', '{"x": -6.0, "y": -2.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:13:47');
INSERT INTO public.plants VALUES ('farm01_plant_10', 'farm_01', 'tomato', '{"x": -2.0, "y": -2.0, "z": 0.75, "yaw": 0.0}', true, false, false, '2026-03-30 00:14:47');
INSERT INTO public.plants VALUES ('farm01_plant_11', 'farm_01', 'tomato', '{"x": 2.0, "y": -2.0, "z": 0.75, "yaw": 0.0}', false, true, false, '2026-03-30 00:15:47');
INSERT INTO public.plants VALUES ('farm01_plant_12', 'farm_01', 'tomato', '{"x": 6.0, "y": -2.0, "z": 0.75, "yaw": 0.0}', false, true, false, '2026-03-30 00:16:47');
INSERT INTO public.plants VALUES ('farm01_plant_13', 'farm_01', 'tomato', '{"x": -6.0, "y": 2.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:17:47');
INSERT INTO public.plants VALUES ('farm01_plant_14', 'farm_01', 'tomato', '{"x": -2.0, "y": 2.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:18:47');
INSERT INTO public.plants VALUES ('farm01_plant_15', 'farm_01', 'tomato', '{"x": 2.0, "y": 2.0, "z": 0.75, "yaw": 0.0}', true, false, false, '2026-03-30 00:19:47');
INSERT INTO public.plants VALUES ('farm01_plant_16', 'farm_01', 'tomato', '{"x": 6.0, "y": 2.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:20:47');
INSERT INTO public.plants VALUES ('farm01_plant_17', 'farm_01', 'tomato', '{"x": -6.0, "y": 4.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:21:47');
INSERT INTO public.plants VALUES ('farm01_plant_19', 'farm_01', 'tomato', '{"x": 2.0, "y": 4.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:23:47');
INSERT INTO public.plants VALUES ('farm01_plant_20', 'farm_01', 'tomato', '{"x": 6.0, "y": 4.0, "z": 0.75, "yaw": 0.0}', true, false, false, '2026-03-30 00:24:47');
INSERT INTO public.plants VALUES ('farm01_plant_21', 'farm_01', 'tomato', '{"x": -6.0, "y": 6.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:25:47');
INSERT INTO public.plants VALUES ('farm01_plant_22', 'farm_01', 'tomato', '{"x": -2.0, "y": 6.0, "z": 0.75, "yaw": 0.0}', false, false, true, '2026-03-30 00:26:47');
INSERT INTO public.plants VALUES ('farm01_plant_23', 'farm_01', 'tomato', '{"x": 2.0, "y": 6.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:27:47');
INSERT INTO public.plants VALUES ('farm01_plant_24', 'farm_01', 'tomato', '{"x": 6.0, "y": 6.0, "z": 0.75, "yaw": 0.0}', false, false, false, '2026-03-30 00:28:47');
INSERT INTO public.plants VALUES ('farm01_plant_18', 'farm_01', 'tomato', '{"x": -2.0, "y": 4.0, "z": 0.75}', false, false, false, '2026-03-30 00:58:18.04462');


--
-- Data for Name: robots; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.robots VALUES ('11111111-1111-1111-1111-111111111111', 'AGR-02', 'PATROL', 82, 'farm_01', '{"x": 0.0, "y": -8.6, "z": 0.0, "yaw": 1.57, "frame_id": "map"}', '2026-03-30 00:58:26.296292');


--
-- Data for Name: zones; Type: TABLE DATA; Schema: public; Owner: agribot
--

INSERT INTO public.zones VALUES ('farm_01', 'Farm 01', '{"max_x": 10.0, "max_y": 10.0, "min_x": -10.0, "min_y": -10.0}', 'farm_world 전체를 하나의 운영 구역으로 사용합니다.');


--
-- Name: actuation_commands actuation_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.actuation_commands
    ADD CONSTRAINT actuation_commands_pkey PRIMARY KEY (id);


--
-- Name: actuation_logs actuation_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.actuation_logs
    ADD CONSTRAINT actuation_logs_pkey PRIMARY KEY (id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: crop_observations crop_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.crop_observations
    ADD CONSTRAINT crop_observations_pkey PRIMARY KEY (id);


--
-- Name: environment_samples environment_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.environment_samples
    ADD CONSTRAINT environment_samples_pkey PRIMARY KEY (id);


--
-- Name: fruits fruits_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.fruits
    ADD CONSTRAINT fruits_pkey PRIMARY KEY (id);


--
-- Name: harvest_events harvest_events_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.harvest_events
    ADD CONSTRAINT harvest_events_pkey PRIMARY KEY (id);


--
-- Name: iot_devices iot_devices_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.iot_devices
    ADD CONSTRAINT iot_devices_pkey PRIMARY KEY (id);


--
-- Name: missions missions_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.missions
    ADD CONSTRAINT missions_pkey PRIMARY KEY (id);


--
-- Name: plants plants_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_pkey PRIMARY KEY (id);


--
-- Name: robots robots_name_key; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.robots
    ADD CONSTRAINT robots_name_key UNIQUE (name);


--
-- Name: robots robots_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.robots
    ADD CONSTRAINT robots_pkey PRIMARY KEY (id);


--
-- Name: zones zones_pkey; Type: CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.zones
    ADD CONSTRAINT zones_pkey PRIMARY KEY (id);


--
-- Name: ix_fruits_id; Type: INDEX; Schema: public; Owner: agribot
--

CREATE INDEX ix_fruits_id ON public.fruits USING btree (id);


--
-- Name: ix_iot_devices_id; Type: INDEX; Schema: public; Owner: agribot
--

CREATE INDEX ix_iot_devices_id ON public.iot_devices USING btree (id);


--
-- Name: ix_plants_id; Type: INDEX; Schema: public; Owner: agribot
--

CREATE INDEX ix_plants_id ON public.plants USING btree (id);


--
-- Name: ix_zones_id; Type: INDEX; Schema: public; Owner: agribot
--

CREATE INDEX ix_zones_id ON public.zones USING btree (id);


--
-- Name: actuation_commands actuation_commands_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.actuation_commands
    ADD CONSTRAINT actuation_commands_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.iot_devices(id);


--
-- Name: actuation_commands actuation_commands_mission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.actuation_commands
    ADD CONSTRAINT actuation_commands_mission_id_fkey FOREIGN KEY (mission_id) REFERENCES public.missions(id);


--
-- Name: actuation_commands actuation_commands_observation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.actuation_commands
    ADD CONSTRAINT actuation_commands_observation_id_fkey FOREIGN KEY (observation_id) REFERENCES public.crop_observations(id);


--
-- Name: actuation_commands actuation_commands_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.actuation_commands
    ADD CONSTRAINT actuation_commands_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES public.zones(id);


--
-- Name: actuation_logs actuation_logs_command_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.actuation_logs
    ADD CONSTRAINT actuation_logs_command_id_fkey FOREIGN KEY (command_id) REFERENCES public.actuation_commands(id);


--
-- Name: actuation_logs actuation_logs_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.actuation_logs
    ADD CONSTRAINT actuation_logs_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.iot_devices(id);


--
-- Name: alerts alerts_observation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_observation_id_fkey FOREIGN KEY (observation_id) REFERENCES public.crop_observations(id);


--
-- Name: alerts alerts_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_plant_id_fkey FOREIGN KEY (plant_id) REFERENCES public.plants(id);


--
-- Name: alerts alerts_robot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_robot_id_fkey FOREIGN KEY (robot_id) REFERENCES public.robots(id);


--
-- Name: alerts alerts_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES public.zones(id);


--
-- Name: crop_observations crop_observations_fruit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.crop_observations
    ADD CONSTRAINT crop_observations_fruit_id_fkey FOREIGN KEY (fruit_id) REFERENCES public.fruits(id);


--
-- Name: crop_observations crop_observations_mission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.crop_observations
    ADD CONSTRAINT crop_observations_mission_id_fkey FOREIGN KEY (mission_id) REFERENCES public.missions(id);


--
-- Name: crop_observations crop_observations_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.crop_observations
    ADD CONSTRAINT crop_observations_plant_id_fkey FOREIGN KEY (plant_id) REFERENCES public.plants(id);


--
-- Name: crop_observations crop_observations_robot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.crop_observations
    ADD CONSTRAINT crop_observations_robot_id_fkey FOREIGN KEY (robot_id) REFERENCES public.robots(id);


--
-- Name: environment_samples environment_samples_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.environment_samples
    ADD CONSTRAINT environment_samples_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES public.zones(id);


--
-- Name: fruits fruits_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.fruits
    ADD CONSTRAINT fruits_plant_id_fkey FOREIGN KEY (plant_id) REFERENCES public.plants(id);


--
-- Name: harvest_events harvest_events_fruit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.harvest_events
    ADD CONSTRAINT harvest_events_fruit_id_fkey FOREIGN KEY (fruit_id) REFERENCES public.fruits(id);


--
-- Name: harvest_events harvest_events_mission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.harvest_events
    ADD CONSTRAINT harvest_events_mission_id_fkey FOREIGN KEY (mission_id) REFERENCES public.missions(id);


--
-- Name: harvest_events harvest_events_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.harvest_events
    ADD CONSTRAINT harvest_events_plant_id_fkey FOREIGN KEY (plant_id) REFERENCES public.plants(id);


--
-- Name: harvest_events harvest_events_robot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.harvest_events
    ADD CONSTRAINT harvest_events_robot_id_fkey FOREIGN KEY (robot_id) REFERENCES public.robots(id);


--
-- Name: iot_devices iot_devices_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.iot_devices
    ADD CONSTRAINT iot_devices_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES public.zones(id);


--
-- Name: missions missions_robot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.missions
    ADD CONSTRAINT missions_robot_id_fkey FOREIGN KEY (robot_id) REFERENCES public.robots(id);


--
-- Name: missions missions_target_fruit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.missions
    ADD CONSTRAINT missions_target_fruit_id_fkey FOREIGN KEY (target_fruit_id) REFERENCES public.fruits(id);


--
-- Name: missions missions_target_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.missions
    ADD CONSTRAINT missions_target_plant_id_fkey FOREIGN KEY (target_plant_id) REFERENCES public.plants(id);


--
-- Name: missions missions_target_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.missions
    ADD CONSTRAINT missions_target_zone_id_fkey FOREIGN KEY (target_zone_id) REFERENCES public.zones(id);


--
-- Name: plants plants_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES public.zones(id);


--
-- Name: robots robots_current_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: agribot
--

ALTER TABLE ONLY public.robots
    ADD CONSTRAINT robots_current_zone_id_fkey FOREIGN KEY (current_zone_id) REFERENCES public.zones(id);


--
-- PostgreSQL database dump complete
--

\unrestrict LCnUHV3T2zyBRwbpNsDkS1jGfLBk7YVyQKJB6r4KCgDTHJeo8dw9vm476SUzAFh

