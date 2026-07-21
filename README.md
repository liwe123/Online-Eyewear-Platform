# 丹智慧眼

> 基于 AI 与大数据的丹阳眼镜产业智能化识别与精准营销平台

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3-green.svg)](https://flask.palletsprojects.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-teal.svg)](https://fastapi.tiangolo.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0-red.svg)](https://pytorch.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

南京师范大学中北学院 · 大学生创新创业训练计划项目

---

## 项目简介

丹阳作为"中国眼镜之都"，眼镜年产量占全国 70% 以上。本项目通过 AI 技术重构眼镜选购体验，实现**拍照 → 脸型识别 → 智能推荐 → 虚拟试戴**的完整闭环。

### 核心功能

- **AI 脸型识别** — CNN 深度学习模型，自动识别圆形脸、方形脸、鹅蛋脸、长方形脸
- **智能推荐** — 结合脸型 + 瞳距 + 角膜曲率 + 近视度数，决策树算法精准匹配眼镜
- **虚拟试戴** — Canvas 实时叠加眼镜效果，无需到店即可预览佩戴效果
- **数据管理** — 用户验光数据、推荐历史、眼镜商品库的统一存储与查询

---

## 技术架构

```
┌─────────────────────────────────────────┐
│           Frontend (端口 5500)            │
│     HTML5 / CSS3 / Bootstrap / JS        │
│      图片上传 · 虚拟试戴 · 结果展示         │
└──────────────────┬──────────────────────┘
                   │ REST API
┌──────────────────▼──────────────────────┐
│           Backend (端口 5000)             │
│        Flask + SQLAlchemy + SQLite        │
│     用户管理 · 推荐记录 · 眼镜数据管理       │
└──────────────────┬──────────────────────┘
                   │ REST API
┌──────────────────▼──────────────────────┐
│         Model API (端口 8000)             │
│    FastAPI + PyTorch + scikit-learn       │
│  脸型识别 (CNN+MTCNN) · 推荐 (决策树)      │
└─────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.10+
- 现代浏览器 (Chrome / Edge / Firefox)

### 1. 克隆项目

```bash
git clone https://github.com/liwe123/Online-Eyewear-Platform.git
cd 丹智慧眼项目
```

### 2. 安装依赖

```bash
# 推荐使用虚拟环境
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### 3. 训练模型（首次使用）

```bash
python model_train.py
```

### 4. 一键启动

**Windows（推荐）**：双击 `start.bat`

**手动启动**：

```bash
# 终端 1：模型 API 服务（端口 8000）
python model_api.py

# 终端 2：后端服务（端口 5000）
python backend/backend_main.py

# 终端 3：前端页面（端口 5500）
cd frontend && python -m http.server 5500
```

### 5. 访问

打开浏览器访问 **http://localhost:5500**

---

## 目录结构

```
丹智慧眼项目/
├── backend/                    # Flask 后端
│   ├── backend_main.py         # 主入口（接口 + 数据模型）
│   ├── config.py               # 配置（数据库、端口）
│   └── requirements.txt        # 后端依赖
├── model/                      # 模型文件（训练产物）
│   ├── face_shape_model.pth    # 脸型识别 CNN 权重
│   ├── recommend_model.pkl     # 推荐模型（决策树）
│   └── label_encoder.pkl       # 标签编码器
├── data/                       # 数据文件
│   ├── glasses_data.csv        # 眼镜商品数据
│   ├── user_eye_data.csv       # 用户验光训练数据
│   └── face/                   # 人脸图片数据集
├── frontend/                   # 前端页面
│   ├── index.html              # 主页（AI试戴入口）
│   ├── detail.html             # 眼镜详情页
│   ├── app.js                  # 前端逻辑
│   └── style.css               # 样式（深墨蓝 + 哑光金）
├── tools/                      # 开发工具
│   ├── test_gradient.py        # 梯度测试
│   └── 眼镜数据爬取代码.py       # 拼多多爬虫
├── docs/                       # 项目文档
│   ├── 大创项目汇报文档.md
│   └── 项目运维文档.md
├── model_api.py                # 模型服务入口
├── model_train.py              # 模型训练脚本
├── model_utils.py              # CNN 模型结构定义
├── requirements.txt            # 完整项目依赖
├── start.bat                   # 一键启动（Windows）
├── stop.bat                    # 一键停止（Windows）
├── .gitignore
└── README.md
```

---

## API 接口

### 后端 (Flask · 端口 5000)

| 方法   | 路径                    | 说明                       |
| ------ | ----------------------- | -------------------------- |
| POST   | `/api/user/submit`      | 上传照片+参数，获取推荐结果 |
| GET    | `/api/glasses/detail`   | 查询眼镜详情              |

### 模型服务 (FastAPI · 端口 8000)

| 方法   | 路径                    | 说明                       |
| ------ | ----------------------- | -------------------------- |
| POST   | `/predict_face_shape`   | 上传图片，返回脸型分类     |
| POST   | `/get_recommendation`   | 传入参数+脸型，返回推荐列表 |
| GET    | `/health`               | 健康检查                   |

在线文档：启动后访问 `http://localhost:8000/docs`

---

## 环境变量

| 变量名           | 默认值                       | 说明             |
| ---------------- | ---------------------------- | ---------------- |
| `MODEL_API_URL`  | `http://localhost:8000`      | 模型 API 地址    |
| `BACKEND_PORT`   | `5000`                       | 后端服务端口     |
| `MODEL_PORT`     | `8000`                       | 模型服务端口     |
| `MODEL_DIR`      | `./model`                    | 模型文件目录     |
| `DATA_DIR`       | `./data`                     | 数据文件目录     |
| `CORS_ORIGINS`   | `http://127.0.0.1:5500,...`  | CORS 允许源      |
| `FLASK_DEBUG`    | `0`                          | Flask 调试模式   |

---

## 常见问题

**Q: 启动后前端无法连接后端？**  
确认三个服务均已启动（模型API:8000 → 后端:5000 → 前端:5500），检查防火墙设置。

**Q: 模型加载失败？**  
确保 `model_train.py` 已执行，`model/` 目录下存在 `.pth` 和 `.pkl` 文件。

**Q: 端口被占用？**  
```bash
netstat -ano | findstr :5000    # 查看占用
taskkill /PID <PID> /F          # 终止进程
```
或通过环境变量修改端口。

---

## 项目展望

- AR 实时试戴（WebRTC + Face Mesh）
- 推荐算法升级（协同过滤 / 深度学习）
- 微信小程序版本
- 企业 SaaS 数据分析服务

---

## 许可证

MIT License

---

> 南京师范大学中北学院 · 丹智慧眼项目组
