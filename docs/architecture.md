# 「税智·心判」多维业态财税合规与内控决策支持系统 架构设计文档

> 版本：v1.0 | 日期：2026-07-14 | 安全等级：等保 2.0 三级

---

## 目录

1. [系统全景拓扑](#1-系统全景拓扑)
2. [核心引擎架构](#2-核心引擎架构)
3. [数据流设计](#3-数据流设计)
4. [前端组件树](#4-前端组件树)
5. [数据库 E-R 图](#5-数据库-e-r-图)
6. [API 端点表](#6-api-端点表)
7. [NBT 行为干预管线](#7-nbt-行为干预管线)
8. [安全架构](#8-安全架构)
9. [技术栈](#9-技术栈)
10. [DevSecOps 部署流水线](#10-devsecops-部署流水线)

---

## 1. 系统全景拓扑

```mermaid
graph TB
    subgraph "公网入口层"
        CDN["CDN / WAF"]
        LB["Nginx 反代网关<br/>TLS 1.3 + Rate Limiting"]
    end

    subgraph "前端展示层"
        WEB["React 18 SPA (Vite 5)<br/>Tailwind CSS + Recharts + Zustand"]
        PAGES["7 个页面<br/>Dashboard / RiskMap / Profile<br/>Simulator / Compliance<br/>Remediation / Reports"]
    end

    subgraph "后端服务层"
        API["FastAPI 网关 (Uvicorn)<br/>CORS + pydantic 校验"]
        ENGINES["核心财税引擎集群<br/>7 大引擎 + 1 个 V2 五维引擎"]
        LLM["LLM 干预服务<br/>DeepSeek / Qwen"]
    end

    subgraph "持久化层"
        DB[("PostgreSQL 15<br/>SCRAM-SHA-256 加密<br/>AES-256 静态加密")]
        VOL["持久化卷<br/>pg_data"]
    end

    subgraph "DevSecOps"
        CI["GitHub Actions<br/>Ruff + Bandit + pytest"]
        REGISTRY["ghcr.io 镜像仓库"]
        SEEDER["Faker 脱敏数据播种器<br/>≥50家企业账套"]
    end

    CDN --> LB
    LB --> WEB
    WEB --> API
    API --> ENGINES
    API --> LLM
    ENGINES --> DB
    LLM --> DB
    CI --> REGISTRY
    SEEDER --> DB
```

---

## 2. 核心引擎架构

系统核心由**8个纯函数/纯硬编码财税引擎**组成，所有数值运算强制使用 `decimal.Decimal`，严禁浮点数，严禁大模型参与数值推演。

```mermaid
graph LR
    subgraph "数据输入层"
        E1["Enterprise<br/>企业基础画像"]
        E2["BankTransaction<br/>银行流水"]
        E3["Invoice<br/>进销项发票"]
        E4["Contract<br/>合同台账"]
        E5["TaxDeclaration<br/>纳税申报"]
        E6["FinancialStatement<br/>财务报表"]
        E7["IndustryBenchmark<br/>行业基准"]
    end

    subgraph "V1 风险引擎集群（7引擎）"
        F1["four_flow_match.py<br/>四流匹配度计算<br/>覆盖率 95%"]
        F2["risk_engine.py<br/>7维度风险评分<br/>覆盖率 97%"]
        F3["profile_engine.py<br/>6维度心理画像<br/>覆盖率 97%"]
        F4["penalty_calculator.py<br/>复合罚款敞口计算<br/>覆盖率 99%"]
        F5["simulation_engine.py<br/>3时间节点推演<br/>覆盖率 96%"]
        F6["tax_preference.py<br/>税收优惠校验<br/>覆盖率 100%"]
        F7["intervention.py<br/>心理干预策略<br/>覆盖率 99%"]
    end

    subgraph "V2 五维引擎"
        F8["tax_risk_engine.py<br/>五维全景穿透评估<br/>覆盖率 22%（新增）"]
    end

    subgraph "输出层"
        O1["RiskAssessment<br/>风险评分 + 双轨叙事"]
        O2["ProfileResult<br/>偏差画像 + 免责声明"]
        O3["PenaltyExposure<br/>罚款+个税穿透+滞纳金"]
        O4["SimulationResult<br/>双路径对比 + 案例引用"]
        O5["NBTIntervention<br/>Nudge-Budge-Trudge"]
    end

    E1 & E2 & E3 & E4 & E5 & E6 & E7 --> F1
    F1 --> F2
    F2 --> F8
    F1 & E2 --> F3
    F2 & E5 --> F4
    F2 & F4 --> F5
    E1 & E7 --> F6
    F3 --> F7
    F2 --> O1
    F3 --> O2
    F4 --> O3
    F5 --> O4
    F2 & F3 --> O5
```

### 2.1 五维全景穿透评估引擎（V2）

`calculate_comprehensive_tax_risk()` — 计划书 V2 优化版核心交付物：

| 维度 | 评估内容 | 阻断逻辑 | 法律依据 |
|------|---------|---------|---------|
| **一** | 行业基准与宏观内控核算（成本费用率） | `actual_cost_rate > benchmark × 1.5` → `InternalControlFailureWarning` | 行业财税特征量化 |
| **二** | 增值税GAAR穿透（四流匹配 + 资金闭环） | `four_flow_score < 60 AND fund_loopback_detected` → `GAARViolationWarning` | 《企业所得税法》第47条 |
| **三** | 个人所得税隐性分红穿透 | `shareholder_loan > 0 AND days_overdue > 365` → 强制 ×20% | 财税[2003]158号 |
| **四** | 0.5-5.0×浮动行政罚款 + 日万分之五复利滞纳金 | 多级倍数叠加 | 《税收征收管理法》第32/63/68条 |
| **五** | 综合加权评分 + 一票否决 | 「三流及以上维度命中高危阈值」→ 总体风险 = CRITICAL | 风险矩阵评估框架 |

---

## 3. 数据流设计

```mermaid
sequenceDiagram
    participant U as 企业主用户
    participant FE as React SPA
    participant API as FastAPI 网关
    participant RE as 风险引擎集群
    participant DB as PostgreSQL 15
    participant LLM as LLM 干预服务

    %% 阶段1: 风险扫描
    U->>FE: 选择企业 → 触发风险扫描
    FE->>API: POST /api/v1/enterprises/{id}/scan
    API->>DB: 查询企业画像 + 流水 + 发票 + 合同 + 申报 + 报表 + 行业基准
    DB-->>API: 全量明细数据
    API->>RE: 调用 four_flow_match → risk_engine → tax_risk_engine
    RE-->>API: RiskAssessment（7维 + 五维 + 双轨叙事）
    API->>DB: 持久化评估结果
    API-->>FE: {code: 200, data: RiskAssessment}

    %% 阶段2: 心理画像
    FE->>API: GET /api/v1/enterprises/{id}/profile
    API->>DB: 查询流水行为数据
    DB-->>API: BehavioralData
    API->>RE: profile_engine.calculate_psychological_profile()
    RE-->>API: ProfileResult（6维偏差 + 免责声明）
    API-->>FE: {code: 200, data: ProfileResult}

    %% 阶段3: 风险模拟
    FE->>API: POST /api/v1/enterprises/{id}/simulate
    API->>RE: simulation_engine.run_simulation()
    RE-->>API: SimulationResult（3时间节点）
    API-->>FE: {code: 200, data: SimulationResult}

    %% 阶段4: NBT干预
    FE->>API: POST /api/v1/enterprises/{id}/nbt-intervention
    API->>DB: 补充企业画像
    API->>LLM: DeepSeek/Qwen（30s timeout + 3次重试）
    LLM-->>API: JSON{ nudge, budge, trudge }
    API-->>FE: {code: 200, data: NBTInterventionResult}

    %% 渲染
    FE->>U: 五维雷达 | 双轨仪表 | 指数雪球 | Trudge SOP
```

---

## 4. 前端组件树

```
App.tsx (Vite 5 + React 18 + TypeScript)
│
├── MainLayout
│   ├── Header                      # 企业选择器 + 导航栏
│   └── Sidebar                     # 7个页面入口
│
├── Dashboard.tsx                   # 数据驾驶舱
│   ├── StatCard × 4                # 核心KPI卡片
│   ├── RiskRadar                   # 7维度雷达图
│   ├── RiskBarChart                # 风险维度柱状图
│   └── RiskTrendChart              # 风险评分趋势折线图
│
├── RiskMap.tsx                     # 五维全景税务内控侦测面板（重构版）
│   ├── BusinessModelBanner         # 重资产/轻资产锚点标识
│   ├── RiskLegend                  # 风险三色图例
│   ├── LanguageToggle              # 商业/技术视角切换
│   ├── ICRadarSection              # 宏观内控雷达监测区
│   │   ├── DualCostGauge           #   成本费用率 vs 行业警戒阈值（SVG弧线）
│   │   └── TaxBurdenElasticityChart #  收入增长率 vs 税负率下跌曲线
│   ├── RiskMapCard × 7            # 7维度可展开卡片
│   ├── NudgeLayerBanner            # Nudge高压渲染（#EF4444背景）
│   └── BridgeLayerPanel            # 损失框架对比（高压时显示）
│
├── Profile.tsx                     # 心理画像仪
│   ├── ProfileRadarChart           # 6维度偏差雷达图
│   ├── BiasCard                    # 主导偏差卡片
│   ├── ProfileSummary              # 画像摘要
│   └── DisclaimerBanner            # 免责声明
│
├── Simulator.tsx                   # 沉浸式风险模拟器（重构版）
│   ├── SimulationInputForm         # 参数输入面板
│   ├── ExponentialSnowballChart    # 指数雪球双路径对比图
│   ├── SnowballDecompositionTable  # 组分分解表（本金+罚金+个税+滞纳金）
│   ├── LossFrameMessage            # 损失框架话术
│   ├── CaseStudyCard               # 同行业案例引用
│   ├── TrudgeChecklist             # 可交互SOP微任务打卡列表
│   │   ├── ProgressBar             #   合规整改进度条
│   │   └── TrudgeTaskItem × N      #   可展开详情 + 勾选框
│   └── RecommendationBanner        # 模拟建议
│
├── Compliance.tsx                  # 合规导航仪
│   ├── TaxPreferencePanel          # 税收优惠校验面板
│   ├── PlanComparisonTable         # 方案对比表
│   └── InterventionLayerCard       # 干预策略卡片
│
├── Remediation.tsx                 # 整改追踪器
│   ├── ProgressDonut               # 进度环形图
│   ├── TaskCard × N                # 任务卡片列表
│   └── ImprovementFeedback         # 整改反馈面板
│
├── Reports.tsx                     # 报告查看页
│
└── Common Components               # 通用组件
    ├── LoadingSpinner
    ├── EmptyState
    ├── RiskBadge
    └── Disclaimer
```

**状态管理（Zustand Store）：**

```
store/index.ts
├── useEnterpriseStore              # { currentEnterprise, enterprises[], selectEnterprise() }
├── useRiskStore                    # { result, loading, scanRisk() }
└── useRemediationStore             # { tasks[], fetchTasks() }
```

---

## 5. 数据库 E-R 图

```mermaid
erDiagram
    Enterprise ||--o{ BankTransaction : "has"
    Enterprise ||--o{ Invoice : "issues"
    Enterprise ||--o{ TaxDeclaration : "files"
    Enterprise ||--o{ Contract : "signs"
    Enterprise ||--o{ FinancialStatement : "reports"
    Enterprise ||--o{ RiskAssessment : "evaluated_by"
    Enterprise ||--o{ PsychologicalProfile : "profiled_by"
    Enterprise ||--o{ RemediationTask : "assigned_to"
    Enterprise }o--|| IndustryBenchmark : "benchmarked_against"
    Enterprise ||--o{ Report : "generated"

    Enterprise {
        uuid id PK
        string credit_code UK
        string name
        enum industry
        numeric revenue_annual
        integer employee_count
        numeric tax_rate_claimed
        numeric cost_rate_claimed
        boolean is_high_tech
        boolean is_small_micro
        string legal_person_name
        string legal_person_id
        enum risk_level
    }

    IndustryBenchmark {
        uuid id PK
        enum industry_asset_type "HEAVY / LIGHT"
        string industry_name
        numeric std_tax_burden_rate
        numeric max_cost_expense_ratio
        numeric depreciation_to_revenue_ratio
        numeric private_card_ratio_mean
    }

    BankTransaction {
        uuid id PK
        uuid enterprise_id FK
        date transaction_date
        numeric amount "NUMERIC(15,2)"
        enum direction "inflow / outflow"
        enum account_type "corporate / personal"
        string counterparty
        string description
        boolean is_declared
    }

    Invoice {
        uuid id PK
        uuid enterprise_id FK
        string invoice_no
        enum invoice_type "input / output"
        date invoice_date
        numeric amount
        numeric tax_amount
        numeric total_amount
        string product_name
        boolean is_digital
    }

    RiskAssessment {
        uuid id PK
        uuid enterprise_id FK
        date assessment_date
        enum overall_risk_level
        numeric overall_risk_score
        numeric four_flow_match_score
        numeric private_card_ratio
        numeric cost_deviation
        json risk_details
        json recommendations
        text business_narrative
        text technical_summary
    }

    PsychologicalProfile {
        uuid id PK
        uuid enterprise_id FK
        date assessment_date
        numeric deviation_index
        array dominant_biases
        json bias_scores
        json intervention_strategy
        text disclaimer
    }

    RemediationTask {
        uuid id PK
        uuid enterprise_id FK
        uuid risk_assessment_id FK
        string title
        string description
        enum priority
        enum status
        date due_date
        numeric progress
    }
```

### 数值精度红线

所有货币/比率字段强制使用 PostgreSQL NUMERIC 类型：

| 字段类型 | PostgreSQL 列定义 | Python 端 |
|---------|-------------------|----------|
| 金额 | `NUMERIC(15,2)` | `Decimal(str(value)).quantize(Decimal("0.01"))` |
| 比率 | `NUMERIC(10,4)` | `Decimal(str(value)).quantize(Decimal("0.0001"))` |
| 百分比 | `NUMERIC(5,2)` | `Decimal(str(value))` |
| 日期 | `DATE` / `TIMESTAMP WITH TIME ZONE` | `date.today()` / `datetime.now(tz=...)` |

---

## 6. API 端点表

基础路径：`/api/v1`

### 企业管理

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `GET` | `/enterprises` | 企业列表（分页） | ✅ |
| `GET` | `/enterprises/{id}` | 企业详情 | ✅ |
| `POST` | `/enterprises` | 新增企业 | ✅ |

### 数据导入

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `POST` | `/enterprises/{id}/bank-transactions` | 导入银行流水 | ✅ |
| `POST` | `/enterprises/{id}/invoices` | 导入发票 | ✅ |
| `POST` | `/enterprises/{id}/tax-declarations` | 导入纳税申报 | ✅ |
| `POST` | `/enterprises/{id}/contracts` | 导入合同 | ✅ |

### 风险引擎

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `POST` | `/enterprises/{id}/scan` | 执行风险扫描（V1+V2 引擎） | ✅ |
| `GET` | `/enterprises/{id}/risk-assessments` | 风险评估历史 | ✅ |
| `GET` | `/enterprises/{id}/profile` | 心理画像 | ✅ |

### 风险模拟

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `POST` | `/enterprises/{id}/simulate` | 执行风险模拟（3时间节点） | ✅ |
| `GET` | `/enterprises/{id}/simulation-history` | 模拟历史 | ✅ |

### 合规导航

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `GET` | `/enterprises/{id}/tax-preference` | 税收优惠校验 | ✅ |
| `GET` | `/enterprises/{id}/intervention` | 干预策略 | ✅ |
| `POST` | `/enterprises/{id}/nbt-intervention` | **NBT 三层行为干预（LLM）** | ✅ |

### 整改追踪

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `GET` | `/enterprises/{id}/tasks` | 整改任务列表 | ✅ |
| `POST` | `/enterprises/{id}/tasks` | 创建整改任务 | ✅ |
| `PUT` | `/tasks/{id}` | 更新任务状态 | ✅ |

### 报告

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `POST` | `/enterprises/{id}/reports` | 生成综合风险报告 | ✅ |
| `GET` | `/enterprises/{id}/reports` | 报告列表 | ✅ |

### AI 助手

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `POST` | `/enterprises/{id}/ai-assistant` | AI 智能纳税合规顾问 | ✅ |
| `GET` | `/enterprises/{id}/case-studies` | 同行业案例库 | ✅ |

### 健康检查

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| `GET` | `/health` | 健康检查 | ✅ |

### 统一响应格式

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { ... }
}
```

**错误码体系：**

| 错误码 | 含义 |
|--------|------|
| `200` | 成功 |
| `40001` | 参数校验失败 |
| `40002` | 业务逻辑错误 |
| `40003` | 资源不存在 |
| `50000` | 服务器内部错误 |

---

## 7. NBT 行为干预管线

```mermaid
flowchart TB
    INPUT["输入<br/>RiskAssessment + ProfileResult + 企业画像"]
    RT{"LLM 健康检查"}
    DEEPSEEK["DeepSeek API<br/>response_format: json_object<br/>30s timeout<br/>3次指数退避重试"]
    QWEN["Qwen API<br/>OpenAI 兼容模式"]
    MOCK["降级 Mock<br/>预置模板匹配行业"]
    VALID{"Pydantic 严格校验<br/>NBTInterventionResponse"}
    RETRY{"重试次数 < 3?"}
    OUTPUT["输出<br/>{ nudge, budge, trudge }"]

    INPUT --> RT
    RT -->|"DeepSeek在线"| DEEPSEEK
    RT -->|"Qwen在线"| QWEN
    RT -->|"全部离线"| MOCK
    DEEPSEEK --> VALID
    QWEN --> VALID
    MOCK --> VALID
    VALID -->|"通过"| OUTPUT
    VALID -->|"失败"| RETRY
    RETRY -->|"是"| RT
    RETRY -->|"否"| MOCK
```

**三层结构说明：**

| 层 | 名称 | 心理学基础 | 前端渲染 |
|----|------|-----------|---------|
| **Nudge** | 环境助推 | 注意力引导 + 色彩心理学 | #EF4444 深红高压渲染 + 直白预警文案 |
| **Bridge** | 信念重塑 | 前景理论（损失敏感度 ≈ 收益 ×2.5） | 三卡片面板（损失对比/破除逃避/时间压力） |
| **Trudge** | 长效信任 | 自我效能感 + 承诺一致性 | 交互式 Checkbox 微任务列表 + 进度条 |

---

## 8. 安全架构

```mermaid
flowchart LR
    subgraph "传输层"
        TLS["TLS 1.3<br/>AES-256-GCM<br/>CHACHA20-POLY1305"]
    end
    subgraph "DDoS 防护"
        RATE["Rate Limiting<br/>10r/s (正常) · 5r/s (API)<br/>1r/s (认证)"]
        CONN["连接数限制<br/>20/IP (全局)"]
    end
    subgraph "数据层"
        MASK["PII 星号掩码<br/>不可逆脱敏"]
        CREDIT["GB 32100 虚拟<br/>信用代码生成"]
        PWD["SCRAM-SHA-256<br/>PostgreSQL 认证"]
    end
    subgraph "CI/CD"
        RUFF["Ruff 静态分析"]
        BANDIT["Bandit 安全扫描"]
        HARD["Exit Code ≠ 0<br/>→ 硬性阻断"]
    end
    subgraph "容器层"
        READONLY["只读根文件系统"]
        NOPRIV["no-new-privileges"]
        ZEROTRUST["零信任网络<br/>DB 不对外暴露端口"]
    end

    TLS --> RATE
    RATE --> CONN
    CONN --> MASK
    RUFF --> HARD
    BANDIT --> HARD
    HARD --> READONLY
    READONLY --> NOPRIV
    NOPRIV --> ZEROTRUST
```

### 安全头注入（Nginx）

| Header | 值 | 目的 |
|--------|---|------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | 强制 HTTPS |
| `X-Content-Type-Options` | `nosniff` | 防 MIME 嗅探 |
| `X-Frame-Options` | `DENY` | 防 Clickjacking |
| `X-XSS-Protection` | `1; mode=block` | 防 XSS |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | 隐私保护 |
| `Content-Security-Policy` | `default-src 'self'` | XSS 纵深防御 |

---

## 9. 技术栈

| 层级 | 技术选型 | 版本 |
|------|---------|------|
| **前端框架** | React + TypeScript | 18.x |
| **构建工具** | Vite | 5.x |
| **CSS 框架** | Tailwind CSS | 3.4 |
| **图表库** | Recharts | 2.x |
| **状态管理** | Zustand | 5.x |
| **HTTP 客户端** | Axios | 1.x |
| **UI 组件** | Ant Design | 5.x |
| **后端框架** | FastAPI + Uvicorn | 0.x |
| **ORM** | SQLAlchemy 2.0 (async) | 2.x |
| **数据校验** | Pydantic v2 | 2.x |
| **数据库** | PostgreSQL (asyncpg) | 15 |
| **迁移工具** | Alembic | 1.x |
| **数值计算** | decimal.Decimal | 内置 |
| **数据播种** | Python Faker | >=30.0 |
| **LLM 集成** | httpx + openai SDK | — |
| **CI/CD** | GitHub Actions | v4 |
| **容器化** | Docker + Docker Compose | — |
| **Web 服务器** | Nginx | 1.x |
| **静态分析** | Ruff + Bandit | — |
| **测试框架** | pytest + pytest-asyncio + pytest-cov | — |

---

## 10. DevSecOps 部署流水线

```mermaid
flowchart LR
    PUSH["git push<br/>main branch"]
    J1["JOB 1: 后端扫描&测试<br/>Ruff + Bandit + pytest<br/>postgres:15 服务容器<br/>覆盖率阈值 ≥90%"]
    J2["JOB 2: 前端构建<br/>tsc noEmit<br/>ESLint max-warnings 0<br/>Vite build"]
    J3["JOB 3: Docker 镜像<br/>构建 & 推送<br/>ghcr.io"]
    J4["JOB 4: 安全摘要<br/>合规清单输出"]

    PUSH --> J1
    PUSH --> J2
    J1 & J2 --> J3
    J3 --> J4
    J1 -->|"Exit ≠ 0 → BLOCK"| BLOCK["部署硬阻断"]
    J2 -->|"Exit ≠ 0 → BLOCK"| BLOCK
    J3 -->|"镜像推送成功"| DEPLOY["kubectl / docker compose<br/>生产环境部署"]
```

### 部署检查清单

```yaml
# 部署前执行
docker compose up -d postgres
cd backend && alembic upgrade head
python ../scripts/mock_desensitized_data_seeder.py --count 50
docker compose up -d --build

# 验证端点
curl -k https://localhost/api/v1/health
curl -k https://localhost/api/v1/enterprises

# 运行测试
cd backend && pytest tests/ --cov=app/core --cov-fail-under=90
```

---

*文档生成时间：2026-07-14*
*本文档与 `api.md`、`deployment.md`、`ai_collaboration_log.md` 共同构成项目技术文档体系。*
