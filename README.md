# 丹智慧眼

> 基于 AI 与大数据的丹阳眼镜产业智能化识别与精准营销平台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3-green.svg)](https://flask.palletsprojects.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-teal.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/pytest-94%20passed-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

南京师范大学中北学院 · 大学生创新创业训练计划项目

---

## 项目简介

丹阳作为"中国眼镜之都"，眼镜年产量占全国 70% 以上。本项目通过 AI 技术重构眼镜选购体验，实现**拍照 → 脸型识别 → 智能推荐 → 虚拟试戴**的完整闭环。

### 核心功能

- **AI 脸型识别** — MediaPipe Face Mesh 468 个面部关键点几何分析（脸长宽比/下颌宽度/额头比例），规则分类四种脸型，无训练数据依赖；关键点不可用时自动降级
- **智能推荐** — 透明规则引擎：脸型→镜框映射 + 度数硬过滤 + 折射率/瞳距加权打分，每条推荐附带可解释规则说明
- **虚拟试戴** — MediaPipe 关键点定位（双眼距×2.4 宽度、连线中点、连线角度旋转），真实贴合而非居中贴图
- **眼镜商城** — 48 款商品，分页/形状筛选/关键词搜索，购物车（localStorage）
- **用户系统** — JWT 注册登录（24h token），推荐记录关联账号
- **管理后台** — 商品 CRUD + CSV 批量导入（admin 权限）

### 生产级特性

- 认证授权（PyJWT）、接口限流（flask-limiter 10/120 per min）、安全响应头、ProxyFix 真实 IP
- pydantic-settings 统一配置、loguru 结构化日志按天轮转
- pytest 94 个用例全绿、GitHub Actions CI（测试 + Docker 构建）
- Docker 三服务编排、Nginx 反代配置、可选 PostgreSQL

---

## 技术架构

```
┌─────────────────────────────────────────┐
│           Frontend (端口 5500)            │
│   HTML5/Bootstrap/JS + MediaPipe 试戴     │
└──────────────────┬──────────────────────┘
                   │ REST API (JWT)
┌──────────────────▼──────────────────────┐
│           Backend (端口 5000)             │
│  Flask + SQLAlchemy + SQLite/PostgreSQL   │
│  认证/限流/商城/购物车/管理后台/静态图      │
└──────────────────┬──────────────────────┘
                   │ REST API
┌──────────────────▼──────────────────────┐
│         Model API (端口 8000)             │
│     FastAPI + MediaPipe + OpenCV          │
│  几何脸型分类 + 规则推荐引擎（可解释）       │
└─────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.10+（Docker 部署则只需 Docker）

### 1. 克隆项目

```bash
git clone https://github.com/liwe123/Online-Eyewear-Platform.git
cd Online-Eyewear-Platform
```

### 2. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### 3. 一键启动

**Windows（推荐）**：双击 `start.bat`

**手动启动**：

```bash
python model_api.py              # 终端1：模型API (8000)
python backend/backend_main.py   # 终端2：后端 (5000)
cd frontend && python -m http.server 5500   # 终端3：前端 (5500)
```

### 4. 访问

打开浏览器访问 **http://localhost:5500**

> 默认管理员账号 `admin` / `admin123`（**生产部署必须经环境变量修改**，见 .env.example）

### Docker 部署

```bash
cp .env.example .env   # 修改 SECRET_KEY / ADMIN_PASSWORD
docker compose up -d --build
# 含 PostgreSQL：docker compose --profile prod up -d --build
```

---

## 目录结构

```
丹智慧眼项目/
├── backend/                    # Flask 后端
│   ├── backend_main.py         # 应用装配（路由/限流/安全头/日志）
│   ├── settings.py             # pydantic-settings 配置
│   ├── config.py               # 兼容层：复用 settings 的旧 config 导出
│   ├── models.py               # SQLAlchemy 模型（含 Account 账号表）
│   ├── auth.py                 # JWT 认证 + 装饰器
│   └── admin.py                # 管理后台 CRUD + CSV 导入
├── model_api.py                # 模型服务入口（FastAPI）
├── face_geometry.py            # 几何脸型分类器（MediaPipe 关键点）
├── recommend_rules.py          # 规则推荐引擎（可解释）
├── model_utils.py              # 历史 CNN 结构（已弃用，保留兼容）
├── frontend/                   # 前端
│   ├── index.html / detail.html
│   ├── app.js                  # 主逻辑（表单/试戴/商城）
│   ├── common.js               # 共享工具（API/转义/占位图）
│   ├── cart.js / auth.js       # 购物车 / 登录注册模块
│   └── style.css
├── data/                       # 数据（CSV + SVG 商品图 + SQLite）
├── model/                      # 历史模型文件（已弃用）
├── tests/                      # pytest 套件（94 用例）
├── tools/                      # 数据生成器 / 爬虫 / 调试脚本
├── docs/                       # 项目文档
├── Dockerfile.backend / Dockerfile.frontend / Dockerfile.model
├── docker-compose.yml          # 三服务编排（prod profile 含 Postgres）
├── nginx/nginx.conf            # 手动部署反代参考
├── .github/workflows/ci.yml    # CI：pytest + docker build
├── requirements.txt            # 完整依赖
├── requirements-model.txt      # 模型服务 Docker 构建依赖
├── .env.example                # 环境变量模板
├── start.bat / stop.bat        # Windows 一键启停
└── README.md
```

---

## API 接口

### 后端 (Flask · 端口 5000)

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/api/auth/register` | 注册 | 匿名（10/min 限流） |
| POST | `/api/auth/login` | 登录，返回 JWT | 匿名（10/min 限流） |
| POST | `/api/user/submit` | 上传照片+验光参数，获取推荐 | 匿名/可选 token（10/min） |
| GET | `/api/glasses/list` | 商品列表（分页/筛选/搜索） | 匿名 |
| GET | `/api/glasses/detail` | 商品详情 | 匿名 |
| GET | `/static/glasses/<file>` | 商品图片 | 匿名 |
| POST | `/api/admin/glasses` | 新建商品 | admin |
| PUT | `/api/admin/glasses/<id>` | 更新商品 | admin |
| DELETE | `/api/admin/glasses/<id>` | 删除商品 | admin |
| POST | `/api/admin/glasses/import` | CSV 批量导入 | admin |

### 模型服务 (FastAPI · 端口 8000)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/predict_face_shape` | 上传图片，返回中文脸型 + 几何指标 |
| POST | `/get_recommendation` | 验光参数+脸型，返回 Top-3 推荐 + 命中规则 |
| GET | `/health` | 健康检查（含降级状态） |

在线文档：启动后访问 `http://localhost:8000/docs`

---

## 环境变量

复制 `.env.example` 为 `.env` 修改。关键项：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SECRET_KEY` | （dev 默认值） | **生产必改**，JWT 签名密钥 |
| `ADMIN_PASSWORD` | `admin123` | **生产必改**，admin 初始密码 |
| `DATABASE_URL` | `sqlite:///data/backend.db` | 生产切 `postgresql://...` |
| `MODEL_API_URL` | `http://localhost:8000` | 模型 API 地址 |
| `CORS_ORIGINS` | 本地 5500 | CORS 白名单（逗号分隔） |

---

## 测试

```bash
python -m pytest tests/ -v
# 94 个用例：后端认证/提交/列表/admin/限流/安全头 + 几何分类 + 规则推荐 + 模型API
```

---

## 已知限制

1. **商品数据双源**：推荐引擎读 `data/glasses_data.csv`，商城/后台读写 SQLite。Admin 增删商品后推荐不会同步（重启模型服务可刷新）。后续可将模型服务改为查询后端接口统一数据源。
2. **限流为内存存储**：gunicorn 多 worker 下各进程独立计数，严格限流需换 Redis 存储。
3. **脸型分类阈值为人工调参**：基于几何比例的规则分类在大表情/遮挡/侧脸场景会降级为默认脸型，不影响主流程。
4. **compose 局域网访问**：以 IP 方式访问前端时，需在 HTML 设置 `data-api-base` 指向后端地址（nginx 反代部署无此问题）。

---

## 项目展望

- AR 实时试戴（WebRTC 摄像头流 + Face Mesh）
- 推荐算法升级（协同过滤 / 用户行为反馈学习）
- 真实商品数据对接丹阳企业
- 微信小程序版本

---

## 许可证

MIT License

---

> 南京师范大学中北学院 · 丹智慧眼项目组
