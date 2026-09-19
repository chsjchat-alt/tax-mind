# 全面代码审核报告（2026-09-18）

> **审计对象**：`蒙牛全产业链 AI 内生合规决策大脑`（repo_stage @ commit `c3e1065`，与 `tax/` 镜像 b98e0b2 内容一致）
> **审计方法**：静态编译 → 全量测试 → 依赖/引用/配置完整性排查 → 逐模块逻辑审查 → 与《蒙牛AI创新_方案_迭代版V4》逐项比对
> **审计范围**：后端 124 个 .py 文件、前端全量 .ts/.tsx、alembic 迁移 001–010、docker-compose / Dockerfile / nginx.conf / .env.example、docs 全量文档

---

## 一、执行摘要（结论先行）

| 维度 | 结论 |
|---|---|
| **语法/编译** | ✅ **通过**。后端 124 个 .py 全部编译通过；前端 `tsc --noEmit` 0 错误 |
| **测试** | ✅ **通过**。后端 pytest **387 passed / 8 skipped**（含 zen-engine 依赖的 2 个模块）；前端 vitest **4 文件 / 55 用例全过** |
| **依赖引用** | ✅ **通过**。已删模块（心理画像/SSF/NBT）悬空导入 **0 处**；前端相对导入全部可解析；alembic 001→010 线性单头；前后端 API 面 33 个前端调用全部有后端对应路由 |
| **本地可运行性** | ✅ **可运行**（uvicorn + vite dev 开发模式完全正常） |
| **Docker 部署可运行性** | ❌ **当前无法启动**。存在 **5 个 P1 级部署缺陷**（密钥未注入、SSL 模式不匹配、健康检查路径错误、nginx 指令上下文错误、TLS 证书缺失），详见问题清单 #1–#5 |
| **V4 方案符合度** | ⚠️ **核心高度符合（约 90%）**，存在 **4 处 P2 级口径偏差**（一票否决档位、整改率算法、整改验证字段、证据链落库），详见问题清单 #6–#9 |

**问题总计：P1×5 / P2×5 / P3×5。**

---

## 二、静态检查与测试结果

| 检查项 | 结果 |
|---|---|
| 后端 `py_compile` 全量（124 文件） | 0 失败 |
| 前端 `tsc --noEmit` | 0 错误 |
| 后端 pytest 全量（补装 zen-engine 后） | **387 passed / 8 skipped / 0 failed** |
| 前端 vitest | **4 files / 55 tests passed** |
| 悬空导入（对已删 profile/ssf/nbt 模块） | 0 处 |
| 前端未解析相对导入 | 0 处 |
| alembic 迁移链 | 001→010 线性完整，单头节点，无悬空 down_revision |
| App.tsx 路由 ↔ pages 目录 | 7 页全部挂载，无缺失/无冗余 |
| 前后端 API 面 | 前端 33 个调用全部有后端路由；后端 6 个端点无前端调用（见 #14） |
| requirements.txt ↔ 实际 import | 全覆盖（zen-engine 已声明，属本机环境缺装而非代码缺陷） |

---

## 三、问题清单（按严重程度）

### 🔴 P1（严重 — 阻断部署/启动）

**#1 docker-compose 未注入启动必需密钥 → backend 容器启动即崩溃**
- 位置：`docker-compose.yml`（backend.environment）、`docker-compose.prod.yml`（仅 DATABASE_URL 等覆盖）、`backend/app/config.py`（启动强制校验）
- 现象：`config.py` 要求 `JWT_SECRET_KEY`、`ENCRYPTION_KEY` 为启动强制项，缺失直接抛 `RuntimeError`；两份 compose 均未传递这两个变量。
- 修复建议：在 compose 的 backend 环境变量中补 `JWT_SECRET_KEY=${JWT_SECRET_KEY}` 与 `ENCRYPTION_KEY=${ENCRYPTION_KEY}`，并在 `.env.example` 中给出占位符与生成命令（`openssl rand -hex 32` / Fernet key）。

