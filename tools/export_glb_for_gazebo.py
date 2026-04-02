#!/usr/bin/env python3

# 이 스크립트는 개발 보조 도구로서 export glb for gazebo 작업을 수행한다.
from __future__ import annotations

import argparse
import colorsys
import json
import math
import struct
from pathlib import Path
from typing import Iterable


COMPONENT_INFO = {
    5121: ("B", 1),
    5123: ("H", 2),
    5125: ("I", 4),
    5126: ("f", 4),
}

TYPE_COMPONENTS = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
}


def load_glb(path: Path) -> tuple[dict, bytes]:
    # GLB를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"{path} is not a GLB file")
    if version != 2:
        raise ValueError(f"{path} uses unsupported glTF version {version}")

    offset = 12
    gltf = None
    binary = None
    while offset < length:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == 0x4E4F534A:
            gltf = json.loads(chunk.decode("utf-8"))
        elif chunk_type == 0x004E4942:
            binary = chunk

    if gltf is None or binary is None:
        raise ValueError(f"{path} is missing required GLB chunks")
    return gltf, binary


def identity_matrix() -> list[list[float]]:
    # identity 행렬 정보를 계산해 반환한다.
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def multiply_matrix(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    # multiply 행렬 정보를 계산해 반환한다.
    out = [[0.0] * 4 for _ in range(4)]
    for row in range(4):
        for col in range(4):
            out[row][col] = sum(a[row][k] * b[k][col] for k in range(4))
    return out


def transpose_matrix(m: list[list[float]]) -> list[list[float]]:
    # transpose 행렬 정보를 계산해 반환한다.
    return [[m[col][row] for col in range(4)] for row in range(4)]


def inverse_matrix(m: list[list[float]]) -> list[list[float]]:
    # inverse 행렬 정보를 계산해 반환한다.
    n = 4
    aug = [row[:] + identity_row[:] for row, identity_row in zip(m, identity_matrix())]

    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("Matrix is singular")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]

        pivot_value = aug[col][col]
        aug[col] = [value / pivot_value for value in aug[col]]

        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [
                current - factor * pivot_entry
                for current, pivot_entry in zip(aug[row], aug[col])
            ]

    return [row[n:] for row in aug]


def matrix_from_trs(
    translation: Iterable[float] | None,
    rotation: Iterable[float] | None,
    scale: Iterable[float] | None,
) -> list[list[float]]:
    # 행렬 trs 정보를 계산해 반환한다.
    tx, ty, tz = translation or (0.0, 0.0, 0.0)
    qx, qy, qz, qw = rotation or (0.0, 0.0, 0.0, 1.0)
    sx, sy, sz = scale or (1.0, 1.0, 1.0)

    xx = qx * qx
    yy = qy * qy
    zz = qz * qz
    xy = qx * qy
    xz = qx * qz
    yz = qy * qz
    wx = qw * qx
    wy = qw * qy
    wz = qw * qz

    return [
        [
            (1.0 - 2.0 * (yy + zz)) * sx,
            (2.0 * (xy - wz)) * sy,
            (2.0 * (xz + wy)) * sz,
            tx,
        ],
        [
            (2.0 * (xy + wz)) * sx,
            (1.0 - 2.0 * (xx + zz)) * sy,
            (2.0 * (yz - wx)) * sz,
            ty,
        ],
        [
            (2.0 * (xz - wy)) * sx,
            (2.0 * (yz + wx)) * sy,
            (1.0 - 2.0 * (xx + yy)) * sz,
            tz,
        ],
        [0.0, 0.0, 0.0, 1.0],
    ]


def node_matrix(node: dict) -> list[list[float]]:
    # 노드 행렬 정보를 계산해 반환한다.
    if "matrix" in node:
        values = node["matrix"]
        return [
            [values[0], values[4], values[8], values[12]],
            [values[1], values[5], values[9], values[13]],
            [values[2], values[6], values[10], values[14]],
            [values[3], values[7], values[11], values[15]],
        ]
    return matrix_from_trs(
        node.get("translation"),
        node.get("rotation"),
        node.get("scale"),
    )


def apply_transform(matrix: list[list[float]], vector: tuple[float, ...]) -> tuple[float, float, float]:
    # 변환에 반영한다.
    x, y, z = vector[:3]
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


def apply_normal_transform(matrix: list[list[float]], vector: tuple[float, ...]) -> tuple[float, float, float]:
    # 법선 변환에 반영한다.
    normal_matrix = transpose_matrix(inverse_matrix(matrix))
    x, y, z = vector[:3]
    tx = normal_matrix[0][0] * x + normal_matrix[0][1] * y + normal_matrix[0][2] * z
    ty = normal_matrix[1][0] * x + normal_matrix[1][1] * y + normal_matrix[1][2] * z
    tz = normal_matrix[2][0] * x + normal_matrix[2][1] * y + normal_matrix[2][2] * z
    length = math.sqrt(tx * tx + ty * ty + tz * tz)
    if length < 1e-12:
        return (0.0, 0.0, 1.0)
    return (tx / length, ty / length, tz / length)


