# -*- coding: utf-8 -*-
"""后端管理接口测试：权限控制、CRUD、CSV 导入。"""
import io

from admin import MAX_CSV_SIZE
from models import Glasses

# 与 backend/admin.py 中 CSV_REQUIRED_COLUMNS 一致的列头
CSV_HEADER = ("glasses_id,frame_shape,frame_size,frame_material,lens_degree_min,"
              "lens_degree_max,lens_refractive_index,price,image_url")


def _new_glasses_payload(glasses_id="NEW01", price=666.0):
    return {
        "glasses_id": glasses_id,
        "frame_shape": "圆形",
        "frame_size": "50-20-140",
        "frame_material": "TR90",
        "lens_degree_min": -6.0,
        "lens_degree_max": 0.0,
        "lens_refractive_index": 1.60,
        "price": price,
        "image_url": "/static/glasses/NEW01.svg",
    }


def _csv_upload(csv_text: str, filename: str = "import.csv"):
    return (io.BytesIO(csv_text.encode("utf-8")), filename, "text/csv")


class TestAdminAuth:
    """权限控制：401 / 403。"""

    def test_no_token_401(self, client):
        assert client.post("/api/admin/glasses", json=_new_glasses_payload()).status_code == 401
        assert client.put("/api/admin/glasses/T001", json={"price": 1}).status_code == 401
        assert client.delete("/api/admin/glasses/T001").status_code == 401

    def test_invalid_token_401(self, client):
        headers = {"Authorization": "Bearer not.a.valid.token"}
        resp = client.post("/api/admin/glasses", json=_new_glasses_payload(), headers=headers)
        assert resp.status_code == 401

    def test_normal_user_token_403(self, client, user_headers):
        resp = client.post("/api/admin/glasses", json=_new_glasses_payload(), headers=user_headers)
        assert resp.status_code == 403
        body = resp.get_json()
        assert body["code"] == 403
        assert "管理员" in body["msg"]


