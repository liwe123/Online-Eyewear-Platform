# -*- coding: utf-8 -*-
"""recommend_rules 透明规则引擎测试。"""
import re

import pandas as pd
import pytest

from recommend_rules import RECOMMEND_FIELDS, recommend

# 12 条测试库存：覆盖各形状 / 度数范围 / 折射率
ROWS = [
    # glasses_id, shape, size, material, dmin, dmax, refractive_index, price
    ("R001", "圆形",   "50-20-140", "TR90",     -8.0,  0.0,  1.74, 399.0),
    ("R002", "圆形",   "52-18-140", "金属",      -4.0,  0.0,  1.56, 299.0),
    ("R003", "圆形",   "48-18-138", "复合板材",   -6.0, -1.0,  1.60, 499.0),
    ("R004", "方形",   "54-16-140", "TR90",      -6.0,  0.0,  1.56, 199.0),
    ("R005", "方形",   "52-18-142", "金属",      -2.0,  0.0,  1.50, 159.0),
    ("R006", "长方形", "56-16-144", "纯钛",      -8.0, -0.25, 1.67, 899.0),
    ("R007", "长方形", "55-17-140", "TR90",      -6.0,  0.0,  1.60, 349.0),
    ("R008", "猫眼形", "51-21-139", "复合板材",   -8.0, -0.5,  1.74, 519.0),
    ("R009", "多边形", "50-19-140", "金属",      -6.0,  0.0,  1.60, 459.0),
    ("R010", "鹅蛋形", "52-18-140", "TR90",      -4.0,  0.0,  1.56, 259.0),
    ("R011", "圆形",   "50-20-140", "TR90",     -10.0, -6.0,  1.74, 699.0),
    ("R012", "方形",   "53-17-141", "金属",      -0.5,  2.0,  1.50, 129.0),
]
COLUMNS = ["glasses_id", "frame_shape", "frame_size", "frame_material",
           "lens_degree_min", "lens_degree_max", "lens_refractive_index", "price"]

# 所有 frame_pd（镜宽+鼻梁宽）均 ≥ 66mm，瞳距取 60 时瞳距加分恒为 0
NO_PD_BONUS_PD = 60.0


@pytest.fixture()
def glasses_df():
    return pd.DataFrame(ROWS, columns=COLUMNS)


def _small_df(rows):
    return pd.DataFrame(rows, columns=COLUMNS)


class TestDegreeHardFilter:
    """度数适配硬过滤。"""

    def test_out_of_range_items_filtered(self, glasses_df):
        items, rules = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-3.0, face_shape="方形",
            glasses_df=glasses_df, top_n=3,
        )
        returned_ids = {it["glasses_id"] for it in items}
        # R005(-2~0)、R011(-10~-6)、R012(-0.5~2) 均不覆盖 -3.0
        assert returned_ids.isdisjoint({"R005", "R011", "R012"})
        assert len(items) == 3

    def test_no_match_returns_empty_with_rules(self, glasses_df):
        items, rules = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-20.0, face_shape="方形",
            glasses_df=glasses_df, top_n=3,
        )
        assert items == []
        assert len(rules) >= 1
        assert any("无适配" in r for r in rules)

    def test_boundary_degree_included(self, glasses_df):
        # R005 范围 -2.0~0.0，-2.0 为边界值应被保留
        items, _ = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-2.0, face_shape="圆形",  # 圆形脸推荐 方形/长方形/多边形
            glasses_df=glasses_df, top_n=10,
        )
        assert "R005" in {it["glasses_id"] for it in items}


class TestFaceShapeMapping:
    """脸型→镜框形状映射。"""

    def test_square_face_hits_mapped_shapes(self, glasses_df):
        items, rules = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-2.0, face_shape="方形",
            glasses_df=glasses_df, top_n=3,
        )
        # 方形脸映射：圆形/鹅蛋形/猫眼形；映射内候选 ≥3 不需放宽
        assert len(items) == 3
        for it in items:
            assert it["frame_shape"] in {"圆形", "鹅蛋形", "猫眼形"}
            # -2.0 无折射率加分，pd=60 无瞳距加分 → 仅脸型分 40
            assert it["score"] == 40

    def test_face_shape_with_suffix_normalized(self, glasses_df):
        # 「方形脸」与「方形」应等价
        items_a, _ = recommend(NO_PD_BONUS_PD, 43.0, -2.0, "方形", glasses_df, top_n=3)
        items_b, _ = recommend(NO_PD_BONUS_PD, 43.0, -2.0, "方形脸", glasses_df, top_n=3)
        assert [it["glasses_id"] for it in items_a] == [it["glasses_id"] for it in items_b]

    def test_oval_face_matches_everything(self, glasses_df):
        items, rules = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-2.0, face_shape="鹅蛋脸",
            glasses_df=glasses_df, top_n=5,
        )
        assert any("百搭" in r for r in rules)
        assert len(items) == 5
        # 鹅蛋脸百搭：所有形状均命中脸型分
        assert all(it["score"] == 40 for it in items)

    def test_unknown_face_shape(self, glasses_df):
        items, rules = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-2.0, face_shape="瓜子脸",
            glasses_df=glasses_df, top_n=3,
        )
        assert any("未识别的脸型" in r for r in rules)
        # 脸型维度不打分：无任何加分项的条目应给出「基础推荐」
        assert any(it["reason"] == "基础推荐" for it in items)


