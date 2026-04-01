# 이 모듈은 인지와 추론 패키지에서 codebook 기능을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class CodebookEntry:
    # codebook 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    code: str
    name_en: str
    name_ko: str
    group: str
    description: str = ""
    verified: bool = True


@dataclass(frozen=True, slots=True)
class DetectionTarget:
    # detection 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    class_index: int
    disease_code: str
    class_name: str
    name_ko: str


NORMAL_DISEASE_CODE = "00"
TARGET_CROP_TOMATO_CODE = "2"
TARGET_AREA_LEAF_CODE = "3"

NORMAL_IMAGE_POLICY_NOTE = (
    "Disease code '00' means a normal image. In this detection-first project it is "
    "kept as metadata only and must be handled as a negative sample, not as a "
    "detection class."
)


def _entry(
    code: str,
    name_en: str,
    name_ko: str,
    group: str,
    *,
    description: str = "",
    verified: bool = True,
) -> CodebookEntry:
    # 항목 정보를 계산해 반환한다.
    return CodebookEntry(
        code=code,
        name_en=name_en,
        name_ko=name_ko,
        group=group,
        description=description,
        verified=verified,
    )


def _unknown_entry(code: str, group: str) -> CodebookEntry:
    # 알 수 없는 항목 정보를 계산해 반환한다.
    group_name_ko = {
        "disease": "질병",
        "physiological_disorder": "생리장해",
        "pest": "해충",
        "crop": "작물",
        "area": "부위",
        "grow": "생육 단계",
    }.get(group, "코드")
    return _entry(
        code=code,
        name_en=f"unknown_{group}_{code}",
        name_ko=f"미확인 {group_name_ko} 코드 {code}",
        group=group,
        description=(
            "The raw code is preserved, but the human-readable label still needs "
            "dataset-side verification."
        ),
        verified=False,
    )


def _build_crop_codebook() -> Mapping[str, CodebookEntry]:
    # 작물 codebook를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    entries = {
        "1": _entry(
            "1",
            "strawberry",
            "딸기",
            "crop",
            description=(
                "Non-tomato crop entry kept for cross-crop metadata handling. "
                "Recheck against raw metadata before using it as a filter policy."
            ),
            verified=False,
        ),
        "2": _entry(
            "2",
            "tomato",
            "토마토",
            "crop",
            description="Primary crop for the current detection-first pipeline.",
        ),
        "3": _entry(
            "3",
            "paprika",
            "파프리카",
            "crop",
            description=(
                "Non-tomato crop entry kept for cross-crop metadata handling. "
                "Recheck against raw metadata before using it as a filter policy."
            ),
            verified=False,
        ),
        "4": _entry(
            "4",
            "cucumber",
            "오이",
            "crop",
            description=(
                "Non-tomato crop entry kept for cross-crop metadata handling. "
                "Recheck against raw metadata before using it as a filter policy."
            ),
            verified=False,
        ),
        "5": _entry(
            "5",
            "pepper",
            "고추",
            "crop",
            description=(
                "Non-tomato crop entry kept for cross-crop metadata handling. "
                "Recheck against raw metadata before using it as a filter policy."
            ),
            verified=False,
        ),
        "6": _entry(
            "6",
            "grape",
            "포도",
            "crop",
            description=(
                "Non-tomato crop entry kept for cross-crop metadata handling. "
                "Recheck against raw metadata before using it as a filter policy."
            ),
            verified=False,
        ),
    }
    return MappingProxyType(entries)


def _build_area_codebook() -> Mapping[str, CodebookEntry]:
    # area codebook를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    entries = {
        "1": _entry(
            "1",
            "fruit",
            "과실",
            "area",
            description="Common plant part label kept for later bbox filtering.",
            verified=False,
        ),
        "2": _entry(
            "2",
            "flower",
            "꽃",
            "area",
            description="Common plant part label kept for later bbox filtering.",
            verified=False,
        ),
        "3": _entry(
            "3",
            "leaf",
            "잎",
            "area",
            description="Verified leaf area used by the current tomato disease baseline.",
        ),
        "4": _entry(
            "4",
            "stem",
            "줄기",
            "area",
            description="Common plant part label kept for later bbox filtering.",
            verified=False,
        ),
    }
    return MappingProxyType(entries)


