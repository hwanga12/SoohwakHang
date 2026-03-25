from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class BackendConfirmation:
    observation_id: str
    final_label: str
    final_confidence: float
    image_path: str
    decision_source: str


class BackendClient:
    """Small HTTP client used by the robot thin inference node."""

    def __init__(self, endpoint_url: str, timeout_sec: float) -> None:
        self._endpoint_url = endpoint_url
        self._timeout_sec = timeout_sec

    def confirm_detection(self, payload: dict[str, Any]) -> BackendConfirmation:
        raw_request = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        http_request = request.Request(
            self._endpoint_url,
            data=raw_request,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with request.urlopen(http_request, timeout=self._timeout_sec) as response:
                response_payload = json.loads(response.read().decode('utf-8'))
        except error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'backend returned HTTP {exc.code}: {body}') from exc
        except error.URLError as exc:
            raise RuntimeError(f'backend request failed: {exc.reason}') from exc

        return BackendConfirmation(
            observation_id=str(response_payload.get('observation_id', payload['observation_id'])),
            final_label=str(response_payload.get('final_label', payload.get('preliminary_label', ''))),
            final_confidence=float(
                response_payload.get(
                    'final_confidence',
                    payload.get('preliminary_confidence', 0.0),
                )
            ),
            image_path=str(response_payload.get('image_path', '')),
            decision_source=str(response_payload.get('decision_source', 'backend_model')),
        )
