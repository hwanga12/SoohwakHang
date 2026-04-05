# File-based QoS policy loader for primary protocol topics.
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Any

from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

try:
    from ament_index_python.packages import get_package_share_directory
except Exception:  # pragma: no cover - optional runtime dependency
    get_package_share_directory = None

try:
    import yaml
except Exception:  # pragma: no cover - optional runtime dependency
    yaml = None


_DEFAULT_PROFILE = {
    'history': 'keep_last',
    'depth': 10,
    'reliability': 'reliable',
    'durability': 'volatile',
}
_HISTORY = {
    'keep_last': HistoryPolicy.KEEP_LAST,
    'keep_all': HistoryPolicy.KEEP_ALL,
}
_RELIABILITY = {
    'reliable': ReliabilityPolicy.RELIABLE,
    'best_effort': ReliabilityPolicy.BEST_EFFORT,
}
_DURABILITY = {
    'volatile': DurabilityPolicy.VOLATILE,
    'transient_local': DurabilityPolicy.TRANSIENT_LOCAL,
}


def get_default_protocol_qos_path() -> Path:
    # Resolve the protocol QoS policy file from env, source tree, or installed share dir.
    configured_path = os.environ.get('AGRIBOT_PROTOCOL_QOS_FILE', '').strip()
    if configured_path:
        return Path(configured_path).expanduser()

    source_path = Path(__file__).resolve().parents[1] / 'config' / 'protocol_qos.yaml'
    if source_path.exists():
        return source_path

    if get_package_share_directory is not None:
        try:
            return Path(get_package_share_directory('agribot_bringup')) / 'config' / 'protocol_qos.yaml'
        except Exception:  # pragma: no cover - depends on local install layout
            pass

    return source_path


@lru_cache(maxsize=8)
def _load_protocol_qos_config(path_value: str) -> dict[str, Any]:
    # Read the YAML policy file once and reuse it for subsequent topic lookups.
    path = Path(path_value)
    if yaml is None or not path.exists():
        return {}

    payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return payload if isinstance(payload, dict) else {}


def protocol_qos_profile(topic_name: str, *, default_depth: int = 10) -> QoSProfile:
    # Build a QoS profile for the topic using the configured protocol policy file.
    profile_payload = dict(_DEFAULT_PROFILE)
    profile_payload['depth'] = max(1, int(default_depth))

    config = _load_protocol_qos_config(str(get_default_protocol_qos_path()))
    topics = config.get('topics', {})
    topic_payload = topics.get(topic_name, {}) if isinstance(topics, dict) else {}

    profile_name = ''
    if isinstance(topic_payload, dict):
        profile_name = str(topic_payload.get('profile', '')).strip()

    profiles = config.get('profiles', {})
    if profile_name and isinstance(profiles, dict) and isinstance(profiles.get(profile_name), dict):
        profile_payload.update(profiles[profile_name])

    if isinstance(topic_payload, dict):
        for key in ('history', 'depth', 'reliability', 'durability'):
            if key in topic_payload:
                profile_payload[key] = topic_payload[key]
        overrides = topic_payload.get('overrides', {})
        if isinstance(overrides, dict):
            profile_payload.update(overrides)

    history_key = str(profile_payload.get('history', 'keep_last')).strip().lower()
    reliability_key = str(profile_payload.get('reliability', 'reliable')).strip().lower()
    durability_key = str(profile_payload.get('durability', 'volatile')).strip().lower()

    return QoSProfile(
        history=_HISTORY.get(history_key, HistoryPolicy.KEEP_LAST),
        depth=max(1, int(profile_payload.get('depth', default_depth))),
        reliability=_RELIABILITY.get(reliability_key, ReliabilityPolicy.RELIABLE),
        durability=_DURABILITY.get(durability_key, DurabilityPolicy.VOLATILE),
    )