def _build_grow_codebook() -> Mapping[str, CodebookEntry]:
    # grow codebook를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    entries = {
        "11": _entry(
            "11",
            "seedling_stage",
            "육묘기",
            "grow",
            description="AI Hub grow stage code for seedling stage.",
        ),
        "12": _entry(
            "12",
            "vegetative_stage",
            "생장기",
            "grow",
            description="AI Hub grow stage code for vegetative growth stage.",
        ),
        "13": _entry(
            "13",
            "flowering_fruiting_stage",
            "착화/과실기",
            "grow",
            description="AI Hub grow stage code for flowering and fruiting stage.",
        ),
    }
    return MappingProxyType(entries)


def _build_disease_codebook() -> Mapping[str, CodebookEntry]:
    # disease codebook를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    entries: dict[str, CodebookEntry] = {
        NORMAL_DISEASE_CODE: _entry(
            NORMAL_DISEASE_CODE,
            "normal",
            "정상",
            "disease",
            description=NORMAL_IMAGE_POLICY_NOTE,
        ),
    }

    for index in range(1, 13):
        code = f"a{index}"
        entries[code] = _unknown_entry(code, "disease")

    for index in range(1, 9):
        code = f"b{index}"
        entries[code] = _unknown_entry(code, "physiological_disorder")

    for index in (1, 2, 3, 4, 5, 6, 7, 9, 11, 12):
        code = f"c{index}"
        entries[code] = _unknown_entry(code, "pest")

    entries.update(
        {
            "a5": _entry(
                "a5",
                "tomato_powdery_mildew",
                "토마토흰가루병",
                "disease",
                description="Initial detection target.",
            ),
            "a6": _entry(
                "a6",
                "tomato_gray_mold",
                "토마토잿빛곰팡이병",
                "disease",
                description="Initial detection target.",
            ),
            "b2": _entry(
                "b2",
                "tomato_crack",
                "토마토열과",
                "physiological_disorder",
                description="Initial detection target.",
            ),
            "b3": _entry(
                "b3",
                "tomato_calcium_deficiency",
                "토마토칼슘결핍",
                "physiological_disorder",
                description="Initial detection target.",
            ),
            "b6": _entry(
                "b6",
                "tomato_nitrogen_deficiency",
                "토마토질소결핍",
                "physiological_disorder",
                description=(
                    "Known tomato physiological disorder kept in the codebook for "
                    "future filtering and analysis."
                ),
            ),
            "b7": _entry(
                "b7",
                "tomato_phosphorus_deficiency",
                "토마토인결핍",
                "physiological_disorder",
                description=(
                    "Known tomato physiological disorder kept in the codebook for "
                    "future filtering and analysis."
                ),
            ),
            "b8": _entry(
                "b8",
                "tomato_potassium_deficiency",
                "토마토칼륨결핍",
                "physiological_disorder",
                description=(
                    "Known tomato physiological disorder kept in the codebook for "
                    "future filtering and analysis."
                ),
            ),
        }
    )

    return MappingProxyType(entries)


CROP_CODEBOOK = _build_crop_codebook()
AREA_CODEBOOK = _build_area_codebook()
GROW_CODEBOOK = _build_grow_codebook()
DISEASE_CODEBOOK = _build_disease_codebook()


DETECTION_TARGETS = (
    DetectionTarget(0, "a5", "tomato_powdery_mildew", "토마토흰가루병"),
    DetectionTarget(1, "a6", "tomato_gray_mold", "토마토잿빛곰팡이병"),
    DetectionTarget(2, "b2", "tomato_crack", "토마토열과"),
    DetectionTarget(3, "b3", "tomato_calcium_deficiency", "토마토칼슘결핍"),
)

DETECTION_TARGET_BY_DISEASE_CODE = MappingProxyType(
    {target.disease_code: target for target in DETECTION_TARGETS}
)

DETECTION_CLASS_INDEX_BY_DISEASE_CODE = MappingProxyType(
    {target.disease_code: target.class_index for target in DETECTION_TARGETS}
)

DETECTION_CLASS_NAME_BY_DISEASE_CODE = MappingProxyType(
    {target.disease_code: target.class_name for target in DETECTION_TARGETS}
)


