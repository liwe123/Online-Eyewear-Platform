"""透明规则推荐引擎。

输入用户眼部参数与脸型，对眼镜库存打分排序，输出 Top-N 推荐
及每条命中规则的中文说明（可解释、可调参）。

打分规则（分值均为模块级常量）：
a) 脸型→镜框形状映射：命中 +40（鹅蛋脸百搭，任意形状均命中）；
b) 度数适配：lens_degree_min <= myopia_degree <= lens_degree_max，硬过滤；
c) 折射率建议（加分项不过滤）：|近视|>=6.0 且折射率为 1.67/1.74 → +20；
   |近视|>=3.0 且折射率>=1.60 → +10；
d) 瞳距适配（加分项）：镜宽+鼻梁宽 与瞳距之差 <=2mm → +10，<=4mm → +5；
e) 价格不参与打分（不设权重）。

当命中脸型规则的候选不足 top_n 时，自动放宽脸型限制按分数补满，
并在规则说明中注明。
"""
from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# 模块级常量（调参入口）
# ---------------------------------------------------------------------------
# 脸型 → 推荐镜框形状（值为空列表表示百搭）。键为去掉「脸」后缀的规范化脸型。
FACE_FRAME_MAP: dict[str, list[str]] = {
    "方形": ["圆形", "鹅蛋形", "猫眼形"],
    "圆形": ["方形", "长方形", "多边形"],
    "长方形": ["圆形", "猫眼形", "鹅蛋形"],
    "鹅蛋": [],
}

# 各脸型推荐理由模板（用于全局规则说明）
_FACE_RULE_REASON: dict[str, str] = {
    "方形": "以柔和脸部轮廓",
    "圆形": "以拉长脸部线条",
    "长方形": "以缩短视觉脸长",
    "鹅蛋": "鹅蛋脸为百搭脸型，各形状镜框均可驾驭",
}

SCORE_FACE_MATCH: int = 40        # 脸型命中加分
SCORE_REFRACTION_HIGH: int = 20   # 高度近视优选折射率加分
SCORE_REFRACTION_MID: int = 10    # 中度近视折射率加分
SCORE_PD_EXCELLENT: int = 10      # 瞳距匹配优秀加分
SCORE_PD_GOOD: int = 5            # 瞳距匹配良好加分

HIGH_MYOPIA_THRESHOLD: float = 6.0                 # 高度近视阈值（|度数|）
MID_MYOPIA_THRESHOLD: float = 3.0                  # 中度近视阈值（|度数|）
PREFERRED_INDICES_HIGH: tuple[float, ...] = (1.67, 1.74)  # 高度近视优选折射率
PREFERRED_INDEX_MID: float = 1.60                  # 中度近视建议最低折射率

PD_EXCELLENT_DIFF_MM: float = 2.0  # 瞳距匹配优秀阈值（毫米）
PD_GOOD_DIFF_MM: float = 4.0       # 瞳距匹配良好阈值（毫米）

# 返回给前端的推荐字段（API 契约）
RECOMMEND_FIELDS: tuple[str, ...] = (
    "glasses_id",
    "name",
    "brand",
    "frame_shape",
    "frame_size",
    "frame_material",
    "lens_refractive_index",
    "price",
    "image_url",
)

_FRAME_SIZE_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _normalize_face_shape(face_shape: str) -> str:
    """规范化脸型标签（去掉末尾「脸」字并去空白），便于查 FACE_FRAME_MAP。

    参数:
        face_shape: 原始脸型标签，如「方形脸」「鹅蛋脸」「长方形」。

    返回:
        规范化后的键，如「方形」「鹅蛋」「长方形」。
    """
    key = str(face_shape or "").strip()
    return key[:-1] if key.endswith("脸") else key


def _display_face_shape(face_shape: str) -> str:
    """生成用于展示的脸型名称（确保以「脸」字结尾）。

    参数:
        face_shape: 原始脸型标签。

    返回:
        如「方形脸」「长方形脸」；空输入原样返回。
    """
    name = str(face_shape or "").strip()
    if name and not name.endswith("脸"):
        return name + "脸"
    return name


def _parse_frame_size(frame_size: Any) -> tuple[Optional[float], Optional[float]]:
    """解析 frame_size 字符串（如「52-18-140」）。

    参数:
        frame_size: 尺寸字符串，三段依次为镜宽、鼻梁宽、镜腿長（毫米）。

    返回:
        (镜宽, 鼻梁宽)；解析失败返回 (None, None)。
    """
    if not isinstance(frame_size, str):
        return None, None
    nums = _FRAME_SIZE_PATTERN.findall(frame_size)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    if len(nums) == 1:
        return float(nums[0]), None
    return None, None


