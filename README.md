# 税智·心判 — 中小民企财税合规决策支持系统

## 项目简介

「税智·心判」是一个面向中小民企老板的财税合规决策支持系统，核心创新点是将行为经济学/认知心理学引入财税合规领域。系统通过模拟金税四期稽查逻辑识别企业财税风险，同时基于老板的决策行为数据推断其认知偏差类型（掌控欲、损失厌恶、乐观偏差、控制错觉、短期主义、防御心理），并通过沉浸式风险模拟器进行心理干预，引导老板做出合规决策。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Vite 5 + Tailwind CSS 3.4 + Ant Design 5 + Zustand + Recharts |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 |
| 数据库 | PostgreSQL 15 |
| 部署 | Docker + docker-compose |

## 快速启动

### 方式一：Docker 一键部署（推荐）

```bash
# 克隆项目后执行
docker-compose up -d

# 访问前端
open http://localhost:3000

# 访问 API 文档
open http://localhost:8000/docs
```

### 方式二：本地开发

**后端：**

```bash
cd backend

# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量（从模板复制）
cp .env.example .env

# 4. 初始化数据库并导入种子数据
python seed_multi_tenant.py

# 5. 启动服务
uvicorn app.main:app --reload --port 8000
```
> 默认登录账户：`admin_t1` / `a123456`（租户A管理员）
> 开发环境默认使用 SQLite，无需安装 PostgreSQL。

### 方式三：Railway 单容器部署（推荐生产）

项目根目录提供多阶段 `Dockerfile`（前端构建 + FastAPI 运行，前端静态产物由后端同域托管）。Railway 的 Railpack 无法解析 `docker-compose.yml`，因此必须使用 Dockerfile 部署：

1. **创建数据库**：在 Railway 项目内添加 `PostgreSQL` 插件（或任意外部 Postgres）。
2. **部署服务**：连接 GitHub 仓库 `tax-mind`，Railway 自动检测根目录 `Dockerfile` 并构建。
3. **配置环境变量**（服务 Variables）：

   | 变量 | 说明 |
   |------|------|
   | `DATABASE_URL` | 由 Postgres 插件提供，形如 `postgresql://user:pass@host:5432/db`（后端会自动转为 `+asyncpg`） |
   | `JWT_SECRET_KEY` | 随机 32+ 位字符串，缺失则拒绝启动 |
   | `ENCRYPTION_KEY` | Base64 编码的 32 字节密钥（AES-256-GCM），缺失则拒绝启动 |
   | `DEBUG` | 建议 `false` |
   | `LLM_PROVIDER` / `DEEPSEEK_API_KEY` / `QWEN_API_KEY` | 可选，用于合规导航等 AI 能力 |

4. **启动流程**（内置 `start.sh` 自动执行）：等待数据库就绪 → `alembic upgrade head` 迁移 → 幂等导入种子数据 → 启动 uvicorn（监听 Railway 注入的 `PORT`）。
5. **默认账号**：`admin_t1` / `a123456`。

> 域名由 Railway 自动分配（`*.up.railway.app`），如绑定自定义域名无需额外配置，前后端同域部署。

**前端：**

```bash
cd frontend
npm install
npm run dev
```

## 项目结构

```
tax/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/            # API 路由
│   │   ├── core/           # 核心算法
│   │   ├── models/         # SQLAlchemy 数据模型
│   │   ├── schemas/        # Pydantic 数据校验
│   │   ├── services/       # 业务服务层
│   │   ├── utils/          # 工具函数
│   │   ├── config.py       # 配置管理
│   │   ├── database.py     # 数据库连接
│   │   └── main.py         # FastAPI 入口
│   ├── alembic/            # 数据库迁移
│   └── tests/              # 单元测试
├── frontend/               # React 前端
│   ├── src/
│   │   ├── components/     # 通用组件
│   │   │   └── layout/     # 布局组件
│   │   ├── pages/          # 页面组件
│   │   ├── store/          # Zustand 状态管理
│   │   ├── types/          # TypeScript 类型
│   │   └── utils/          # 工具函数
│   └── public/             # 静态资源
├── docker-compose.yml      # 容器编排
└── .env.example            # 环境变量模板
```

## 功能模块

- **数据驾驶舱** — 企业财税概览与关键指标
- **风险地图** — 金税四期视角下的风险可视化
- **心理画像** — 老板认知偏差类型推断
- **风险模拟器** — 沉浸式决策场景模拟与心理干预
- **合规导航** — 合规路径与法规指引
- **整改追踪** — 风险整改任务管理与跟踪
- **报告中心** — 合规分析报告生成
