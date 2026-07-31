# -*- coding: utf-8 -*-
"""端到端集成测试：注册 → 登录 → 携带 token 提交 → 落库关联 → 列表查询。

独立成文件以复用 conftest 的 client / fake_model_post 夹具，
同时不影响 test_backend_submit.py 中 TestRateLimit 类的执行顺序。
"""
from conftest import MOCK_FACE_SHAPE, backend_main, make_upload_file
from models import Account, RecommendRecord, User, db

FORM = {
    "pupil_distance": "62",
    "corneal_curvature": "43",
    "myopia_degree": "-3.5",
}


def test_full_flow_register_login_submit_query(client, png_bytes):
    """完整业务闭环，且用户提交结果与登录账号正确关联。"""
    # 1. 注册
    resp = client.post("/api/auth/register", json={
        "username": "flowuser", "password": "flow123456",
    })
    assert resp.status_code == 200, f"注册失败: {resp.get_json()}"

    # 2. 登录获取 token
    resp = client.post("/api/auth/login", json={
        "username": "flowuser", "password": "flow123456",
    })
    assert resp.status_code == 200, f"登录失败: {resp.get_json()}"
    token = resp.get_json()["data"]["token"]
    assert token, "应返回非空 token"
    headers = {"Authorization": f"Bearer {token}"}

    # 3. 携带 token 提交照片与眼部参数
    data = dict(FORM)
    data["image"] = make_upload_file(png_bytes)
    resp = client.post("/api/user/submit", data=data,
                       content_type="multipart/form-data", headers=headers)
    assert resp.status_code == 200, f"提交失败: {resp.get_json()}"
    body = resp.get_json()
    assert body["code"] == 200
    user_id = body["data"]["user_id"]
    assert body["data"]["face_shape"] == MOCK_FACE_SHAPE

    # 4. 落库验证：User 与 RecommendRecord 存在且与账号关联
    with backend_main.app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        assert user.pupil_distance == 62.0
        assert user.corneal_curvature == 43.0
        assert user.myopia_degree == -3.5
        account = Account.query.filter_by(username="flowuser").first()
        assert account is not None
        assert user.account_id == account.id, "携带 token 提交应关联账号"

        record = RecommendRecord.query.filter_by(user_id=user.id).first()
        assert record is not None, "应生成推荐记录"
        assert record.face_shape == MOCK_FACE_SHAPE
        assert record.glasses_ids, "推荐记录应包含眼镜 ID 列表"

    # 5. 列表接口可用
    resp = client.get("/api/glasses/list?page=1&page_size=5")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert len(data["items"]) == 5
    assert data["total"] >= 5
