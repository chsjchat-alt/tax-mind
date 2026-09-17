# 开源组件集成说明（OPEN_SOURCE_INTEGRATION.md）

> 对应《蒙牛AI创新_方案_迭代版V4.md》§九（验收指标）与 §十一（Rule ID 法规治理矩阵）。
> 本文档记录本次引入的全部开源依赖、选型依据、许可证、集成步骤与已踩过的坑。

---

## 一、依赖总览

| 依赖 | 版本 | 许可证 | 来源仓库 | 定位 |
|---|---|---|---|---|
| zen-engine | 2.0.x（`>=2.0,<2.1`） | MIT | gorules/zen（约 1980★，持续维护） | Rule ID 执行层：决策表/表达式图引擎，承担**定性路由**（扣除率档位、范围判定、转人工路由） |
| rapidfuzz | 3.x（`>=3.0,<4.0`） | MIT | rapidfuzz/RapidFuzz（约 4120★） | 四流稽核品名匹配的**受控增强层**（token_set_ratio 双分数对照） |
| pdfplumber | 0.11.x（`>=0.11,<0.12`） | MIT | jsvine/pdfplumber（约 10736★） | 同期资料 PDF 文本抽取（TP 工作台上传附件解析） |

**未引入（二期可选）**：
- PaddleOCR（Apache-2.0，约 89363★）：扫描件 PDF 无文本层时的 OCR 路径，二期按需引入；
- chroma（Apache-2.0，约 29283★）：向量检索/知识库语义召回，二期按需引入。注意其为 Rust 内核，Python 版与 Rust 版存在**版本对齐坑**，引入时须锁定客户端与服务端版本。

**评估后未采用**：
- pandera（MIT）：数据校验框架，本项目无 pandas 数据层，引入反而增加依赖面。

## 二、铁律：税额计算绝不交给规则引擎

**架构红线**：zen-engine 只做定性路由（`0.09` 档位、`ROUTE_TO_MANUAL` 说明等），
**所有金额计算（进项税额、罚金、风险敞口）一律在 Python 层用 `decimal.Decimal`
+ `ROUND_HALF_UP`（量化到分）完成**。规则引擎的输出仅作为路由结论被消费，
浮点结果不参与任何算术。

实现位置：`app/core/deemed_deduction/engine.py`
（`calc_input_output_method` / `calc_cost_method` / `calc_invoice_path_amount`）。

## 三、集成步骤（复现指南）

### 3.1 安装

```bash
cd tax/backend
pip install -r requirements.txt
```

### 3.2 Rule ID 法规治理矩阵

1. 法规条目登记在 `app/core/rule_governance/fixtures/rules.json`（17 条，覆盖
   增值税法豁免、核定扣除、发票路径、个税礼物、已废止文号等）；
2. `RuleRegistry.load_default()` 加载注册表；任何规则执行前先过闸门：
   - `status` 非 active（repealed/superseded/dynamic）→ 拦截；
   - `on_date` 不在 `[effective_from, effective_to]` → 拦截；
   - `review != human_verified`（如省级补丁 pending_refresh）→ 拦截；
   - 批量闸门 `require_all_executable` 原子生效：一条失效即整体不可执行；
3. 通过闸门后由 `RuleExecutor.execute()` 调 zen 执行决策图，产出
   `CalculationResult`（calc_id + 参数快照 + 结果）或 `ManualRoute`。

### 3.3 核定扣除引擎（乳业试点）

1. 单耗标准登记在 `app/core/deemed_deduction/fixtures/consumption_standards.json`
   （38号文附件2 六系数 + 鲜奶范围口径 + 发票路径三情形 + 省级补丁占位）；
2. 主链路 `run_deemed_calculation()`：
   闸门 → 抵扣路径判定（试点身份优先）→ 鲜奶范围判定 → 单耗系数 →
   扣除率路由（zen 决策表）→ Decimal 金额计算；
3. 任一环节不确定（范围外产品、未知凭证、未知品名）→ `route="manual"`
   并给出原因，**绝不默认套用 9%**。

### 3.4 四流稽核增强层

`app/core/four_flow_match.py` 新增 `calculate_product_match_dual()`：
- 原 Jaccard 评分路径**完全不动**（阈值常量 2%/10%/30% 不变）；
- rapidfuzz `token_set_ratio` 作为对照分数（对每个进项品名取与全部销项品名
  的最佳分，再对进项序列取算术平均）；
- rapidfuzz 未安装时优雅降级（`available=False`），不影响主链路。

### 3.5 审计证据链字段

