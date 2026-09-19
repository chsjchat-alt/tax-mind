# 「蒙牛全产业链 AI 内生合规决策大脑」API 接口文档

> 版本：v1.0 | 基础路径：`/api/v1` | 协议：RESTful JSON over HTTPS (TLS 1.3)
>
> 基于 FastAPI 自动生成的 [OpenAPI JSON](file:///d:/安永/tax/backend/openapi.json) 整理，含业务说明。

---

## 0. 认证（Authentication）

所有业务 API 均需携带 JWT Bearer Token 进行身份认证。

### 0.1 注册用户

```http
POST /api/v1/auth/register
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | ✅ | 用户名 |
| `password` | string | ✅ | 密码 |
| `tenant_slug` | string | ✅ | 租户标识 |

### 0.2 登录（OAuth2 Password Flow）

```http
POST /api/v1/auth/login
```

**请求体（`application/x-www-form-urlencoded`）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | ✅ | 用户名 |
| `password` | string | ✅ | 密码 |

**响应 `data`：**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 0.3 刷新令牌

```http
POST /api/v1/auth/refresh
```

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `refresh_token` | string | ✅ | 已颁发的 refresh_token |

**响应 `data`：** 返回新的 `access_token` + `refresh_token` 对。

### 0.4 获取当前用户信息

```http
GET /api/v1/auth/me
```

**需要认证：** 🔐 viewer

**响应 `data`：**

```json
{
  "user_id": "uuid",
  "username": "admin",
  "tenant_id": "uuid",
  "role": "admin",
  "created_at": "2025-01-15T10:30:00Z"
}
```

### JWT Token 格式

所有认证接口返回的 `access_token` 和 `refresh_token` 均为 JWT Bearer Token，载荷（Payload）中包含：

| 字段 | 说明 |
|------|------|
| `sub` | `user_id`（用户唯一标识） |
| `username` | 用户名 |
| `tenant_id` | 所属租户标识 |
| `role` | 用户角色（`viewer` / `auditor` / `admin`） |
| `exp` | 过期时间（access_token 默认 60 分钟） |
| `iat` | 签发时间 |

### 调用受保护接口

所有业务接口（除健康检查外）均需在请求头中携带 Token：

```http
Authorization: Bearer <access_token>
```

---

## 目录

0. [认证（Authentication）](#0-认证authentication)
1. [通用约定](#通用约定)
2. [企业管理（Enterprises）🔐 admin](#1-企业管理)
3. [数据接入（Data Ingestion）🔐 admin](#2-数据接入)
4. [风险引擎（Risk Engine）🔐 auditor](#3-风险引擎)
5. [风险模拟（Risk Simulation）🔐 auditor](#4-风险模拟)
6. [合规导航（Compliance）🔐 auditor](#5-合规导航)
7. [整改追踪（Remediation）🔐 admin](#6-整改追踪)
8. [报告生成（Reports）🔐 viewer](#7-报告生成)
9. [AI 助手（AI Assistant）🔐 viewer](#8-ai-助手)
10. [核定扣除计算（Deemed Deduction）🔐 viewer](#9-核定扣除计算)
11. [参数配置（Risk Config）🔐 admin](#10-参数配置)
12. [健康检查（公开）](#11-健康检查)

---

## 通用约定

### 统一响应格式

所有接口采用统一 JSON 响应格式：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | `integer` | 状态码（见下方错误码表） |
| `message` | `string` | 人类可读的状态说明 |
| `data` | `object / array / null` | 业务数据载荷 |

### 错误码

| code | 含义 | 触发场景 |
|------|------|---------|
| `200` | 成功 | 无 |
| `40001` | 参数校验失败 | 请求体不符合 Pydantic schema |
| `40002` | 业务逻辑错误 | 企业不存在 / LLM 超时 / 数据不足 |
| `40003` | 资源不存在 | 查询的资源 ID 在数据库中不存在 |
| `50000` | 服务器内部错误 | 未预期的异常 |

### 请求头

| Header | 值 | 说明 |
|--------|---|------|
| `Authorization` | `Bearer <access_token>` | 所有需要认证的业务接口必须携带（除健康检查外） |
| `Content-Type` | `application/json` | 所有 POST/PUT 请求必须携带 |
| `Accept` | `application/json` | 客户端期望的响应格式 |

### 日期格式

所有日期字段使用 ISO 8601 格式：`YYYY-MM-DD`（如 `2025-07-14`）。

---

## 1. 企业管理 🔐 admin

管理企业基本档案信息，是所有风险分析的数据锚点。

```
基础路径: /api/v1/enterprises
```

### 1.1 获取企业列表

```http
GET /api/v1/enterprises
```

**查询参数：**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `page` | integer | 否 | 1 | 页码 |
| `page_size` | integer | 否 | 20 | 每页条数 |
| `industry` | string | 否 | — | 按行业筛选（批发零售/制造/建筑/电商/餐饮服务/医美咨询） |
| `risk_level` | string | 否 | — | 按风险等级筛选（low/medium/high/critical） |

**响应 `data`：**

```json
{
  "items": [{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "创亿电子商务实业有限公司",
    "industry": "电商",
    "revenue_annual": 47090000,
    "risk_level": "low",
    "created_at": "2025-01-15T10:30:00Z"
  }],
  "total": 50,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

### 1.2 创建企业

```http
POST /api/v1/enterprises
```

**请求体 — `EnterpriseCreate`：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 企业名称 |
| `credit_code` | string | ✅ | 统一社会信用代码（18位） |
| `industry` | string | ✅ | 行业类型（批发零售/制造/建筑/电商/餐饮服务） |
| `revenue_annual` | number | 否 | 年营收（元） |
| `employee_count` | integer | 否 | 员工人数 |
| `tax_rate_industry` | number | 否 | 行业平均税负率（%） |
| `cost_rate_industry` | number | 否 | 行业平均成本费用率（%） |
| `is_high_tech` | boolean | 否 | 是否高新技术企业 |
| `is_small_micro` | boolean | 否 | 是否小微企业 |
| `risk_level` | string | 否 | 风险等级（low/medium/high） |

**示例：**

```json
{
  "name": "创亿电子商务实业有限公司",
  "credit_code": "91440300HRKTHM178W",
  "industry": "电商",
  "revenue_annual": 50000000,
  "employee_count": 45,
  "tax_rate_industry": 3.2,
  "cost_rate_industry": 88.5,
  "is_high_tech": false,
  "is_small_micro": true,
  "risk_level": "low"
}
```

**响应 `data`：** 返回创建后的完整 `Enterprise` 对象（含 auto-generated `id` 和 `created_at`）。

### 1.3 获取企业详情

```http
GET /api/v1/enterprises/{enterprise_id}
```

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `enterprise_id` | UUID | 企业唯一标识 |

**响应 `data`：**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "创亿电子商务实业有限公司",
  "credit_code": "91440300HRKTHM178W",
  "industry": "电商",
  "revenue_annual": 47090000,
  "employee_count": 45,
  "tax_rate_industry": 3.2,
  "cost_rate_industry": 88.5,
  "is_high_tech": false,
  "is_small_micro": true,
  "risk_level": "low",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-07-14T08:00:00Z"
}
```

### 1.4 更新企业

```http
PUT /api/v1/enterprises/{enterprise_id}
```

**请求体 — `EnterpriseUpdate`：**

所有字段均为可选，仅提交需要更新的字段。

```json
{
  "revenue_annual": 55000000,
  "risk_level": "medium"
}
```

### 1.5 删除企业

```http
DELETE /api/v1/enterprises/{enterprise_id}
```

**说明：** 级联删除该企业关联的所有流水、发票、申报、合同、评估、整改任务和报告。

---

## 2. 数据接入

导入与查询企业六源财税数据——银行流水、发票、纳税申报、合同、财务报表——为风险引擎提供计算原料。

```
基础路径: /api/v1/enterprises/{enterprise_id}
```

### 2.1 银行流水

#### 获取流水列表
```http
GET /api/v1/enterprises/{enterprise_id}/bank-statements
```

**响应 `data` — `BankTransaction[]`：**

```json
[{
  "id": "uuid",
  "enterprise_id": "uuid",
  "transaction_date": "2025-06-15",
  "direction": "inflow",
  "amount": 125000.00,
  "account_type": "corporate",
  "counterparty": "鑫达钢材有限公司",
  "description": "货款",
  "is_declared": true
}]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `direction` | enum | `inflow`（流入）/ `outflow`（流出） |
| `account_type` | enum | `corporate`（公户）/ `personal`（个人卡） |
| `is_declared` | boolean | 是否已在税收申报中体现 |

#### 导入流水数据
```http
POST /api/v1/enterprises/{enterprise_id}/bank-statements
```

**请求体：** `BankTransaction[]` 数组（批量导入）。

### 2.2 发票

#### 获取发票列表
```http
GET /api/v1/enterprises/{enterprise_id}/invoices
```

#### 导入发票
```http
POST /api/v1/enterprises/{enterprise_id}/invoices
```

**`Invoice` 对象：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `invoice_no` | string | 发票号码（如 `FP-2025-06-OS-0001`） |
| `invoice_type` | enum | `input`（进项）/ `output`（销项） |
| `invoice_date` | date | 开票日期 |
| `product_name` | string | 商品/服务名称 |
| `tax_rate` | number | 税率（如 13.0） |
| `amount` | number | 不含税金额 |
| `tax_amount` | number | 税额 |
| `total_amount` | number | 含税总额 |
| `buyer_name` | string | 购方名称 |
| `seller_name` | string | 销方名称 |
| `is_digital` | boolean | 是否数字化电子发票 |

### 2.3 纳税申报

```http
GET /api/v1/enterprises/{enterprise_id}/tax-declarations
```

**`TaxDeclaration` 对象：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `tax_type` | enum | VAT / INCOME_TAX / PERSONAL_INCOME_TAX |
| `period` | string | 所属期（如 `2025-Q2-VAT`） |
| `declared_revenue` | number | 申报收入 |
| `declared_tax` | number | 申报税额 |
| `actual_paid` | number | 实际缴纳额 |

### 2.4 合同

```http
GET /api/v1/enterprises/{enterprise_id}/contracts
```

**`Contract` 对象：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `contract_no` | string | 合同编号（如 `XS-2025-0001`） |
| `contract_type` | enum | `sales` / `purchase` |
| `counterparty` | string | 对方主体 |
| `contract_amount` | number | 合同金额 |
| `signing_date` | date | 签订日期 |
| `execution_status` | string | 履约状态 |

### 2.5 财务报表

```http
GET /api/v1/enterprises/{enterprise_id}/financial-statements
```

**`FinancialStatement` 对象：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `period` | string | 期间（如 `2025-Q1-BS`） |
| `statement_type` | enum | `balance_sheet` / `income_statement` / `cash_flow` |
| `total_assets` | number | 总资产 |
| `total_liabilities` | number | 总负债 |
| `total_revenue` | number | 营业收入 |
| `total_cost` | number | 营业成本 |
| `net_profit` | number | 净利润 |
| `operating_cash_flow` | number | 经营性现金流 |
| `tax_burden_rate` | number | 税负率（%） |
| `cost_rate` | number | 成本费用率（%） |

### 2.6 批量注入模拟数据

```http
POST /api/v1/enterprises/{enterprise_id}/load-mock-data
```

**说明：** 自动为指定企业注入 24 个月银行流水 + 发票 + 纳税申报 + 合同。适用于快速填充演示数据，不适用于生产环境。

---

## 3. 风险引擎 🔐 auditor

> **计算引擎：** `risk_engine.py`（7维度 V1 + 双轨输出）+ `tax_risk_engine.py`（五维全景穿透 V2）  
> **辅助引擎：** `four_flow_match.py`（四流匹配度）、`penalty_calculator.py`（复合罚款敞口）

```
基础路径: /api/v1/enterprises/{enterprise_id}
```

### 3.1 执行风险扫描

```http
POST /api/v1/enterprises/{enterprise_id}/risk-scan
```

**说明：** 触发完整风险扫描流程——四流匹配 → V1 7维度评分 → V2 五维穿透评估 → 双轨叙事生成。耗时取决于数据量，通常 3-10 秒。

**无请求体。** 扫描所需所有数据均从已导入的企业数据中获取。

**响应 `data` — `RiskScanResult`：**

```json
{
  "risk_assessment_id": "uuid",
  "enterprise_id": "uuid",
  "overall_risk_level": "high",
  "overall_risk_score": 78.5,
  "four_flow_match_score": 58.2,
  "private_card_ratio": 0.45,
  "cost_deviation": 25.3,
  "dimension_scores": {
    "private_card_ratio": 92,
    "cost_deviation": 78,
    "tax_burden_deviation": 65,
    "four_flow_mismatch": 58,
    "invoice_bank_mismatch": 42,
    "large_personal_transfer": 38,
    "input_output_imbalance": 25
  },
  "dim_details": {
    "private_card_ratio": {
      "detail": "私卡收款率45%，远超行业基准15%，存在严重的收入隐匿风险",
      "technical_detail": "private_card_ratio=0.45 vs industry_benchmark=0.15, severity=critical"
    }
  },
  "recommendations": {},
  "business_narrative": "贵司私卡收款比率高达45%，成本费用率偏离行业基准25.3个百分点...",
  "technical_summary": "private_card_ratio=0.45(总分92), cost_deviation=25.3pp(总分78)...",
  "assessment_date": "2025-07-14T10:30:00Z"
}
```

**V2 五维引擎额外输出（嵌入在 `RiskScanResult` 的扩展字段中）：**

| 维度 | evaluator | 阻断逻辑 |
|------|-----------|---------|
| 一·成本费用率内控 | `InternalControlFailureWarning` | `actual_cost_rate > benchmark × 1.5` |
| 二·GAAR穿透 | `GAARViolationWarning` | `four_flow_score < 60 AND fund_loopback_detected` |
| 三·个税隐性分红 | `IITHiddenDividendWarning` | `shareholder_loan_days > 365 → 强制 ×20%` |
| 四·复合罚款 | `penalty_calculator` | 0.5-5.0x + 日万分之五滞纳金 |
| 五·一票否决 | `calculate_comprehensive_tax_risk` | 三流及以上高危 → `CRITICAL` |

### 3.2 获取风险评估历史

```http
GET /api/v1/enterprises/{enterprise_id}/risk-assessments
```

### 3.3 获取最新风险评估

```http
GET /api/v1/enterprises/{enterprise_id}/risk-assessments/latest
```

### 3.4 获取详情（跨企业）

```http
GET /api/v1/risk-assessments/{assessment_id}
```

---

## 4. 风险模拟

> **计算引擎：** `simulation_engine.py`（3时间节点推演）+ `penalty_calculator.py`（复合罚款敞口）

```
基础路径: /api/v1/enterprises/{enterprise_id}
```

### 4.1 执行风险模拟

```http
POST /api/v1/enterprises/{enterprise_id}/simulate
```

**请求体 — `SimulationRequest`：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `monthly_hidden_revenue` | number | ✅ | 月均隐匿收入（元） |
| `comprehensive_tax_rate` | number | ✅ | 综合税率（如 0.06 表示 6%） |
| `remediation_cost` | number | ✅ | 合规整改成本（元） |

**示例：**

```json
{
  "monthly_hidden_revenue": 500000,
  "comprehensive_tax_rate": 0.06,
  "remediation_cost": 300000
}
```

**响应 `data` — `SimulationResult`：**

```json
{
  "time_points": [{
    "period": "6months",
    "months_elapsed": 6,
    "path_a_cost": 1250000,
    "path_b_cost": 300000,
    "cost_difference": 950000,
    "audit_probability": 0.55,
    "expected_penalty": 520000,
    "expected_late_fee": 45800,
    "total_hidden_tax": 180000
  }, {
    "period": "1year",
    "months_elapsed": 12,
    "path_a_cost": 2850000,
    "path_b_cost": 300000,
    "cost_difference": 2550000,
    "audit_probability": 0.72,
    "expected_penalty": 1120000,
    "expected_late_fee": 136500,
    "total_hidden_tax": 360000
  }, {
    "period": "3years",
    "months_elapsed": 36,
    "path_a_cost": 10250000,
    "path_b_cost": 300000,
    "cost_difference": 9950000,
    "audit_probability": 0.94,
    "expected_penalty": 3980000,
    "expected_late_fee": 590000,
    "total_hidden_tax": 1080000
  }],
  "recommendation": "从成本差异分析，主动整改的财务合理性极高...",
  "loss_frame_message": "未来3年累计税务风险敞口可达1025万，远超当期30万整改成本...",
  "technical_summary": "path_a_3y=10.25M, path_b_3y=0.30M, ratio=34.2x, audit_prob=0.94",
  "case_references": [
    {"case_name": "某电商企业隐匿收入案", "penalty_amount": 8500000, "sentence": "3年"}
  ]
}
```

**前端扩展计算（指数雪球）：**

前端 `Simulator.tsx` 在收到后端数据后，进一步计算确定性雪球金额（非概率调整值）：
- **税金本金** = `monthly_hidden_revenue × comprehensive_tax_rate × months`
- **倍数罚金** = `税金本金 × (0.5|1.5|3.5|5.0)`
- **个税穿透** = `隐匿收入总额 × 20%`
- **滞纳金** = `税金本金 × 0.0005 × days`

**路径A = 税金本体 + 倍数罚金 + 个税穿透 + 复利滞纳金  
路径B = 合规整改投入（低平直线）**

### 4.2 获取同行业案例库

```http
GET /api/v1/case-studies
```

**说明：** 返回 `case_studies.json` 中的脱敏同行业税务处罚案例库。

---

## 5. 合规导航 🔐 auditor

> **计算引擎：** `tax_preference.py`（小微/高企优惠校验）、`compliance_adjustment.py`（合规调整评分）

```
基础路径: /api/v1/enterprises/{enterprise_id}
```

### 5.1 税收优惠校验

```http
GET /api/v1/enterprises/{enterprise_id}/tax-preference
```

**响应 `data` — `TaxPreferenceResult`：**

```json
{
  "is_small_micro": true,
  "small_micro_eligible": true,
  "small_micro_conditions": {
    "revenue": {"value": 47090000, "threshold": 50000000, "passed": true},
    "employees": {"value": 45, "threshold": 300, "passed": true},
    "total_assets": {"value": 35000000, "threshold": 50000000, "passed": true}
  },
  "is_high_tech": false,
  "high_tech_risk": null,
  "current_status": "符合小微企业标准",
  "industry_preferences": ["电子商务增值税3%简易征收"],
  "recommendations": ["建议申请小微企业税收优惠备案", "整理年度收入证明材料"],
  "business_narrative": "贵司年营收、从业人数、资产总额均符合...",
  "technical_summary": "revenue=47.09M<50M; employees=45<300; assets=35M<50M; eligible=True"
}
```

### 5.2 获取干预策略

```http
GET /api/v1/enterprises/{enterprise_id}/intervention
```

**说明：** 基于风险等级与合规调整结果生成分层干预策略（V4 §5.4：仅使用外部可观测的风险数据，不做心理画像推断）。

## 6. 整改追踪 🔐 admin

```
基础路径: /api/v1/enterprises/{enterprise_id} + /api/v1/remediation-tasks
```

### 6.1 获取整改任务列表

```http
GET /api/v1/enterprises/{enterprise_id}/remediation-tasks
```

### 6.2 创建整改任务

```http
POST /api/v1/enterprises/{enterprise_id}/remediation-tasks
```

**请求体 — `RemediationTaskCreate`：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | ✅ | 任务标题 |
| `description` | string | 否 | 任务描述 |
| `priority` | string | 否 | `high` / `medium` / `low` |
| `due_date` | date | 否 | 截止日期 |
| `risk_assessment_id` | UUID | 否 | 关联的风险评估ID |

### 6.3 更新任务状态

```http
PUT /api/v1/remediation-tasks/{task_id}
```

**请求体 — `RemediationTaskUpdate`：**

```json
{
  "status": "completed",
  "progress": 100
}
```

**完成时的附加响应：**

```json
{
  "comparison": {
    "before": {"overall_risk_score": 78.5, "assessment_date": "2025-07-14"},
    "after": {"overall_risk_score": 45.2, "assessment_date": "2025-08-15"}
  },
  "overall_risk_score": 45.2
}
```

### 6.4 获取任务详情

```http
GET /api/v1/remediation-tasks/{task_id}
```

### 6.5 人工验证确认（V4 §3.2）🔐 admin/auditor

```http
POST /api/v1/remediation-tasks/{task_id}/verify
```

整改率分子「已验证整改项」的认定入口：任务标记完成后，须经 admin 或
auditor 人工确认（单确认 + 备注留痕）其权重才计入整改率。

**请求体 — `RemediationTaskVerify`：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `note` | string | 否 | 验证确认备注（整改证据说明，留痕可回溯，≤2000 字） |

**口径约束：**

- 仅 `status=completed` 的任务可验证，否则返回 `40001`；
- 重复验证 → 更新验证人与备注（纠正留痕，幂等）；
- 任务被重置为非完成状态时，验证自动失效（清除 verified_by/at/note）。

---

## 7. 报告生成

```
基础路径: /api/v1/enterprises/{enterprise_id}/reports
```

### 7.1 生成综合风险报告

```http
POST /api/v1/enterprises/{enterprise_id}/reports/generate
```

**请求体 — `ReportGenerateRequest`：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `include_simulation` | boolean | 否 | 是否包含风险模拟结果 |

**响应 `data` — `Report`：**

```json
{
  "id": "uuid",
  "title": "创亿电子商务·综合税务风险评估报告",
  "report_type": "comprehensive",
  "generated_at": "2025-07-14T11:00:00Z",
  "content_summary": {"risk_level": "high", "is_fully_compliant": false}
}
```

### 7.2 获取报告列表

```http
GET /api/v1/enterprises/{enterprise_id}/reports
```

### 7.3 获取报告详情

```http
GET /api/v1/reports/{report_id}
```

### 7.4 下载报告（PDF）

```http
GET /api/v1/reports/{report_id}/download
```

**说明：** 返回 PDF 格式的综合风险评估报告文件。

---

## 8. AI 助手 🔐 viewer

> **LLM 服务：** `llm_service.py`（通用对话 + 报告润色）

```
基础路径: /api/v1/ai
```

### 8.1 智能对话

```http
POST /api/v1/ai/chat
```

**请求体 — `ChatRequest`：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `messages` | array | ✅ | 对话消息列表（OpenAI 格式） |
| `model` | string | 否 | 模型名称（`deepseek` / `qwen`，默认 `deepseek`） |

```json
{
  "messages": [
    {"role": "user", "content": "企业年度收入超过小微企业标准是否必须转为一般纳税人？"}
  ],
  "model": "deepseek"
}
```

### 8.2 报告润色

```http
POST /api/v1/ai/polish-report
```

**请求体 — `PolishReportRequest`：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `raw_text` | string | ✅ | 原始报告文本 |
| `context` | object | 否 | 上下文信息 |
| `style` | string | 否 | 风格：`professional` / `friendly` / `warning` |

---

## 9. 核定扣除计算

> **UI 状态：预留接口**（后端能力已备，前端页面二期接入，见附录 D）

乳业农产品核定扣除端到端计算（V4 §4.2）：路径判定 →『鲜奶』范围 →
单耗标准 → 扣除率路由（zen 决策图）→ Decimal 金额。自动路由成功时将
`calc_id` 与参数快照写入审计日志（证据链落库）。

### 9.1 执行核定扣除计算 🔐 viewer

```http
POST /api/v1/deemed-deduction/calculate
```

**请求体 — `DeemedCalcPayload`（数值字段以字符串承载，保 Decimal 精度）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `entity_is_pilot` | boolean | 否 | 是否核定扣除试点主体（默认 true） |
| `product_kind` | string | 否 | `uht`（灭菌乳）/ `pasteurized`（巴氏杀菌乳） |
| `animal` | string | 否 | 原料奶来源：`cow` / `goat` |
| `high_protein` | boolean | 否 | 是否高蛋白产品（单耗标准分档） |
| `sales_quantity` | string | ✅ | 当期销售货物数量（吨），数字字符串，须为正 |
| `avg_purchase_price` | string | ✅ | 购进农产品平均单价（万元/吨），数字字符串，须为正 |
| `product_name` | string | 否 | 产品名称（『鲜奶』范围判定；缺失 → 转人工） |
| `voucher_type` | string | 否 | 非试点路径凭证类型，取值见下方枚举表；白名单外 → 转人工 |

**`voucher_type` 枚举（对应 2026 年第 10 号公告第五条第（二）项，SSOT 为
`backend/app/core/deemed_deduction/fixtures/consumption_standards.json` 的 `invoice_path_cases`）：**

| 取值 | 情形 | 扣除率口径 |
|------|------|------------|
| `general_vat_invoice_or_customs` | ①取得增值税专用发票 / 海关进口增值税专用缴款书 | 凭票面注明税额抵扣（引擎不代算，回传 `rate=null`） |
| `small_scale_3pct_special_invoice` | ②简易计税 3% 征收率小规模纳税人开具的专票 | 发票注明金额 × 9% |
| `sales_or_purchase_invoice` | ③取得（开具）农产品销售发票 / 收购发票 | 买价 × 9%（默认值） |
| `coop_exempt_product` | ④从农民专业合作社购进的免税农产品 | 买价 × 9% |

> 仅非试点主体（`entity_is_pilot=false`）使用本字段；试点主体一律走核定扣除路径，
> 扣除率由产出货物适用税率决定，与本字段无关。传入上表之外的任意值 → 判定不确定 → `route=manual`。

**响应 `data`：**

```json
{
  "is_auto": true,
  "result": {
    "route": "auto",
    "input_vat": "3.53",
    "calc_id": "26fd7ab7…（SHA-256，同输入重算一致）",
    "rule_ids": ["VAT-INPUT-DEEMED-001"],
    "params_snapshot": {"context": "..."},
    "formula": "…"
  }
}
```

**口径约束：**

- `route=manual` 时不产出 `calc_id` 与金额，并给出转人工原因（禁止默认套用）；
- 非法/非正数值返回 `40001`。

---

## 10. 参数配置

> **UI 状态：预留接口**（参数治理面向管理员，配置页面二期接入，见附录 D）

### 10.1 获取全部参数 🔐 viewer

```http
GET /api/v1/risk-config
```

返回全部评分/阈值参数（含权威来源标注，多源互证）。

### 10.2 更新参数 🔐 admin

```http
PUT /api/v1/risk-config
```

**请求体：** `{ "config_key": new_value }`，仅接受已注册的参数键，未知键返回 `40001`；更新后风险扫描缓存全量失效。

> 注：`reduction_pct_per_task` / `reduction_pct_max` 两键自 V4 §3.2 方案 B
> （权重比整改率）起不再被引擎读取，仅为历史兼容保留。

---

## 11. 健康检查（公开，无需认证）

```http
GET /health
```

**响应：**

```text
OK
```

**状态码：** `200`

---

## 附录 A：请求/响应 Schema 速览

| Schema | 方法 | 说明 |
|--------|------|------|
| `EnterpriseCreate` | `POST /enterprises` | 创建企业 |
| `EnterpriseUpdate` | `PUT /enterprises/{id}` | 更新企业 |
| `SimulationRequest` | `POST .../simulate` | 风险模拟参数 |
| `RemediationTaskCreate` | `POST .../remediation-tasks` | 创建整改任务 |
| `RemediationTaskUpdate` | `PUT /remediation-tasks/{id}` | 更新任务 |
| `ReportGenerateRequest` | `POST .../reports/generate` | 生成报告 |
| `ChatRequest` | `POST /ai/chat` | AI 对话 |
| `PolishReportRequest` | `POST /ai/polish-report` | 报告润色 |

## 附录 B：CORS 配置

所有端点均允许跨域访问（开发环境）。生产环境通过 Nginx 反代统一管理。

## 附录 C：Rate Limiting（Nginx 层）

| 区域 | 限制 | burst |
|------|------|-------|
| 全局 | 10 req/s | 20 |
| `/api/` | 5 req/s | 10 |
| 登录/认证 | 1 req/s | 3 |

## 附录 D：端点 UI 接入状态（审计 #14）

后端已实现但**前端页面尚未接入**的端点清单（属"能力已备、UI 预留"，非断链）：

| 端点 | UI 状态 | 说明 |
|------|---------|------|
| `POST /api/v1/auth/register` | 预留 | 管理员后台开户流程二期接入 |
| `GET /api/v1/auth/me` | 预留 | 个人中心页二期接入 |
| `POST /api/v1/ai/chat` | 二期 | AI 对话界面（V4 一期不承诺对话 UI） |
| `POST /api/v1/ai/polish-report` | 二期 | 报告润色入口（V4 一期不承诺润色 UI） |
| `GET /enterprises/{id}/financial-statements` | 预留 | 财报导入向导二期接入 |
| `GET/PUT /api/v1/risk-config` | 预留 | 参数治理配置页二期接入（见 §10） |
| `POST /api/v1/deemed-deduction/calculate` | 预留 | 核定扣除工作台二期接入（见 §9） |

其余端点均已被前端页面调用（前后端 API 面一致性经脚本核对）。

---

*文档生成时间：2026-07-14*
*基于 `backend/openapi.json` 自动提取 + 手工业务注解整理*
*本文档与 [architecture.md](architecture.md)、[deployment.md](deployment.md)、[ai_collaboration_log.md](ai_collaboration_log.md) 共同构成项目技术文档体系。*