**#2 dev compose 数据库 SSL 模式不匹配 → asyncpg 连接失败**
- 位置：`docker-compose.yml`（postgres 服务未配置 SSL）、`backend/app/config.py`（`db_ssl_mode` 默认 `"require"`）
- 现象：开发环境的 postgres 容器不支持 SSL，而默认 `ssl=require` 会导致连接被拒。
- 修复建议：dev compose 中给 backend 显式设 `DB_SSL_MODE=disable`（或把默认值改为 `prefer`）；prod 保持 `require`。

**#3 健康检查路径错误 → backend 永远被判 unhealthy**
- 位置：`docker-compose.yml`（`healthcheck.test` 探测 `/api/v1/health`）、`backend/app/main.py`（健康路由实际挂载在 `/health`）
- 现象：已实例化应用验证路由表，仅存在 `/health`；compose 探测 `/api/v1/health` 必然 404，健康检查永不通过（文档 `docs/api.md` 写的 `/health` 是对的）。
- 修复建议：compose 健康检查改为 `curl -f http://localhost:8000/health`；或在 `api_router` 中补一条 `/health` 别名路由。

**#4 nginx 指令放在错误上下文 → 前端容器 `nginx -t` 直接失败**
- 位置：`frontend/nginx.conf:23-24`（`worker_connections 1024;`、`worker_rlimit_nofile 65535;`）、`frontend/Dockerfile:17`（该文件被复制到 `/etc/nginx/conf.d/default.conf`，处于 **http** 上下文）
- 现象：这两条指令仅允许在 **main** 上下文；官方 nginx 镜像通过 conf.d 在 http 块内 include，`nginx -t` 报 `"worker_connections" directive is not allowed here`，容器无法启动。
- 修复建议：删除这两行（默认值即可），或改写到独立的 main 配置并通过自定义入口注入。

**#5 nginx 强制 TLS 但无证书挂载 → 前端容器启动失败**
- 位置：`frontend/nginx.conf:59-68`（`ssl_certificate /etc/nginx/ssl/fullchain.pem`、`ssl_certificate_key`、`ssl_dhparam`、`ssl_stapling`）、`docker-compose.yml`（frontend 服务无 ssl 卷挂载、未映射 443）
- 现象：dev compose 只映射 80 端口、无证书卷，nginx 因证书文件不存在拒绝启动。
- 修复建议：dev 场景提供仅 80 端口的简化配置（或用环境变量区分 dev/prod conf）；prod 场景补证书卷挂载与 443 映射，并在文档写明 certbot 签发流程。

---

### 🟠 P2（重要 — 与 V4 方案口径偏差 / 功能不完整）

**#6 一票否决未实现 DISQUALIFIED（不合格）档**
- 位置：`backend/app/core/credit_veto.py`（只返回否决标记）、`backend/app/core/compliance_adjustment.py:124`（否决时语义仅为"评分不因整改下调"，仍按原分走等级映射）；全库 grep 无 `DISQUALIFIED` 实现
- 方案要求：V4 §3.2 双状态口径 —— 触发一票否决（纳税信用 D 级 / 涉税犯罪）时应**直接判为不合格（DISQUALIFIED）**，不参与五档映射。
- 修复建议：在 `compliance_adjustment.py` 中当 `credit_veto` 命中时直接返回 `DISQUALIFIED` 档位；前端等级展示组件补该档位样式。

**#7 整改率算法与方案定义口径不一致**
- 位置：`backend/app/core/compliance_adjustment.py:140-141,182`（`reduction_pct = min(0.80, completion_count × 0.15)`）
- 方案要求：V4 §3.2 定义 整改率 = **已验证整改项权重 ÷ 可整改项总权重**，调整后分 = 原始分 × (1 − 整改率)。
- 现状差异：实现为"每完成一个任务固定降 15%、封顶 80%"，等价于任务数线性折减，未按风险项权重加权——高权重项与低权重项降幅相同。
- 修复建议：为 RemediationTask 关联的风险项引入权重字段，按方案公式重算；或（若团队认可现口径）在 V4 文档中修订该定义并注明理由。