def _refraction_bonus(myopia_degree: float, refractive_index: Optional[float]) -> tuple[int, Optional[str]]:
    """计算折射率加分及原因。

    参数:
        myopia_degree: 近视度数（负值）。
        refractive_index: 镜片折射率，缺失为 None。

    返回:
        (加分, 原因字符串)；无加分时原因为 None。
    """
    if refractive_index is None:
        return 0, None
    degree_abs = abs(myopia_degree)
    if degree_abs >= HIGH_MYOPIA_THRESHOLD and refractive_index in PREFERRED_INDICES_HIGH:
        return SCORE_REFRACTION_HIGH, f"高度近视(|{myopia_degree}|≥{HIGH_MYOPIA_THRESHOLD})适配高折射率{refractive_index}"
    if degree_abs >= MID_MYOPIA_THRESHOLD and refractive_index >= PREFERRED_INDEX_MID:
        return SCORE_REFRACTION_MID, f"中度近视(|{myopia_degree}|≥{MID_MYOPIA_THRESHOLD})适配折射率{refractive_index}"
    return 0, None


def _pd_bonus(pupil_distance: float, frame_size: Any) -> tuple[int, Optional[str]]:
    """计算瞳距匹配加分及原因。

    镜框瞳距近似为 镜宽+鼻梁宽（如「52-18-140」→ 70mm），与用户瞳距
    差值越小越匹配（瞳距大 → 镜宽宜大）。

    参数:
        pupil_distance: 用户瞳距（毫米）。
        frame_size: 镜框尺寸字符串。

    返回:
        (加分, 原因字符串)；无法解析或无加分时原因为 None。
    """
    lens_w, bridge_w = _parse_frame_size(frame_size)
    if lens_w is None:
        return 0, None
    frame_pd = lens_w + (bridge_w or 0.0)
    diff = abs(frame_pd - pupil_distance)
    size_desc = f"镜宽{lens_w:g}+鼻梁{(bridge_w or 0.0):g}={frame_pd:g}mm"
    if diff <= PD_EXCELLENT_DIFF_MM:
        return SCORE_PD_EXCELLENT, f"{size_desc}与瞳距{pupil_distance:g}mm差{diff:.1f}mm，匹配优秀"
    if diff <= PD_GOOD_DIFF_MM:
        return SCORE_PD_GOOD, f"{size_desc}与瞳距{pupil_distance:g}mm差{diff:.1f}mm，匹配良好"
    return 0, None


