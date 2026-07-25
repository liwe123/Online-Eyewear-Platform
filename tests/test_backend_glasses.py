# -*- coding: utf-8 -*-
"""后端眼镜列表 / 详情 / 静态图片接口测试。"""
from conftest import TEST_GLASSES

TOTAL = len(TEST_GLASSES)  # 12


class TestGlassesListPagination:
    """GET /api/glasses/list 分页。"""

    def test_first_page(self, client):
        resp = client.get("/api/glasses/list?page=1&page_size=5")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == TOTAL
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["items"]) == 5

    def test_second_page_items_correct(self, client):
        page1 = client.get("/api/glasses/list?page=1&page_size=5").get_json()["data"]
        page2 = client.get("/api/glasses/list?page=2&page_size=5").get_json()["data"]
        assert page2["page"] == 2
        assert len(page2["items"]) == 5
        ids1 = {it["glasses_id"] for it in page1["items"]}
        ids2 = {it["glasses_id"] for it in page2["items"]}
        assert ids1.isdisjoint(ids2), "两页数据不应重复"

    def test_last_page_partial(self, client):
        data = client.get("/api/glasses/list?page=3&page_size=5").get_json()["data"]
        assert len(data["items"]) == TOTAL - 10  # 12 - 10 = 2

    def test_page_size_capped_at_50(self, client):
        data = client.get("/api/glasses/list?page=1&page_size=999").get_json()["data"]
        assert data["page_size"] == 50
        assert len(data["items"]) == TOTAL

    def test_default_pagination(self, client):
        data = client.get("/api/glasses/list").get_json()["data"]
        assert data["page"] == 1
        assert data["page_size"] == 12
        assert len(data["items"]) == TOTAL

    def test_invalid_page_params_400(self, client):
        resp = client.get("/api/glasses/list?page=abc")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == 400


class TestGlassesListFilter:
    """GET /api/glasses/list 筛选。"""

    def test_filter_by_frame_shape(self, client):
        data = client.get("/api/glasses/list?frame_shape=方形&page_size=50").get_json()["data"]
        assert data["total"] == 3  # T004/T005/T011
        assert all(it["frame_shape"] == "方形" for it in data["items"])

    def test_filter_by_material(self, client):
        data = client.get("/api/glasses/list?material=纯钛&page_size=50").get_json()["data"]
        assert data["total"] == 2  # T006/T011
        assert all(it["frame_material"] == "纯钛" for it in data["items"])

    def test_filter_by_keyword_matches_shape(self, client):
        data = client.get("/api/glasses/list?keyword=圆形&page_size=50").get_json()["data"]
        assert data["total"] == 3  # T001/T002/T003

    def test_filter_by_keyword_matches_glasses_id(self, client):
        data = client.get("/api/glasses/list?keyword=T001").get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["glasses_id"] == "T001"

    def test_filter_by_keyword_matches_material(self, client):
        data = client.get("/api/glasses/list?keyword=TR90&page_size=50").get_json()["data"]
        assert data["total"] == 4  # T001/T004/T007/T010
        assert all("TR90" in it["frame_material"] for it in data["items"])

    def test_filter_by_price_range(self, client):
        data = client.get("/api/glasses/list?min_price=300&max_price=500&page_size=50").get_json()["data"]
        assert data["total"] > 0
        assert all(300 <= it["price"] <= 500 for it in data["items"])

    def test_combined_filters(self, client):
        data = client.get(
            "/api/glasses/list?frame_shape=圆形&material=金属&page_size=50"
        ).get_json()["data"]
        assert data["total"] == 1  # 仅 T002
        assert data["items"][0]["glasses_id"] == "T002"


class TestGlassesDetail:
    """GET /api/glasses/detail"""

    def test_detail_exists(self, client):
        resp = client.get("/api/glasses/detail?glasses_id=T001")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["code"] == 200
        data = body["data"]
        assert data["glasses_id"] == "T001"
        assert data["frame_shape"] == "圆形"
        assert "lens_refractive_index" in data
        assert "image_url" in data

    def test_detail_not_found_404(self, client):
        resp = client.get("/api/glasses/detail?glasses_id=NOPE999")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == 404


class TestStaticGlassesImage:
    """GET /static/glasses/<filename>"""

    def test_existing_image_200(self, client):
        # data/glasses_images/ 下真实存在的文件（只读访问）
        resp = client.get("/static/glasses/G001.svg")
        assert resp.status_code == 200

    def test_nonexistent_image_404(self, client):
        resp = client.get("/static/glasses/no_such_file_xyz.svg")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, client):
        # send_from_directory 应阻止路径穿越
        for url in (
            "/static/glasses/..%2F..%2Fbackend%2Fsettings.py",
            "/static/glasses/..%2F..%2Frequirements.txt",
        ):
            resp = client.get(url)
            assert resp.status_code in (400, 404), (
                f"路径穿越应返回 400/404，实际 {resp.status_code}: {url}"
            )
