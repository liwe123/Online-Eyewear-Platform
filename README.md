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

丹阳作为"中国眼镜之都"，眼镜年产量占全国 70% 以上。本项目通过 AI 技术重构眼镜选购体验，实现**拍照 -> 脸型识别 -> 智能推荐 -> 选购**的完整闭环，面向丹阳眼镜产业的线上选型与精准营销场景。

### 核心功能

- **AI 脸型识别** - MediaPipe FaceMesh 468 个面部关键点几何分析（脸长宽比 / 下颌宽比 / 额头宽比 / 下颌角 / 三庭比例 / 五眼比例等 9 项指标），规则分类四种脸型（长方形 / 圆形 / 方形 / 鹅蛋脸），零训练数据依赖；MediaPipe 不可用时自动降级为 MTCNN/Haar 人脸框粗分类，主流程不中断
- **AI 面部分析报告** - 468 特征点大字指标 + 中文判定依据 + 上传照片点云叠加，可视化呈现"AI 如何看脸"
- **智能推荐** - 透明规则引擎：脸型 -> 镜框映射 + 度数硬过滤 + 折射率/瞳距加权打分，每条推荐附带可解释规则说明（"为什么推荐这副眼镜"）；度数输入兼容屈光度（-3.00）与"度数"（300 自动转 -3.00），0 度跳过过滤不致空结果
- **眼镜商城** - 商品列表分页 / 形状筛选 / 关键词搜索，购物车（localStorage 持久化），商品详情页
- **用户系统** - JWT 注册登录（24h token），推荐记录关联账号
- **管理后台** - 商品 CRUD + CSV 批量导入（admin 权限）

### 生产级特性

- 认证授权（PyJWT）、接口限流（flask-limiter 10/120 per min）、安全响应头、ProxyFix 真实 IP
- pydantic-settings 统一配置、loguru 结构化日志按天轮转
- pytest 94 个用例全绿、GitHub Actions CI（测试 + Docker 镜像构建）
- Docker 三服务编排、Nginx 反代配置、可选 PostgreSQL（prod profile）

---

## 项目亮点：原创性与核心优势

> 以下从「原创性设计 / 核心优势 / 项目特点」三个维度说明本项目相较同类作品的价值，便于答辩、评审与对外展示。

### 原创性设计

1. **几何规则脸型分类（零训练数据依赖）** - 弃用需大量标注数据的 CNN 训练方案（历史 `face_shape_model.pth` 为噪声训练产物，已归档弃用），改用 MediaPipe FaceMesh 468 个面部关键点的几何比例（脸长宽比 / 下颌宽比 / 额头宽比 / 下颌角 / 三庭五眼）做规则分类。整套分类阈值与「脸型 -> 镜框」映射表为项目自研，无需任何标注数据集、无 GPU 即可运行。
2. **可解释规则推荐引擎** - 弃用伪标签决策树（`recommend_model.pkl` 为 4KB 占位模型，已弃用），自研「脸型 -> 镜框映射 + 度数硬过滤 + 折射率 / 瞳距加权打分」规则引擎。每条推荐都返回**命中的具体规则**（如"脸型命中 +40 / 高度近视优选 1.74 折射率 +20 / 瞳距匹配优秀 +10"），用户与商家都能看懂「为什么推荐这副眼镜」，是面向导购场景的透明 AI。
3. **AI 面部分析报告** - 不仅给出脸型结论，还把 468 个关键点提取的 9 项几何测量（脸长宽比 / 下颌宽比 / 额头宽比 / 下颌角 / 三庭比例 / 五眼比例 / 鼻长比 / 唇宽比 / 脸眼比）以中文指标网格 + 判定依据文字 + 上传照片点云叠加的方式可视化呈现，让用户直观看到"AI 如何分析我的脸"。
4. **拍照 -> 识别 -> 分析 -> 推荐 -> 选购全闭环** - 多数同类学生作品只做单点（仅脸型分类或仅推荐），本项目打通从用户上传照片到下单的完整链路，且前端 / 后端 / 模型服务三层解耦、可独立演进。

### 核心优势

- **开箱即用，无数据门槛** - 不依赖标注数据集与 GPU，克隆即可运行；缺图或关键点不可用时自动降级为默认脸型，主流程不中断。
- **生产级工程质量** - Docker 三服务编排、GitHub Actions CI（测试 + 镜像构建）、94 个 pytest 用例全绿、JWT 认证、接口限流、安全响应头、loguru 按天轮转日志--远超一般课程 / 大创 demo 的「单脚本跑通」水准。
- **可解释、可审计** - 推荐结果可追溯每条规则与分值，便于商家调整商品策略，也利于答辩中讲清「AI 如何决策」。
- **隐私风险可控** - 人脸图片仅在单次请求生命周期内做几何分析、不落库存储生物特征，相对降低了《个人信息保护法》对生物识别信息的合规负担。
- **工程分层清晰** - 前端（原生 HTML/JS）/ 后端（Flask）/ 模型服务（FastAPI）职责分离，模型服务可独立升级或替换而不影响业务层。