def recommend(
    pupil_distance: float,
    corneal_curvature: float,
    myopia_degree: float,
    face_shape: str,
    glasses_df: pd.DataFrame,
    top_n: int = 3,
) -> tuple[list[dict], list[str]]:
    """基于透明规则为用户推荐眼镜。

    参数:
        pupil_distance: 瞳距（毫米）。
        corneal_curvature: 角膜曲率（当前规则集未使用，保留扩展）。
        myopia_degree: 近视度数（负值，如 -3.5 表示 350 度）。
        face_shape: 脸型标签（如「方形」「鹅蛋脸」）。
        glasses_df: 眼镜库存 DataFrame，需包含 RECOMMEND_FIELDS
            及 lens_degree_min / lens_degree_max 列。
        top_n: 返回推荐数量。

    返回:
        (推荐列表, 规则说明列表)：
        - 推荐列表元素为 dict，含 RECOMMEND_FIELDS 字段外加 score、reason；
        - 规则说明列表为中文规则命中描述。
    """
    rules: list[str] = []
    face_key = _normalize_face_shape(face_shape)
    face_name = _display_face_shape(face_shape)

    df = glasses_df.copy()
    df["frame_shape"] = df["frame_shape"].astype(str).str.strip()
    for col in ("lens_degree_min", "lens_degree_max", "lens_refractive_index", "price"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.drop_duplicates(subset="glasses_id")

    # b) 度数适配（兼容用户输入习惯：正数表示"度数"如300，负数/0 表示屈光度；0 或 None 视为不近视，不硬过滤）
    normalized_degree: Optional[float] = None
    if myopia_degree is None or pd.isna(myopia_degree):
        rules.append("未提供近视度数，跳过度数硬过滤")
    elif myopia_degree == 0:
        rules.append("近视度数为 0，可配任何镜框（跳过度数硬过滤）")
    elif myopia_degree > 0:
        normalized_degree = -myopia_degree / 100.0
        rules.append(f"收到正数度数 {myopia_degree}，按屈光度 {normalized_degree:.2f}D 进行适配")
    else:
        normalized_degree = float(myopia_degree)

    if normalized_degree is not None:
        degree_mask = (df["lens_degree_min"] <= normalized_degree) & (normalized_degree <= df["lens_degree_max"])
        filtered_df = df[degree_mask]
        rules.append(
            f"度数适配：近视{normalized_degree:.2f}D，仅保留可配度数范围覆盖该度数的镜框（硬过滤，剩{len(filtered_df)}款）"
        )
        if filtered_df.empty:
            rules.append(
                f"库存中无完全匹配 {normalized_degree:.2f}D 的镜框，已放宽度数限制，优先按脸型/瞳距推荐"
            )
        else:
            df = filtered_df

    if df.empty:
        rules.append("库存为空，推荐结果为空")
        return [], rules

    # a) 脸型 → 镜框形状映射
    face_known = face_key in FACE_FRAME_MAP
    preferred_shapes = FACE_FRAME_MAP.get(face_key)
    if preferred_shapes is None:
        rules.append(f"未识别的脸型「{face_shape}」，脸型维度不打分，按其余规则推荐")
        preferred_shapes = []
    elif len(preferred_shapes) == 0:
        rules.append(_FACE_RULE_REASON.get(face_key, f"{face_shape}百搭"))
    else:
        reason_tail = _FACE_RULE_REASON.get(face_key, "")
        rules.append(f"{face_name}推荐{'/'.join(preferred_shapes)}镜框{reason_tail}")

    # c) 折射率建议说明（加分项，不过滤）
    degree_for_refraction = normalized_degree if normalized_degree is not None else 0.0
    degree_abs = abs(degree_for_refraction)
    if degree_abs >= HIGH_MYOPIA_THRESHOLD:
        rules.append(
            f"高度近视(|{degree_for_refraction:.2f}|≥{HIGH_MYOPIA_THRESHOLD})：折射率1.67/1.74优先（+{SCORE_REFRACTION_HIGH}分）"
        )
    elif degree_abs >= MID_MYOPIA_THRESHOLD:
        rules.append(
            f"中度近视(|{degree_for_refraction:.2f}|≥{MID_MYOPIA_THRESHOLD}）：建议折射率≥{PREFERRED_INDEX_MID}（+{SCORE_REFRACTION_MID}分）"
        )

    # d) 瞳距适配说明
    rules.append(
        f"瞳距{pupil_distance:g}mm：镜宽+鼻梁宽与瞳距差≤{PD_EXCELLENT_DIFF_MM:g}mm加{SCORE_PD_EXCELLENT}分，"
        f"≤{PD_GOOD_DIFF_MM:g}mm加{SCORE_PD_GOOD}分"
    )

    # 逐款打分
    scored: list[dict] = []
    for row in df.itertuples(index=False):
        item: dict = {field: getattr(row, field, None) for field in RECOMMEND_FIELDS}
        # numpy 标量转 Python 原生类型，保证可 JSON 序列化
        if item["lens_refractive_index"] is not None and pd.notna(item["lens_refractive_index"]):
            item["lens_refractive_index"] = float(item["lens_refractive_index"])
        else:
            item["lens_refractive_index"] = None
        item["price"] = float(item["price"]) if pd.notna(item["price"]) else None

        score = 0
        item_reasons: list[str] = []
        shape = str(getattr(row, "frame_shape", "")).strip()

        # a) 脸型加分（preferred_shapes 为空表示百搭或未识别，均命中）
        if len(preferred_shapes) == 0 or shape in preferred_shapes:
            score += SCORE_FACE_MATCH
            if face_known:
                face_reason = _FACE_RULE_REASON.get(face_key, "")
                if face_reason:
                    item_reasons.append(f"{face_name}适配{shape}镜框，{face_reason}")
                else:
                    item_reasons.append(f"{face_name}适配{shape}镜框")
            item["_face_matched"] = True
        else:
            item["_face_matched"] = False

        # c) 折射率加分
        bonus, why = _refraction_bonus(degree_for_refraction, item["lens_refractive_index"])
        if bonus:
            score += bonus
            item_reasons.append(why)

        # d) 瞳距加分
        bonus, why = _pd_bonus(pupil_distance, getattr(row, "frame_size", None))
        if bonus:
            score += bonus
            item_reasons.append(why)

        item["score"] = score
        item["reason"] = "；".join(item_reasons) if item_reasons else "基础推荐"
        scored.append(item)

    # e) 按分数降序（价格不设权重；同分保持库存原有顺序）
    scored.sort(key=lambda x: -x["score"])
    selected = scored[:top_n]

    # 脸型限制放宽说明：所选中有未命中脸型规则者
    relaxed_count = sum(1 for it in selected if not it["_face_matched"])
    if relaxed_count > 0:
        rules.append(
            f"符合「{face_name}」推荐形状的镜框不足{top_n}款，已放宽脸型限制补满"
            f"（{relaxed_count}款为脸型维度外推荐）"
        )
        for it in selected:
            if not it["_face_matched"]:
                it["reason"] = "脸型限制已放宽；" + it["reason"]

    for it in selected:
        it.pop("_face_matched", None)
    return selected, rules
