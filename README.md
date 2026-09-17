# 蒙牛全产业链 AI 内生合规决策大脑

> **数智全链 · 价值孪生**（答辩终稿）

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![React](https://img.shields.io/badge/React-18%2B-61dafb)
![Tests](https://img.shields.io/badge/Backend%20Tests-387%20passed-brightgreen)
![Tests](https://img.shields.io/badge/Frontend%20Tests-56%20passed-brightgreen)

## 项目简介

本项目是「蒙牛AI创新赛」参赛项目的工程实现，以高壁垒财税核算为确定性切口，全面贯穿「牧场—工厂—物流—营销—海外」全产业链，突破传统财务边界，将物料流动精准映射为法定价值流。

系统的架构主线是**双层解耦 + 审计证据链**：

> **LLM explains. Skill calculates. Rule Engine governs. Evidence Chain proves.**

- **Agent 沟通层**：大模型只负责自然语言理解、沟通、任务编排与报告草拟，**不做任何数值判定**；
- **Skill 确定性层**：税额、评分等一切数值由版本化的确定性规则引擎计算，输入输出可解释、可追溯；
- **两条铁律**：① 法规引用必须携带文号与生效日期元数据；② 任何计算结果不得由大模型「心算」产出；
- **审计证据链**：每个数值携带计算 ID 与参数快照，可回答「为什么算出这个数字、依据哪个法规、当时法规是否有效、谁复核后改了什么」。

> 方案总纲见 [`docs/蒙牛AI创新_方案_迭代版V4.md`](docs/蒙牛AI创新_方案_迭代版V4.md)，
> 开源组件选型/集成/踩坑记录见 [`docs/OPEN_SOURCE_INTEGRATION.md`](docs/OPEN_SOURCE_INTEGRATION.md)。

## 核心引擎（与代码一一对应）

| 引擎 | 代码位置 | 说明 |
|------|----------|------|
| **Rule ID 法规治理矩阵** | `backend/app/core/rule_governance/` | 六级法规层级（宪法/法律/行政法规/部门规章/规范性文件/操作口径）+ 生效/废止时间窗 + `Human verified`/`Pending` 复核闸门；内置 17 条规则，杜绝引用已废止口径（如 2011 年第 38 号液体乳税率公告，已被 2026 年第 18 号公告清理） |
| **乳业农产品核定扣除引擎** | `backend/app/core/deemed_deduction/` | 依据财税〔2012〕38 号（经 2026 年第 10 号公告延续至 2027 年底）的进项税额核定扣除计算；**全部金额运算使用 `Decimal`**，杜绝浮点误差 |
| **四流稽核** | `backend/app/core/four_flow_match.py` | 合同流/发票流/资金流/货物流交叉比对，Jaccard + rapidfuzz 双分数对照（rapidfuzz 为受控增强层，默认评分路径不变） |
| **合规调整分 + 信用否决** | `backend/app/core/compliance_adjustment.py`、`credit_veto.py` | 风险评分之上的合规调整与一票否决机制 |
| **审计证据链** | `backend/app/services/audit_log.py` + `alembic/versions/009_add_audit_calc_snapshot.py` | `calc_id` = SHA-256 规范化 JSON 确定性指纹 + 参数快照，不依赖墙钟时间，保证同输入必同指纹 |

> 行为经济学方法仅用于合规微任务与干预文案设计（方案 V4 §5），**不做侵入式心理画像**（V4 §5.4 明确边界）。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript 5.6 + Vite 5 + Tailwind CSS 3.4 + Ant Design 5 + Zustand 5 + Recharts 2 |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + Alembic |
| 规则/计算 | zen-engine 2.x（Rule ID 治理矩阵）+ rapidfuzz（品名受控模糊匹配）+ pdfplumber（同期资料 PDF 解析） |
| 数据库 | PostgreSQL 15（开发环境默认 SQLite，无需安装） |
| 部署 | Docker + docker-compose / Railway 单容器（多阶段 Dockerfile） |

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

**前端：**

```bash
cd frontend
npm install
npm run dev
```

### 方式三：Railway 单容器部署（推荐生产）

项目根目录提供多阶段 `Dockerfile`（前端构建 + FastAPI 运行，前端静态产物由后端同域托管）。Railway 的 Railpack 无法解析 `docker-compose.yml`，因此必须使用 Dockerfile 部署：

1. **创建数据库**：在 Railway 项目内添加 `PostgreSQL` 插件（或任意外部 Postgres）。
2. **部署服务**：连接本 GitHub 仓库，Railway 自动检测根目录 `Dockerfile` 并构建。
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

## 项目结构

```
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/                # API 路由（auth / enterprises / risk_scan / simulation /
│   │   │                       #   compliance / compliance_check / remediation / reports /
│   │   │                       #   upload / risk_config / ai_assistant，统一挂载 /api/v1）
│   │   ├── core/               # 核心算法与引擎
│   │   │   ├── rule_governance/    # Rule ID 法规治理矩阵（registry + executor + 规则库）
│   │   │   ├── deemed_deduction/   # 乳业农产品核定扣除引擎（全 Decimal 金额运算）
│   │   │   ├── four_flow_match.py  # 四流稽核（Jaccard + rapidfuzz 双分数对照）
│   │   │   ├── compliance_adjustment.py / credit_veto.py
│   │   │   ├── risk_engine.py / tax_risk_engine.py / penalty_calculator.py
│   │   │   ├── simulation_engine.py / intervention.py
│   │   │   └── security.py / encryption.py / pdf_generator.py
│   │   ├── models/             # SQLAlchemy 数据模型
│   │   ├── schemas/            # Pydantic 数据校验
│   │   ├── services/           # 业务服务层（含 audit_log 审计证据链）
│   │   ├── config.py           # 配置管理
│   │   ├── database.py         # 数据库连接
│   │   └── main.py             # FastAPI 入口
│   ├── alembic/versions/       # 数据库迁移（001–010，含 009 审计快照、010 表清理）
│   └── tests/                  # 单元测试（387 passed / 8 skipped）
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── components/         # 通用组件
│   │   ├── pages/              # 页面组件
│   │   ├── store/              # Zustand 状态管理
│   │   ├── types/              # TypeScript 类型
│   │   ├── tests/              # 前端测试（56 passed）
│   │   └── utils/              # 工具函数
├── docs/                       # 方案文档与合规文件
├── scripts/                    # 辅助脚本
├── docker-compose.yml          # 容器编排
├── Dockerfile                  # 多阶段构建（生产单容器）
└── TESTING.md                  # 测试说明
```

## 功能模块

- **数据驾驶舱** — 企业财税概览与关键指标
- **风险地图** — 金税四期视角下的风险可视化与合规干预建议
- **风险模拟器** — 沉浸式决策场景模拟与合规干预
- **合规导航** — 合规路径检查与法规指引（挂接 Rule ID 治理矩阵）
- **合规检查** — 上传附件解析 + 四流稽核 + 核定扣除试算
- **整改追踪** — 风险整改任务管理与跟踪
- **报告中心** — 合规分析报告生成（PDF，数值携带 calc_id 可回溯）

## 测试

```bash
# 后端（387 passed / 8 skipped）
cd backend && pytest

# 前端（56 passed）
cd frontend && npm test
```

覆盖情况详见 [`TESTING.md`](TESTING.md)：核心引擎（rule_governance / deemed_deduction / four_flow_match / compliance_adjustment / credit_veto）、跨模块校验、端到端验证、API 租户隔离等均有独立测试文件。

## 文档

- [蒙牛AI创新_方案_迭代版V4.md](docs/蒙牛AI创新_方案_迭代版V4.md) — 方案总纲（答辩终稿）
- [OPEN_SOURCE_INTEGRATION.md](docs/OPEN_SOURCE_INTEGRATION.md) — 开源组件选型、许可证与集成踩坑
- [architecture.md](docs/architecture.md) — 架构说明
- [api.md](docs/api.md) — API 文档
- [deployment.md](docs/deployment.md) — 部署说明
- [PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md) / [DATA_PROCESSING_AGREEMENT.md](docs/DATA_PROCESSING_AGREEMENT.md) / [TERMS_OF_SERVICE.md](docs/TERMS_OF_SERVICE.md) — 合规文件

## License

MIT License — 见 [LICENSE](LICENSE)。
