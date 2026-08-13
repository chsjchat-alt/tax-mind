# 测试运行与覆盖率报告说明

本文档说明如何运行本项目的测试套件、生成覆盖率报告以及查看报告。

项目结构：

```
tax/
├── backend/                  # Python FastAPI 后端
│   ├── pytest.ini            # pytest 与 pytest-cov 配置
│   ├── tests/                # pytest 单元/接口测试
│   └── htmlcov/              # 后端覆盖率 HTML 报告（运行后生成）
└── frontend/                 # React (Vite/TS/AntD) 前端
    ├── package.json          # 含 test / test:ci 脚本
    ├── vitest.config.ts      # vitest 与覆盖率配置
    └── coverage/             # 前端覆盖率 HTML 报告（运行后生成）
```

---

## 1. 后端测试（Python / pytest）

### 1.1 环境准备

```bash
cd backend
pip install -r requirements.txt
```

依赖包含 `pytest`、`pytest-asyncio`、`pytest-cov`。

### 1.2 运行全部测试

```bash
cd backend
python -m pytest
```

pytest 配置位于 [backend/pytest.ini](backend/pytest.ini)，默认行为：

- 指定 `testpaths = tests`
- 开启 `asyncio_mode = auto`（async 测试无需手动加标记）
- **自动忽略** `tests/test_simulation_engine.py`：该文件导入不存在的
  `PENALTY_MULTIPLIERS` 属存量 collection error，会中断整个测试流程；
  修复后应从 `pytest.ini` 的 `--ignore` 中移除。
- **自动开启覆盖率统计**（pytest-cov），针对三个核心引擎模块：

  | 模块 | 说明 |
  |---|---|
  | `app.core.tax_risk_engine` | 五维全景税务风险评估引擎 |
  | `app.core.ssf_analyzer` | SSF 博弈状态分析引擎 |
  | `app.core.compliance_checker` | 财务数据合规校验引擎 |

### 1.3 只运行指定测试

```bash
# 单个文件
python -m pytest tests/test_tax_risk_engine.py

# 单个用例
python -m pytest tests/test_ssf_analyzer.py::TestComputeTrustCoord
```

### 1.4 覆盖率报告

- 终端摘要：每次 `pytest` 运行后自动打印 `term-missing` 表格（含未覆盖行号）。
- HTML 报告：每次运行后写入 `backend/htmlcov/`，浏览器打开

  ```
  backend/htmlcov/index.html
  ```

- 目标覆盖率（三个引擎模块核心函数）为 **≥ 80%**，当前状态：

  | 模块 | 覆盖率 |
  |---|---|
  | compliance_checker | 100% |
  | ssf_analyzer | 100% |
  | tax_risk_engine | 98% |

### 1.5 已知存量问题（非本次改动引入）

- `tests/test_api/*` 中部分用例报 `enterprises.tenant_id` NOT NULL：
  多租户 schema 改造后测试夹具未携带 `tenant_id`，属存量问题。
- Windows 下临时 SQLite 文件删除偶发文件句柄锁（WinError 32）：
  已在 `tests/test_api/conftest.py` teardown 中增加重试机制缓解。

---

## 2. 前端测试（TypeScript / Vitest）

### 2.1 环境准备

```bash
cd frontend
npm install
```

### 2.2 运行测试

| 命令 | 说明 |
|---|---|
| `npm test` | 运行全部单元测试（`vitest run`） |
| `npm test -- --watch` 或 `npm run test:watch` | 监听模式 |
| `npm run test:ci` | 运行全部测试并生成覆盖率报告（`vitest run --coverage`） |

### 2.3 覆盖率报告

`test:ci` 使用 v8 覆盖率提供器（`@vitest/coverage-v8`），配置见
[frontend/vitest.config.ts](frontend/vitest.config.ts)：

- 统计范围：`src/**/*.{ts,tsx}`
- 排除：测试文件、`src/tests/**`、mock 目录、`main.tsx`、`vite-env.d.ts`
- 输出：终端 `text` 表格 + HTML 报告

浏览器打开：

```
frontend/coverage/index.html
```

---

## 3. 回归基线流程（每次改动必跑）

任何改动提交前，先确认以下基线保持绿：

```bash
# 前端：类型检查 + 全部单元测试
cd frontend
npx tsc --noEmit
npx vitest run

# 后端：全部测试 + 覆盖率
cd backend
python -m pytest
```

基线要求：

- `npx tsc --noEmit` 0 错误；
- 前端 `npx vitest run` 全绿（当前 5 文件 / 67 用例）；
- 后端 `python -m pytest` 无**新增**失败（存量 4 failed / 21 errors 属
  `tests/test_api` 的 tenant_id 夹具问题，见 §1.5）；
- 安全修复必须配套防回归测试。