`app/models/audit_log.py` 新增两列（迁移 `alembic/versions/009_add_audit_calc_snapshot.py`）：
- `calculation_id`（String(64)，索引）：本次计算的确定性指纹；
- `param_snapshot`（Text）：规则三元组 + 引擎版本 + 输入参数的规范 JSON 快照。

```bash
alembic upgrade head   # 应用 009 迁移
```

## 四、calc_id 确定性设计（验收指标：重算一致率 100%）

```
calc_id = SHA-256( 规范JSON{ rule_ids, graph_sha256, context, on_date, engine_version } )
```

- 规范化：`json.dumps(..., sort_keys=True, separators=(",", ":"))`；
- **不含任何墙钟时间**：同参数、同规则版本、同图版本 → calc_id 恒等；
- 规则/图任一变更 → calc_id 变化 → 天然构成"计算指纹"审计链。

测试：`tests/test_rule_governance.py::TestExecutor::test_recalc_agreement_100pct`。

## 五、已踩过的坑（zen-engine 2.x 专项）

以下全部经实际运行验证（2026-09，zen-engine 2.0.2）：

1. **模块改名**：2.x 起 `import zen`（PyPI 包名仍是 `zen-engine`，
   `import zen_engine` 会 ModuleNotFoundError）。
2. **版本断层**：0.53.0 之后是 1.0.0b* 测试线，再之后才是 2.0.x 稳定线；
   锁定 `>=2.0,<2.1` 避免落到 beta。
3. **图 schema**：顶层键是 `nodes` + `edges`（不是 `links`）；边用
   `sourceId`/`targetId`（不是 `source`/`target`）；节点 `id` 必须是**字符串**
   （数字 id 报 `invalid type: number, expected a string`）。
4. **`decisionNode` 是引用型**：内联规则必须用 `expressionNode` 或
   `decisionTableNode`（带完整 content），`decisionNode` 需要 loader，内联
   content 会报 `Loader is not defined`。
5. **决策表 content**：`key` 在 content 顶层；规则行键名为 `i1..x` / `o1..x`
   （inputs/outputs 的 id 序号），`hitPolicy: "first"`。
6. **返回值是 dict**：`decision.evaluate(context)` 返回 `{"result": {...},
   "performance": ...}`；因 `passThrough: true`，输入参数也在结果里，图的输出
   （`result.rate` 字段）嵌套在 `result["result"]` 命名空间下——取值须
   `result["result"]["rate"]`。
7. **参考实现**：以官方 `bindings/python/test_sync.py` 与
   `test-data/graphs/tax-exemption.json` 为准，勿凭旧文档猜 schema。

## 六、其他已知局限

- **rapidfuzz 中文品名**：需先做一致的规范化（全半角、大小写、单位词剥离），
  否则 token_set_ratio 会被无关 token 干扰；`_normalize_product_text` 已统一。
- **pdfplumber**：只能抽取有文本层的 PDF；扫描件（图片型）须走 OCR（二期 PaddleOCR）。
- **AGRI-DEEM-PROV-TEMPLATE（省级补丁）**：刻意登记为 `pending_refresh`，
  用于验证"未经复核签发的规则不得自动执行"闸门，省级细则发布后由人工替换。

## 七、验收指标映射（V4 §九）

| 验收指标 | 实现与测试 |
|---|---|
| 失效/未复核规则必须挂起自动计算 | 闸门 + 原子批量检查；`TestGates`（repealed/superseded/区间外/pending_refresh 全拦截） |
| 相同输入下重算一致率 100% | calc_id 确定性设计；`test_recalc_agreement_100pct` 与端到端可复现性测试 |
| 范围外产品不默认套用 9% | 决策表 r2 规则 + `run_deemed_calculation` manual 路由；`test_yogurt_routes_manual` 等 |
| 试点范围内不得改按普通凭票路径 | `identify_purchase_path` 试点身份优先；路径 notes 显式声明 |
| 金额全 Decimal | `calc_input_output_method` 等 + 全测试断言 `Decimal` 精确值（308.64 / 25596.33 / 304.89 / 900.00） |
| 审计证据链 | audit_log 新增 calculation_id + param_snapshot（009 迁移） |

## 八、本地验证记录（2026-09-12）

- 新增测试 46 个全部通过（`test_rule_governance.py` 15 个 + `test_deemed_deduction.py` 31 个）；
- 全量回归 `pytest tests`：**484 passed, 8 skipped, 0 failed**（skip 为需真实 PostgreSQL 的用例）；
- 覆盖率：compliance_checker 100% / tax_risk_engine 98%。