**#8 整改任务缺少「已验证 / 验证人」数据结构**
- 位置：`backend/app/models/remediation_task.py`（status 仅有 COMPLETED 等状态，无 `verified`/`reviewer_id` 字段）
- 方案要求：V4 审计证据链与整改流程要求整改完成需**验证人确认**后才计入整改率。
- 修复建议：模型加 `verified: bool`、`reviewer_id`、`verified_at` 三列（配套 011 迁移），API 补验证端点，整改率统计改用 `verified=True` 过滤。

**#9 审计证据链"最后一公里"未打通（calc_id 不落库）**
- 位置：`backend/app/core/rule_governance/rule_executor.py:137-140` 与 `deemed_deduction/engine.py`（引擎层已产出 `calc_id` + 参数快照）；`backend/alembic/versions/009_add_audit_calc_snapshot.py`（audit_logs 已加 `calculation_id`/`param_snapshot` 两列）；但 `backend/app/main.py:48-60` 审计中间件**从不写入这两列**（全库无 `AuditLog(calculation_id=...)` 调用）
- 方案要求：V4 §二 —— 报告层引用的每个数值必须来自带计算 ID、参数快照与审计日志的确定性函数返回值。
- 修复建议：在调用规则引擎产生 calc_id 的服务层（报告/风险扫描/合规检查）将 `calculation_id` 与 `param_snapshot` 写入对应审计日志记录，打通引擎→审计日志的链路。

**#10 .env.example 配置项严重不全**
- 位置：`backend/.env.example`（仅 4 个键）vs `backend/app/config.py`（18 个配置字段）
- 现象：除 #1 所述强制项缺失外，`DB_SSL_MODE`、`ACCESS_TOKEN_EXPIRE_MINUTES` 等运行参数均无样例，新部署者无法据此完成配置。
- 修复建议：按 config.py 全量补齐 18 个键并加中文注释，标明必填/选填与默认值。

---

### 🟡 P3（轻微 — 文档/工程卫生）

**#11 `clsx` 声明未使用（死依赖）**
- 位置：`frontend/package.json`（dependencies 含 clsx）；`frontend/src` 全量 grep 无引用
- 修复建议：`npm uninstall clsx`。

**#12 `dayjs` 被引用但未显式声明**
- 位置：`frontend/src` 多处 import dayjs；`package.json` 未声明（当前靠 antd 的传递依赖能跑，antd 升级后可能断裂）
- 修复建议：`npm install dayjs` 显式声明。

**#13 `cryptography` 直接导入但未显式声明**
- 位置：`backend/app/utils/encryption.py:19`（`from cryptography.fernet import Fernet`）；`requirements.txt` 仅通过 passlib 传递安装
- 修复建议：requirements.txt 显式加 `cryptography>=42`。

**#14 后端 6 个已实现端点无前端调用**
- 位置：`/api/v1/auth/me`、`/api/v1/auth/register`、`/api/v1/ai/chat`、`/api/v1/ai/polish-report`、`/api/v1/financial-statements`（导入）、`/api/v1/risk-config` —— 后端路由已注册（43 条之一），前端 `api/index.ts` 无调用
- 说明：属"后端能力已备、UI 未暴露"，不算错误；`/ai/chat` 与 `/ai/polish-report` 若 V4 一期不承诺对话/润色 UI，可标注为二期接口。
- 修复建议：在 `docs/api.md` 标注各端点的 UI 状态（已接入/预留），避免评审误判为断链。

**#15 OPEN_SOURCE_INTEGRATION.md 测试数字过期**
- 位置：`docs/OPEN_SOURCE_INTEGRATION.md`（宣称 484 passed）；实际全量为 **387 passed / 8 skipped**
- 修复建议：更新为实测数字，并注明统计口径（含/不含 zen-engine 模块）。