def read_accessor(gltf: dict, binary: bytes, accessor_index: int) -> list[tuple[float, ...]]:
    # accessor를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    accessor = gltf["accessors"][accessor_index]
    buffer_view = gltf["bufferViews"][accessor["bufferView"]]
    format_char, component_size = COMPONENT_INFO[accessor["componentType"]]
    component_count = TYPE_COMPONENTS[accessor["type"]]
    item_size = component_size * component_count
    stride = buffer_view.get("byteStride", item_size)
    offset = buffer_view.get("byteOffset", 0) + accessor.get("byteOffset", 0)

    values = []
    for index in range(accessor["count"]):
        start = offset + index * stride
        values.append(
            struct.unpack_from("<" + format_char * component_count, binary, start)
        )
    return values


def extract_image(
    gltf: dict,
    binary: bytes,
    image_index: int,
    output_dir: Path,
    texture_stem: str,
) -> str:
    # 원본 데이터에서 이미지만 골라 추출한다.
    image = gltf["images"][image_index]
    buffer_view = gltf["bufferViews"][image["bufferView"]]
    start = buffer_view.get("byteOffset", 0)
    end = start + buffer_view["byteLength"]
    extension = ".png" if image["mimeType"] == "image/png" else ".jpg"
    output_name = f"{texture_stem}_texture{extension}"
    output_path = output_dir / output_name
    output_path.write_bytes(binary[start:end])
    return output_name


def material_texture(
    gltf: dict,
    binary: bytes,
    material: dict,
    output_dir: Path,
    texture_stem: str,
) -> str | None:
    # material 텍스처 정보를 계산해 반환한다.
    pbr = material.get("pbrMetallicRoughness", {})
    texture_info = pbr.get("baseColorTexture")
    if texture_info is None:
        spec_gloss = material.get("extensions", {}).get("KHR_materials_pbrSpecularGlossiness")
        if spec_gloss:
            texture_info = spec_gloss.get("diffuseTexture")
    if texture_info is None:
        return None

    texture = gltf["textures"][texture_info["index"]]
    return extract_image(gltf, binary, texture["source"], output_dir, texture_stem)


def sanitize_name(name: str) -> str:
    # sanitize name 정보를 계산해 반환한다.
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in name)


def average_color(colors: list[tuple[float, ...]] | None) -> tuple[float, float, float]:
    # average 색상 정보를 계산해 반환한다.
    if not colors:
        return (0.8, 0.8, 0.8)
    channel_count = min(3, len(colors[0]))
    return tuple(sum(color[i] for color in colors) / len(colors) for i in range(channel_count))


def boost_tomato_red(color: tuple[float, float, float]) -> tuple[float, float, float]:
    # boost tomato red 정보를 계산해 반환한다.
    r, g, b = color
    if r <= g * 1.5 or r <= b * 2.0:
        return color

    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    red_distance = min(abs(hue), abs(1.0 - hue))
    if red_distance > 0.08 or saturation < 0.5:
        return color

    if hue <= 0.5:
        hue *= 0.35
    else:
        hue = 1.0 - (1.0 - hue) * 0.35
    saturation = min(1.0, max(saturation, 0.92))
    value = min(1.0, max(value, 0.95))
    return colorsys.hsv_to_rgb(hue, saturation, value)


def tune_vertex_color(
    glb_path: Path,
    primitive_name: str,
    color: tuple[float, float, float],
) -> tuple[float, float, float]:
    # tune vertex 색상 정보를 계산해 반환한다.
    if "tomato" in glb_path.stem.lower():
        return boost_tomato_red(color)
    return color