### 项目特点

- **锚定真实产业场景** - 面向「中国眼镜之都」丹阳的眼镜零售选型痛点，而非玩具 demo。
- **透明 AI 取向** - 在精度与可解释性之间优先可解释性，契合营销 / 导购对「说得清」的诉求。
- **多技术栈整合** - Flask + FastAPI + MediaPipe + OpenCV + SQLAlchemy + Nginx 协同，覆盖 CV、Web、工程化全链路。
- **大创落地导向** - 大学生创新创业训练计划项目，设计兼顾技术深度与现场可演示性。

---

## 技术架构

```
┌─────────────────────────────────────────┐
│           Frontend (端口 5500)            │
│   HTML5 / Bootstrap / 原生 JS             │
│   AI 分析报告 · 商城 · 购物车 · 登录       │
└──────────────────┬──────────────────────┘
                   │ REST API (JWT)
┌──────────────────▼──────────────────────┐
│           Backend (端口 5000)             │
│  Flask + SQLAlchemy + SQLite/PostgreSQL   │
│  认证 / 限流 / 商城 / 购物车 / 管理后台    │
│  静态眼镜图服务 / 推荐记录                │
└──────────────────┬──────────────────────┘
                   │ REST API
┌──────────────────▼──────────────────────┐
│         Model API (端口 8000)             │
│     FastAPI + MediaPipe + OpenCV          │
│  几何脸型分类(468点) + 规则推荐引擎        │
│  （可解释，含 9 项面部几何指标）           │
└─────────────────────────────────────────┘
```

数据流：用户上传照片 + 验光参数 -> 后端转发 -> 模型服务做脸型识别与推荐 -> 后端落库推荐记录并返回前端 -> 前端展示 AI 分析报告 + Top-N 推荐商品。

---

## 快速开始

### 环境要求

- Python 3.10+（Docker 部署则只需 Docker）
- Windows / macOS / Linux 均可

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

> MediaPipe 推荐安装 `mediapipe==0.10.14` 以启用 468 点几何脸型识别；缺失时模型服务自动降级为 OpenCV Haar 粗分类（仍可用，精度低）。

### 3. 一键启动

**Windows（推荐）**：双击 `start.bat`

`start.bat` 会自动处理一个 Windows 特有的坑：项目路径含中文（如 `D:\丹智慧眼项目\...`）时，MediaPipe 的 C++ 层按 ANSI 解析路径会失败（Python 能看到文件、C++ 打不开 -> `FileNotFoundError`）。脚本检测到非 ASCII 路径时，会在系统盘建一个 ASCII 路径的目录联接（junction）`%SystemDrive%\dzhy_venv` 指向项目 `.venv`，用该联接里的 python 启动，零复制、不污染系统。

**手动启动**：

```bash
python model_api.py              # 终端1：模型API (8000)
python backend/backend_main.py   # 终端2：后端 (5000)
cd frontend && python -m http.server 5500   # 终端3：前端 (5500)
```

> 注意：必须用项目 `.venv` 的 Python 启动，不要用系统 PATH 里的 Python（可能缺依赖导致服务闪退）。

### 4. 访问

打开浏览器访问 **http://localhost:5500**