def normalize_code(value: Any) -> str:
    # code를 다른 계층에서 쓰기 쉬운 형태로 변환한다.

    if value is None:
        return ""
    return str(value).strip()


def lookup_codebook_entry(
    codebook: Mapping[str, CodebookEntry],
    code: Any,
) -> CodebookEntry | None:
    # lookup codebook 항목 정보를 계산해 반환한다.

    normalized = normalize_code(code)
    if not normalized:
        return None
    return codebook.get(normalized)


def get_crop_entry(code: Any) -> CodebookEntry | None:
    # 작물 entry를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return lookup_codebook_entry(CROP_CODEBOOK, code)


def get_disease_entry(code: Any) -> CodebookEntry | None:
    # disease entry를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return lookup_codebook_entry(DISEASE_CODEBOOK, code)


def get_area_entry(code: Any) -> CodebookEntry | None:
    # area entry를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return lookup_codebook_entry(AREA_CODEBOOK, code)


def get_grow_entry(code: Any) -> CodebookEntry | None:
    # grow entry를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return lookup_codebook_entry(GROW_CODEBOOK, code)


def get_crop_name(code: Any, default: str | None = None) -> str | None:
    # 작물 이름를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    entry = get_crop_entry(code)
    return entry.name_en if entry else default


def get_disease_name(code: Any, default: str | None = None) -> str | None:
    # disease 이름를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    entry = get_disease_entry(code)
    return entry.name_en if entry else default


def get_area_name(code: Any, default: str | None = None) -> str | None:
    # area 이름를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    entry = get_area_entry(code)
    return entry.name_en if entry else default


def get_grow_name(code: Any, default: str | None = None) -> str | None:
    # grow 이름를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    entry = get_grow_entry(code)
    return entry.name_en if entry else default


def is_tomato_crop(code: Any) -> bool:
    # tomato 작물인지 여부를 불리언 값으로 판단한다.
    return normalize_code(code) == TARGET_CROP_TOMATO_CODE


def is_leaf_area(code: Any) -> bool:
    # leaf area인지 여부를 불리언 값으로 판단한다.
    return normalize_code(code) == TARGET_AREA_LEAF_CODE


def is_negative_sample_disease(code: Any) -> bool:
    # negative sample disease인지 여부를 불리언 값으로 판단한다.
    return normalize_code(code) == NORMAL_DISEASE_CODE


def is_detection_target_disease(code: Any) -> bool:
    # detection target disease인지 여부를 불리언 값으로 판단한다.
    return normalize_code(code) in DETECTION_TARGET_BY_DISEASE_CODE


def get_detection_target(code: Any) -> DetectionTarget | None:
    # detection target를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return DETECTION_TARGET_BY_DISEASE_CODE.get(normalize_code(code))


def get_detection_class_index(code: Any) -> int | None:
    # detection class index를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return DETECTION_CLASS_INDEX_BY_DISEASE_CODE.get(normalize_code(code))


def get_detection_class_name(code: Any) -> str | None:
    # detection class 이름를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return DETECTION_CLASS_NAME_BY_DISEASE_CODE.get(normalize_code(code))


__all__ = [
    "AREA_CODEBOOK",
    "CROP_CODEBOOK",
    "DETECTION_CLASS_INDEX_BY_DISEASE_CODE",
    "DETECTION_CLASS_NAME_BY_DISEASE_CODE",
    "DETECTION_TARGET_BY_DISEASE_CODE",
    "DETECTION_TARGETS",
    "DISEASE_CODEBOOK",
    "GROW_CODEBOOK",
    "NORMAL_DISEASE_CODE",
    "NORMAL_IMAGE_POLICY_NOTE",
    "TARGET_AREA_LEAF_CODE",
    "TARGET_CROP_TOMATO_CODE",
    "CodebookEntry",
    "DetectionTarget",
    "get_area_entry",
    "get_area_name",
    "get_crop_entry",
    "get_crop_name",
    "get_detection_class_index",
    "get_detection_class_name",
    "get_detection_target",
    "get_disease_entry",
    "get_disease_name",
    "get_grow_entry",
    "get_grow_name",
    "is_detection_target_disease",
    "is_leaf_area",
    "is_negative_sample_disease",
    "is_tomato_crop",
    "lookup_codebook_entry",
    "normalize_code",
]