def export_obj(glb_path: Path, obj_path: Path) -> None:
    # 내보내기 obj 정보를 계산해 반환한다.
    gltf, binary = load_glb(glb_path)
    output_dir = obj_path.parent
    mtl_path = obj_path.with_suffix(".mtl")

    material_defs: list[str] = []
    material_names: dict[str, str] = {}
    material_cache: dict[int, str] = {}
    image_cache: dict[int, str] = {}

    def resolve_material(
        material_index: int | None,
        colors: list[tuple[float, ...]] | None,
        primitive_name: str,
    ) -> str:
        # 현재 입력 조건을 바탕으로 material를 계산하거나 결정한다.
        if material_index is not None and material_index in material_cache:
            cached_name = material_cache[material_index]
            material = gltf["materials"][material_index]
            textured = material_texture(gltf, binary, material, output_dir, obj_path.stem)
            if textured or not colors:
                return cached_name

        if material_index is None:
            name = f"{obj_path.stem}_default"
            if name not in material_names:
                kd = average_color(colors)
                kd = tune_vertex_color(glb_path, primitive_name, kd)
                material_defs.extend(
                    [
                        f"newmtl {name}",
                        "Ka 0.200000 0.200000 0.200000",
                        f"Kd {kd[0]:.6f} {kd[1]:.6f} {kd[2]:.6f}",
                        "Ks 0.000000 0.000000 0.000000",
                        "d 1.0",
                        "illum 2",
                        "",
                    ]
                )
                material_names[name] = name
            return name

        material = gltf["materials"][material_index]
        name = sanitize_name(material.get("name", f"material_{material_index}"))
        kd = average_color(colors)
        base_color = material.get("pbrMetallicRoughness", {}).get("baseColorFactor")
        if base_color:
            kd = tuple(base_color[:3])
        elif colors:
            kd = tune_vertex_color(glb_path, primitive_name, kd)

        texture_name = None
        if material_index in image_cache:
            texture_name = image_cache[material_index]
        else:
            texture_name = material_texture(
                gltf, binary, material, output_dir, obj_path.stem
            )
            if texture_name:
                image_cache[material_index] = texture_name

        if colors and texture_name is None:
            name = f"{name}_{sanitize_name(primitive_name)}"
        elif name in material_names:
            material_cache[material_index] = name
            return name

        material_defs.extend(
            [
                f"newmtl {name}",
                "Ka 0.200000 0.200000 0.200000",
                f"Kd {kd[0]:.6f} {kd[1]:.6f} {kd[2]:.6f}",
                "Ks 0.000000 0.000000 0.000000",
                "d 1.0",
                "illum 2",
            ]
        )

        if texture_name:
            material_defs.append(f"map_Kd {texture_name}")
        material_defs.append("")

        material_names[name] = name
        material_cache[material_index] = name
        return name

    vertices: list[str] = [f"mtllib {mtl_path.name}", ""]
    vertex_offset = 1
    texcoord_offset = 1
    normal_offset = 1

    scene_index = gltf.get("scene", 0)
    scene_nodes = gltf["scenes"][scene_index]["nodes"]

    def export_node(node_index: int, parent_transform: list[list[float]]) -> None:
        # 내보내기 노드 정보를 계산해 반환한다.
        nonlocal vertex_offset, texcoord_offset, normal_offset

        node = gltf["nodes"][node_index]
        transform = multiply_matrix(parent_transform, node_matrix(node))
        node_name = sanitize_name(node.get("name", f"node_{node_index}"))

        if "mesh" in node:
            mesh = gltf["meshes"][node["mesh"]]
            for primitive_index, primitive in enumerate(mesh["primitives"]):
                if primitive.get("mode", 4) != 4:
                    raise ValueError(f"Unsupported primitive mode in {glb_path}")

                positions = read_accessor(gltf, binary, primitive["attributes"]["POSITION"])
                normals = None
                if "NORMAL" in primitive["attributes"]:
                    normals = read_accessor(gltf, binary, primitive["attributes"]["NORMAL"])
                texcoords = None
                if "TEXCOORD_0" in primitive["attributes"]:
                    texcoords = read_accessor(gltf, binary, primitive["attributes"]["TEXCOORD_0"])
                colors = None
                if "COLOR_0" in primitive["attributes"]:
                    colors = read_accessor(gltf, binary, primitive["attributes"]["COLOR_0"])
                indices = [value[0] for value in read_accessor(gltf, binary, primitive["indices"])]

                transformed_positions = [apply_transform(transform, pos) for pos in positions]
                transformed_normals = (
                    [apply_normal_transform(transform, normal) for normal in normals]
                    if normals
                    else None
                )
                primitive_name = f"{node_name}_{primitive_index}"
                material_name = resolve_material(
                    primitive.get("material"),
                    colors,
                    primitive_name,
                )

                vertices.append(f"o {primitive_name}")
                vertices.append(f"usemtl {material_name}")
                for position in transformed_positions:
                    vertices.append(
                        f"v {position[0]:.6f} {position[1]:.6f} {position[2]:.6f}"
                    )
                if texcoords:
                    for texcoord in texcoords:
                        vertices.append(f"vt {texcoord[0]:.6f} {1.0 - texcoord[1]:.6f}")
                if transformed_normals:
                    for normal in transformed_normals:
                        vertices.append(
                            f"vn {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}"
                        )

                for face_start in range(0, len(indices), 3):
                    face_indices = indices[face_start : face_start + 3]
                    face_tokens = []
                    for face_index in face_indices:
                        v = vertex_offset + face_index
                        vt = texcoord_offset + face_index if texcoords else None
                        vn = normal_offset + face_index if transformed_normals else None
                        if vt is not None and vn is not None:
                            face_tokens.append(f"{v}/{vt}/{vn}")
                        elif vt is not None:
                            face_tokens.append(f"{v}/{vt}")
                        elif vn is not None:
                            face_tokens.append(f"{v}//{vn}")
                        else:
                            face_tokens.append(str(v))
                    vertices.append("f " + " ".join(face_tokens))
                vertices.append("")

                vertex_offset += len(transformed_positions)
                if texcoords:
                    texcoord_offset += len(texcoords)
                if transformed_normals:
                    normal_offset += len(transformed_normals)

        for child_index in node.get("children", []):
            export_node(child_index, transform)

    for root_node in scene_nodes:
        export_node(root_node, identity_matrix())

    obj_path.write_text("\n".join(vertices) + "\n", encoding="utf-8")
    mtl_path.write_text("\n".join(material_defs) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    # args를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    return parser.parse_args()


def main() -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    args = parse_args()
    args.target.parent.mkdir(parents=True, exist_ok=True)
    export_obj(args.source, args.target)


if __name__ == "__main__":
    main()