- 前端：http://localhost:5500
- 后端 API：http://localhost:5000
- 模型 API 文档：http://localhost:8000/docs

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
│   ├── models.py               # SQLAlchemy 模型（Account/User/Glasses/RecommendRecord）
│   ├── auth.py                 # JWT 认证 + 装饰器
│   └── admin.py                # 管理后台 CRUD + CSV 导入
├── model_api.py                # 模型服务入口（FastAPI）
├── face_geometry.py            # 几何脸型分类器（MediaPipe 468 关键点 + 9 项指标）
├── recommend_rules.py          # 规则推荐引擎（可解释，脸型映射+度数过滤+折射率/瞳距打分）
├── model_utils.py              # 历史 CNN 结构（已弃用，保留兼容）
├── model_train.py              # 历史 CNN 训练脚本（已弃用，保留参考）
├── frontend/                   # 前端
│   ├── index.html              # 首页（AI 分析 + 推荐 + 商城入口）
│   ├── detail.html             # 商品详情页
│   ├── app.js                  # 主逻辑（表单/分析报告/商城）
│   ├── common.js               # 共享工具（API/转义/占位图）
│   ├── cart.js / auth.js       # 购物车 / 登录注册模块
│   └── style.css
├── data/                       # 数据
│   ├── glasses_data.csv        # 商品库（推荐引擎读源）
│   ├── backend.db              # SQLite（商城/后台读写）
│   ├── glasses_images/         # 商品图片（jpg 真实图 + svg 占位图）
│   ├── glasses_images_manifest.csv  # 图片署名清单（Wikimedia Commons CC 来源）
│   ├── glasses_attribution.csv # 完整署名清单（合规用）
│   └── glasses_labels.csv      # 框型人工标注
├── model/                      # 历史模型文件（已弃用，保留兼容）
├── tests/                      # pytest 套件（94 用例）
│   ├── test_backend_auth.py    # 认证（8）
│   ├── test_backend_admin.py   # 管理后台（14）
│   ├── test_backend_glasses.py # 商品/列表（18）
│   ├── test_backend_submit.py  # 提交推荐（10）
│   ├── test_face_geometry.py   # 几何分类（6）
│   ├── test_recommend_rules.py # 规则推荐（14）
│   ├── test_model_api.py       # 模型 API（9）
│   ├── conftest.py             # fixtures
│   ├── assets/                 # 测试图片
│   └── real_glasses_template.csv  # 真实数据导入模板
├── tools/                      # 数据工具
│   ├── generate_glasses_data.py         # 商品数据生成器 + SVG 占位图（make_svg）
│   ├── import_real_glasses.py            # 真实商品数据导入（灵活列映射+归一+校验）
│   ├── fetch_real_glasses_images.py      # Wikimedia Commons 真实眼镜图抓取
│   ├── add_specific_commons_files.py     # 补充特定 Commons 文件
│   ├── make_contact_sheets.py            # 拼接标注用网格图
│   ├── rebuild_glasses_with_real_images.py  # 按标注+manifest 重建 CSV
│   └── 眼镜数据爬取代码.py                # 早期爬虫参考
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
| POST | `/api/user/submit` | 上传照片+验光参数，获取脸型分析+推荐 | 匿名/可选 token（10/min） |
| GET | `/api/glasses/list` | 商品列表（分页/筛选/搜索） | 匿名 |
| GET | `/api/glasses/detail` | 商品详情 | 匿名 |
| GET | `/static/glasses/<file>` | 商品图片静态服务 | 匿名 |
| POST | `/api/admin/glasses` | 新建商品 | admin |
| PUT | `/api/admin/glasses/<id>` | 更新商品 | admin |
| DELETE | `/api/admin/glasses/<id>` | 删除商品 | admin |
| POST | `/api/admin/glasses/import` | CSV 批量导入 | admin |

### 模型服务 (FastAPI · 端口 8000)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/predict_face_shape` | 上传图片，返回中文脸型 + 9 项几何指标 + 468 关键点 + 判定依据 |
| POST | `/get_recommendation` | 验光参数+脸型，返回 Top-3 推荐 + 命中规则 + 推荐理由 |
| GET | `/health` | 健康检查（含 mediapipe 可用性 + 商品库数量） |

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

## 真实商品数据导入

项目提供完整的真实商品数据导入管线，支持 CSV / Excel 源文件：

```bash
python tools/import_real_glasses.py <源文件.csv|.xlsx> [--resync] [--no-svg]
```

- 灵活列映射：中英文表头 + 别名自动识别（如"价格"/"price"/"售价"均映射到 `price`）
- 框型归一：飞行员 -> 鹅蛋形、椭圆 -> 鹅蛋形、蝴蝶 -> 猫眼形 等，统一到 6 种标准框型
- 度数/折射率/价格校验归一，缺图片自动生成 SVG 占位图
- `--resync`：清空 SQLite 眼镜表，重启后端即按新 CSV 重新种子
- 导入后**必须同时重启后端(5000)和模型服务(8000)**（模型服务商品库在内存、基于 CSV，不重启仍是旧数据）
- 后验校验：导入后检查图片文件是否存在，缺失会 warning 列出

模板见 `tests/real_glasses_template.csv`。

---

## 已知限制

1. **商品数据双源**：推荐引擎读 `data/glasses_data.csv`，商城/后台读写 SQLite。Admin 增删商品后推荐不会同步（重启模型服务可刷新）。后续可将模型服务改为查询后端接口统一数据源。
2. **限流为内存存储**：gunicorn 多 worker 下各进程独立计数，严格限流需换 Redis 存储。
3. **脸型分类阈值为人工调参**：基于几何比例的规则分类在大表情/遮挡/侧脸场景会降级为默认脸型，不影响主流程。
4. **compose 局域网访问**：以 IP 方式访问前端时，需在 HTML 设置 `data-api-base` 指向后端地址（nginx 反代部署无此问题）。
5. **商品图片来源**：当前部分商品图来自 Wikimedia Commons（CC BY / CC0 / Public Domain），`data/glasses_attribution.csv` 记录完整署名清单。**公开商用前需替换为自己授权的商品图，或保留署名清单合规展示**。

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