---

## 四、与 V4 设计方案逐项比对

| V4 方案要求 | 实现位置 | 符合性 |
|---|---|---|
| §3.1 四流稽核四级分档（≥30% 重大 / 10–30% 显著 / 2–10% 轻微 / <2% 容差） | `four_flow_match.py`（阈值常量与分档逻辑） | ✅ 完全一致 |
| §3.2 双状态口径 + 五档等级映射 | `risk_engine.py` + `compliance_adjustment.py` | ⚠️ 部分一致（见 #6、#7） |
| §3.2 一票否决（信用 D 级 / 涉税犯罪） | `credit_veto.py`（判定依据引官方文件） | ⚠️ 判定有、档位无（#6） |
| §4.2 核定扣除引擎（投入产出法/成本法/参照法路由 + NONPILOT 白名单 + 公式） | `deemed_deduction/engine.py` + `fixtures/consumption_standards.json` | ✅ 公式逐项核对一致（乳制品/白名单/单耗标准齐全） |
| §十一 Rule ID 治理矩阵（14 条规则：编号/状态/层级/复核/责任人） | `rule_governance/fixtures/rules.json` + `rule_executor.py` | ✅ 14 条逐条对应，含状态机与复核标注 |
| §二 审计证据链（计算 ID + 参数快照 + 审计日志） | 引擎层 calc_id ✅ / audit_logs 落库 ❌ | ⚠️ 断链（#9） |
| §5.4 一期边界（不做侵入式心理画像，仅外部可观测行为机制） | 全库清理后仅存合法边界语句 + 历史迁移注释 | ✅ 完全一致 |
| LLM 边界（核心财税计算硬编码，LLM 仅润色/问答/案例检索，Mock 实现） | `llm_service.py`（规则引擎独立，LLM 不参与数值计算） | ✅ 完全一致 |
| calc_id 确定性（相同输入重算一致率 100%） | `rule_executor.py:137` SHA-256 规范化 JSON 哈希；测试断言 r1.calc_id==r2.calc_id | ✅ 已验证 |
| 数据结构：多租户 / 审计日志 / 风险轨迹 / 风险配置 | models + 迁移 003–008 | ✅ 模型与迁移对应完整 |
| 接口定义 | `docs/api.md` 与实际路由抽查一致（健康检查文档正确，compose 反而错了） | ✅（compose 侧见 #3） |

---

## 五、总体结论

1. **代码本体质量：可正常运行。** 语法零错误、依赖引用零悬空、迁移链完整、测试全绿（后端 387 过 / 前端 55 过）。本地开发模式（`uvicorn` + `vite`）开箱即用。

2. **Docker 部署链路：当前不可用。** 5 个 P1 配置缺陷（#1–#5）均集中在"编排/网关配置与代码约定脱节"，属**配置问题而非代码缺陷**，修复工作量小（预计半天内可全部闭环），但不修复则 `docker compose up` 无法得到健康的服务。

3. **方案符合度：核心业务逻辑与 V4 高度一致。** 四流分档、核定扣除公式、规则治理矩阵、LLM 边界、§5.4 一期边界逐项核对通过；**4 处 P2 偏差**（#6–#9）集中在"评分口径细则与证据链闭环"，建议按方案补齐实现（工作量约 1–2 天），或经团队评审后修订 V4 对应条款。

4. **建议修复顺序**：P1 部署五项（半天）→ P2 证据链落库 #9 与否决档 #6（1 天）→ P2 整改率口径 #7/#8（需产品决策）→ P3 工程卫生（随手清）。

---

*报告生成：2026-09-18 · 审计工具链：py_compile / tsc / pytest / vitest / 自研引用完整性扫描（AST 级 import 分析 + 路由正则提取 + MD5 树比对）*