class TestScoring:
    """折射率 / 瞳距加分对排序的影响。"""

    def test_refraction_bonus_changes_ranking(self):
        df = _small_df([
            ("H1", "圆形", "50-20-140", "TR90", -8.0, 0.0, 1.74, 100.0),
            ("H2", "圆形", "50-20-140", "TR90", -8.0, 0.0, 1.50, 200.0),
        ])
        items, rules = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-7.0, face_shape="方形",  # 高度近视，圆形命中脸型
            glasses_df=df, top_n=2,
        )
        assert items[0]["glasses_id"] == "H1", "高度近视下 1.74 折射率应排在 1.50 前"
        assert items[0]["score"] > items[1]["score"]
        assert items[0]["score"] - items[1]["score"] == 20
        assert any("高度近视" in r for r in rules)

    def test_mid_myopia_refraction_rule_text(self, glasses_df):
        _, rules = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-4.0, face_shape="方形",
            glasses_df=glasses_df, top_n=3,
        )
        assert any("中度近视" in r for r in rules)

    def test_pd_bonus_changes_ranking(self):
        df = _small_df([
            ("P1", "圆形", "50-20-140", "TR90", -8.0, 0.0, 1.50, 100.0),  # frame_pd=70
            ("P2", "圆形", "56-22-140", "TR90", -8.0, 0.0, 1.50, 200.0),  # frame_pd=78
        ])
        items, _ = recommend(
            pupil_distance=70.0, corneal_curvature=43.0,
            myopia_degree=-2.0, face_shape="方形",  # 两者脸型均命中，仅瞳距分差
            glasses_df=df, top_n=2,
        )
        assert items[0]["glasses_id"] == "P1", "瞳距差 0mm 的镜框应排在差 8mm 前"
        assert items[0]["score"] - items[1]["score"] == 10
        assert "匹配优秀" in items[0]["reason"]


class TestRelaxFaceLimit:
    """脸型候选不足 top_n 时放宽补满。"""

    def test_relax_to_fill_top_n(self):
        df = _small_df([
            ("F1", "圆形", "50-20-140", "TR90", -8.0, 0.0, 1.50, 100.0),  # 方形脸命中
            ("F2", "方形", "50-20-140", "TR90", -8.0, 0.0, 1.50, 200.0),  # 不命中
            ("F3", "方形", "50-20-140", "TR90", -8.0, 0.0, 1.50, 300.0),  # 不命中
        ])
        items, rules = recommend(
            pupil_distance=NO_PD_BONUS_PD, corneal_curvature=43.0,
            myopia_degree=-2.0, face_shape="方形",
            glasses_df=df, top_n=3,
        )
        assert len(items) == 3, "映射内仅 1 款，应放宽脸型限制补满 3 款"
        assert any("已放宽脸型限制补满" in r for r in rules)
        relaxed = [it for it in items if it["frame_shape"] != "圆形"]
        assert len(relaxed) == 2
        for it in relaxed:
            assert it["reason"].startswith("脸型限制已放宽；")
        # 命中的 F1 排第一
        assert items[0]["glasses_id"] == "F1"


class TestResultContract:
    """返回结构契约。"""

    def test_rules_are_nonempty_chinese(self, glasses_df):
        _, rules = recommend(
            pupil_distance=62.0, corneal_curvature=43.0,
            myopia_degree=-3.5, face_shape="方形",
            glasses_df=glasses_df, top_n=3,
        )
        assert len(rules) >= 3, "至少应包含度数/脸型/瞳距三类规则说明"
        for rule in rules:
            assert isinstance(rule, str) and rule.strip()
            assert re.search(r"[一-鿿]", rule), f"规则说明应为中文: {rule}"

    def test_item_fields_complete(self, glasses_df):
        items, _ = recommend(
            pupil_distance=62.0, corneal_curvature=43.0,
            myopia_degree=-3.5, face_shape="方形",
            glasses_df=glasses_df, top_n=3,
        )
        for it in items:
            for field in RECOMMEND_FIELDS:
                assert field in it, f"缺少契约字段 {field}"
            assert "score" in it and isinstance(it["score"], int)
            assert "reason" in it and isinstance(it["reason"], str) and it["reason"]
            assert "_face_matched" not in it, "内部字段不应泄漏"

    def test_top_n_respected(self, glasses_df):
        for n in (1, 2, 3, 5):
            items, _ = recommend(
                NO_PD_BONUS_PD, 43.0, -3.0, "方形", glasses_df, top_n=n,
            )
            assert len(items) == n