class TestAdminCrud:
    """admin token 下的 CRUD 全流程。"""

    def test_full_crud_flow(self, client, admin_headers):
        # 创建
        resp = client.post("/api/admin/glasses", json=_new_glasses_payload(), headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["glasses_id"] == "NEW01"
        assert data["price"] == 666.0

        # 重名创建 → 400
        resp = client.post("/api/admin/glasses", json=_new_glasses_payload(), headers=admin_headers)
        assert resp.status_code == 400
        assert "已存在" in resp.get_json()["msg"]

        # 更新价格
        resp = client.put("/api/admin/glasses/NEW01", json={"price": 888.0}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["price"] == 888.0

        # 详情验证更新生效
        resp = client.get("/api/glasses/detail?glasses_id=NEW01")
        assert resp.get_json()["data"]["price"] == 888.0

        # 删除
        resp = client.delete("/api/admin/glasses/NEW01", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["msg"] == "删除成功"

        # 删除后详情 404
        resp = client.get("/api/glasses/detail?glasses_id=NEW01")
        assert resp.status_code == 404

    def test_create_missing_fields_400(self, client, admin_headers):
        payload = _new_glasses_payload("NEW02")
        del payload["frame_shape"]
        del payload["price"]
        resp = client.post("/api/admin/glasses", json=payload, headers=admin_headers)
        assert resp.status_code == 400
        assert "缺少必填字段" in resp.get_json()["msg"]

    def test_create_missing_glasses_id_400(self, client, admin_headers):
        payload = _new_glasses_payload("")
        resp = client.post("/api/admin/glasses", json=payload, headers=admin_headers)
        assert resp.status_code == 400

    def test_update_nonexistent_404(self, client, admin_headers):
        resp = client.put("/api/admin/glasses/GHOST99", json={"price": 1}, headers=admin_headers)
        assert resp.status_code == 404

    def test_update_invalid_field_type_400(self, client, admin_headers):
        resp = client.put("/api/admin/glasses/T001", json={"price": "abc"}, headers=admin_headers)
        assert resp.status_code == 400
        assert "非法" in resp.get_json()["msg"]

    def test_update_null_string_field_not_written(self, client, admin_headers):
        """null 字符串字段应被跳过，不得写入 str(None) 的 "None" 垃圾。"""
        resp = client.put("/api/admin/glasses/T001", json={"frame_shape": None},
                          headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["frame_shape"] == "圆形"  # T001 原始值保持不变
        assert data["frame_shape"] != "None"

    def test_delete_nonexistent_404(self, client, admin_headers):
        resp = client.delete("/api/admin/glasses/GHOST99", headers=admin_headers)
        assert resp.status_code == 404


class TestAdminCsvImport:
    """POST /api/admin/glasses/import"""

    def test_import_success_with_upsert(self, client, admin_headers):
        from conftest import backend_main
        with backend_main.app.app_context():
            before = Glasses.query.count()

        # 两行新增 + 一行已有 glasses_id（T001，价格 399 → 999 走 upsert 更新）
        csv_text = (
            CSV_HEADER + "\n"
            "CSV01,圆形,50-20-140,TR90,-6,0,1.60,399,/static/glasses/CSV01.svg\n"
            "CSV02,方形,54-16-140,金属,-6,0,1.56,299,/static/glasses/CSV02.svg\n"
            "T001,圆形,50-20-140,TR90,-6,0,1.60,999,/static/glasses/T001.svg\n"
        )
        resp = client.post(
            "/api/admin/glasses/import",
            data={"file": _csv_upload(csv_text)},
            content_type="multipart/form-data",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["code"] == 200
        assert body["data"]["imported"] == 3

        with backend_main.app.app_context():
            after = Glasses.query.count()
            assert after == before + 2, "upsert 不应重复插入已有 glasses_id"
            t001 = Glasses.query.filter_by(glasses_id="T001").first()
            assert t001.price == 999.0, "upsert 应更新已有记录"

    def test_import_wrong_header_400(self, client, admin_headers):
        csv_text = "col_a,col_b,col_c\n1,2,3\n"
        resp = client.post(
            "/api/admin/glasses/import",
            data={"file": _csv_upload(csv_text)},
            content_type="multipart/form-data",
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "列头" in resp.get_json()["msg"]

    def test_import_no_file_400(self, client, admin_headers):
        resp = client.post(
            "/api/admin/glasses/import", data={}, headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_import_row_missing_glasses_id_400(self, client, admin_headers):
        csv_text = (
            CSV_HEADER + "\n"
            "CSV10,圆形,50-20-140,TR90,-6,0,1.60,399,/a.svg\n"
            ",方形,54-16-140,金属,-6,0,1.56,299,/b.svg\n"
        )
        resp = client.post(
            "/api/admin/glasses/import",
            data={"file": _csv_upload(csv_text)},
            content_type="multipart/form-data",
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "glasses_id" in resp.get_json()["msg"]

    def test_import_gbk_encoding_success(self, client, admin_headers):
        csv_text = (
            CSV_HEADER + "\n"
            "GBK01,圆形,50-20-140,TR90,-6,0,1.60,399,/static/glasses/GBK01.svg\n"
        )
        resp = client.post(
            "/api/admin/glasses/import",
            data={"file": (io.BytesIO(csv_text.encode("gbk")), "gbk.csv", "text/csv")},
            content_type="multipart/form-data",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["imported"] == 1

    def test_import_reordered_columns_success(self, client, admin_headers):
        """列头顺序不同也应导入成功（按字段名而非列位置匹配）。"""
        row = {
            "glasses_id": "ORD1", "frame_shape": "圆形", "frame_size": "50-20-140",
            "frame_material": "TR90", "lens_degree_min": -6, "lens_degree_max": 0,
            "lens_refractive_index": 1.60, "price": 399,
            "image_url": "/static/glasses/ORD1.svg",
        }
        cols = CSV_HEADER.split(",")
        reordered = [cols[i] for i in (8, 4, 5, 6, 7, 0, 1, 2, 3)]  # 打乱顺序
        csv_text = ",".join(reordered) + "\n" + \
            ",".join(str(row[c]) for c in reordered) + "\n"
        resp = client.post(
            "/api/admin/glasses/import",
            data={"file": _csv_upload(csv_text)},
            content_type="multipart/form-data",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["imported"] == 1
        # 按字段名正确落库
        detail = client.get("/api/glasses/detail?glasses_id=ORD1")
        assert detail.status_code == 200
        data = detail.get_json()["data"]
        assert data["frame_shape"] == "圆形"
        assert data["price"] == 399.0

    def test_import_file_too_large_400(self, client, admin_headers):
        """CSV 文件超过 MAX_CSV_SIZE(5MB) → 400「CSV 文件过大」。"""
        big = io.BytesIO(b"a" * (MAX_CSV_SIZE + 1))
        resp = client.post(
            "/api/admin/glasses/import",
            data={"file": (big, "big.csv", "text/csv")},
            content_type="multipart/form-data",
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == 400
        assert "过大" in body["msg"]
