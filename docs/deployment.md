# 蒙牛全产业链 AI 内生合规决策大脑 — 部署与运维手册

> 等保 2.0 三级 | Docker Compose 一键编排 | TLS 1.3 强制加密 | DDoS 防护

---

## 目录

- [1. 系统要求](#1-系统要求)
- [2. 一键启动](#2-一键启动)
- [3. 环境变量](#3-环境变量)
- [4. 容器编排栈](#4-容器编排栈)
- [5. 模拟数据播种](#5-模拟数据播种)
- [6. 健康检查与验证](#6-健康检查与验证)
- [7. 生产加固清单](#7-生产加固清单)
- [8. 常见问题排查](#8-常见问题排查)
- [9. 生产覆盖配置（docker-compose.prod.yml）](#9-生产覆盖配置docker-composeprodyml)
- [10. CI/CD 集成](#10-cicd-集成)

---

## 1. 系统要求

| 组件 | 最低版本 | 说明 |
|---|---|---|
| Docker | 20.10+ | 容器运行时 |
| Docker Compose | 2.0+ | 编排工具 |
| Python | 3.11+ | 本地开发 / 数据播种脚本 |
| Node.js | 20+ | 前端构建（本地开发） |
| PostgreSQL Client | 15+ | 仅需 `pg_isready`（start.sh 健康检查用） |

**资源建议**（生产环境）：

| 资源 | 最小值 | 建议值 |
|---|---|---|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 磁盘 | 20 GB（不含数据量） | 50 GB+ |

---

## 2. 一键启动

### 2.1 克隆项目

```bash
git clone <repo-url> taxmind
cd taxmind
```

### 2.2 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env
```

编辑 `.env`，至少确保以下变量值安全：

```ini
# 数据库密码（生产环境务必更换）
POSTGRES_PASSWORD=your_strong_password_here

# 大模型 API Key（原型阶段可不填，系统降级为 Mock）
DEEPSEEK_API_KEY=sk-xxxxxxxx
LLM_PROVIDER=deepseek
```

### 2.3 启动全部服务

```bash
docker compose up -d
```

首次启动会自动构建镜像（约 3-5 分钟），后续启动仅需数秒。

### 2.4 查看运行状态

```bash
# 容器状态
docker compose ps

# 实时日志
docker compose logs -f

# 仅看特定服务
docker compose logs -f backend
```

### 2.5 停止服务

```bash
# 停止（保留数据卷）
docker compose down

# 停止并删除数据卷（重置全部数据）
docker compose down -v
```

---

## 3. 环境变量

### 3.1 必需变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `POSTGRES_DB` | `taxmind` | 数据库名称 |
| `POSTGRES_USER` | `taxmind` | 数据库用户 |
| `POSTGRES_PASSWORD` | `taxmind123` | 数据库密码（**生产必须修改**） |

### 3.2 后端配置

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` | 由 docker-compose 自动拼接，**无需手动设置** |
| `APP_NAME` | `蒙牛全产业链 AI 内生合规决策大脑` | 应用标识 |
| `APP_VERSION` | `0.3.0` | 版本号 |
| `DEBUG` | `false` | 生产环境必须 `false` |
| `DB_POOL_SIZE` | `20` | 数据库连接池大小 |
| `DB_MAX_OVERFLOW` | `10` | 连接池溢出上限 |
| `LLM_PROVIDER` | `deepseek` | 大模型提供商（`deepseek` / `qwen`） |
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key |
| `QWEN_API_KEY` | — | 通义千问 API Key |
| `LLM_TIMEOUT` | `30` | LLM 请求超时（秒） |
| `LLM_MAX_RETRIES` | `3` | LLM 失败重试次数 |

### 3.3 本地开发覆盖

本地开发可使用 `backend/.env.example` 覆盖服务器地址：

```bash
# 本地使用 SQLite（免 PostgreSQL）
DATABASE_URL=sqlite+aiosqlite:///./taxmind.db

# 本地连接 Docker PostgreSQL
DATABASE_URL=postgresql+asyncpg://taxmind:taxmind123@localhost:5432/taxmind
```

---

## 4. 容器编排栈

### 4.1 架构图

```
 ┌──────────────────────────────────────────────────────┐
 │                    Internet                          │
 │                      │                               │
 │              :80 / :443 (TLS 1.3)                    │
 │                      │                               │
 │  ┌───────────────────▼──────────────────────────┐   │
 │  │  frontend (Nginx + React SPA)                │   │
 │  │  - TLS 终结                                  │   │
 │  │  - /api/* → backend:8000                     │   │
 │  │  - DDoS Rate Limiting (10 req/s)             │   │
 │  │  - Security Headers (HSTS, CSP, XSS)         │   │
 │  └───────────────────┬──────────────────────────┘   │
 │                      │ 内部网络 taxmind-net          │
 │  ┌───────────────────▼──────────────────────────┐   │
 │  │  backend (FastAPI + Uvicorn) ×2 replicas     │   │
 │  │  - :8000 (仅内网暴露)                        │   │
 │  │  - 只读根文件系统 + no-new-privileges        │   │
 │  └───────────────────┬──────────────────────────┘   │
 │                      │                              │
 │  ┌───────────────────▼──────────────────────────┐   │
 │  │  postgres (PostgreSQL 15 Alpine)              │   │
 │  │  - scram-sha-256 认证                        │   │
 │  │  - 数据持久化卷                               │   │
 │  │  - 仅内网:5432                                │   │
 │  └──────────────────────────────────────────────┘   │
 └──────────────────────────────────────────────────────┘
```

### 4.2 服务清单

| 服务 | 镜像 | 端口 | 副本 | CPU 限 | 内存限 |
|---|---|---|---|---|---|
| `postgres` | `postgres:15-alpine` | 5432（内网） | 1 | 1.0 | 512M |
| `backend` | 本地构建 | 8000（内网） | 2 | 1.0 | 512M |
| `frontend` | 本地构建 | 80, 443（公网） | 1 | 0.5 | 256M |

### 4.3 网络

- `taxmind-net`：桥接网络，子网 `172.28.0.0/16`
- 仅 `frontend` 暴露公网端口（零信任原则）
- PostgreSQL 和 Backend 完全内网隔离

---

## 5. 模拟数据播种

### 5.1 播种器简介

[`scripts/mock_desensitized_data_seeder.py`](file:///d:/安永/tax/scripts/mock_desensitized_data_seeder.py) 基于 Faker 库动态生成 ≥50 家企业的完整涉税账套数据，覆盖：

- **重资产行业**：制造、建筑（固定资产折旧率 30%-50%，大额设备采购流水）
- **轻资产行业**：新零售电商、批发零售、餐饮服务（高频无形劳务进项 + 个人账户资金划转）

**安全红线**：所有数据均为自行构造的模拟数据，PII（法人姓名/身份证/银行账号）已不可逆星号掩码。

### 5.2 通过 Docker 执行（推荐）

```bash
# 播种 50 家企业（默认）
docker compose exec backend python scripts/mock_desensitized_data_seeder.py

# 自定义数量
docker compose exec backend python scripts/mock_desensitized_data_seeder.py --count 10

# 预览模式（仅输出不写入数据库）
docker compose exec backend python scripts/mock_desensitized_data_seeder.py --dry-run
```

### 5.3 本地执行

```bash
# 先确保已安装依赖
cd backend
pip install -r requirements.txt

# 需要先将 DATABASE_URL 指向运行中的 PostgreSQL
export DATABASE_URL=postgresql+asyncpg://taxmind:taxmind123@localhost:5432/taxmind

# 执行播种
python scripts/mock_desensitized_data_seeder.py --count 50
```

### 5.4 验证播种结果

```bash
# 检查企业数量
docker compose exec postgres psql -U taxmind -d taxmind -c \
  "SELECT industry, COUNT(*) FROM enterprises GROUP BY industry ORDER BY industry;"
```

预期输出（50 家企业，各行业 ~10 家）：

```
制造        | 10
建筑        | 11
批发零售    | 9
电商        | 10
餐饮服务    | 10
```

---

## 6. 健康检查与验证

### 6.1 健康检查端点

```bash
# 前端 Nginx
curl http://localhost/health
# → OK

# 后端 API
curl http://localhost/api/v1/health
# → {"code": 200, "message": "success", "data": {"status": "ok", "version": "0.3.0"}}

# 前端 SPA
curl -I http://localhost/
# → HTTP/1.1 200 OK (index.html)
```

### 6.2 功能验证

```bash
# 1. 获取企业列表（验证 API + DB 连通性）
curl http://localhost/api/v1/enterprises | python -m json.tool

# 2. 注册测试企业
curl -X POST http://localhost/api/v1/enterprises \
  -H "Content-Type: application/json" \
  -d '{
    "name": "测试企业",
    "credit_code": "91330100MA12345678",
    "industry": "批发零售",
    "revenue_annual": 5000000,
    "tax_rate_claimed": 0.03,
    "cost_rate_claimed": 0.80
  }'

# 3. 执行风险扫描（替换 <enterprise_id>）
curl -X POST http://localhost/api/v1/enterprises/<enterprise_id>/risk-scan
```

### 6.3 Docker 内置健康检查

Docker Compose 已配置 `healthcheck`，可通过 `docker compose ps` 查看：

```bash
docker compose ps
# 正常输出：
# NAME           STATUS
# taxmind-db     Up (healthy)
# taxmind-api    Up (healthy)
# taxmind-web    Up (healthy)
```

健康检查不通过时服务不会启动（`depends_on` 设置了 `condition: service_healthy`）。

---

## 7. 生产加固清单

部署到生产环境前请逐项确认：

- [ ] **数据库密码**：已修改为强密码（`POSTGRES_PASSWORD`）
- [ ] **TLS 证书**：
  ```bash
  # 使用 Let's Encrypt 签发免费证书
  docker compose run --rm certbot certonly --webroot \
    -w /var/www/certbot -d your-domain.com
  # 替换 frontend/nginx.conf 中 ssl_certificate 路径
  ```
- [ ] **TLS 禁用 1.0/1.1**：`nginx.conf` 已配置仅 `TLSv1.2 TLSv1.3`
- [ ] **多副本**：`docker-compose.yml` 中 `backend.deploy.replicas: 2`
- [ ] **DDoS 限流**：Nginx 已配置 （10 req/s 全局 + 5 req/s API + 1 req/s 敏感接口）
- [ ] **安全头**：HSTS (`max-age=63072000`)、CSP、X-Frame-Options、Referrer-Policy 已就绪
- [ ] **零信任网络**：仅 Nginx 暴露公网端口，DB 和 API 仅在内网
- [ ] **只读文件系统**：`backend` 容器已启用 `read_only: true`
- [ ] **禁止提权**：所有容器已设置 `no-new-privileges:true`
- [ ] **日志审计**：Nginx 访问日志包含真实 IP + 上游响应时间
- [ ] **定期备份**：
  ```bash
  docker compose exec postgres pg_dump -U taxmind taxmind > backup_$(date +%Y%m%d).sql
  ```

---

## 8. 常见问题排查

### 8.1 Docker Compose 启动失败

**现象**：`docker compose up -d` 报错或服务反复重启

**排查步骤**：

```bash
# 1. 查看全部容器状态
docker compose ps -a

# 2. 查看具体服务日志
docker compose logs postgres
docker compose logs backend
docker compose logs frontend

# 3. 确认端口未被占用
netstat -ano | findstr ":80"
netstat -ano | findstr ":443"
netstat -ano | findstr ":5432"
```

### 8.2 PostgreSQL 连接拒绝

**现象**：`backend` 日志显示 `could not translate host name "postgres"` 或 `connection refused`

**原因**：PostgreSQL 尚未就绪时 Backend 抢先启动。

**解决**：docker-compose 已配置 `depends_on: condition: service_healthy`，正常情况下会等待。若仍出现，手动重启：

```bash
docker compose restart backend
```

### 8.3 数据库表不存在

**现象**：API 返回 `relation "enterprises" does not exist`

**原因**：首次启动时 `init_db()` / Alembic 迁移未执行。

**解决**：

```bash
# 方式一：重启 Backend（自动执行 startup 建表）
docker compose restart backend

# 方式二：手动执行建表
docker compose exec backend python -c "import asyncio; from app.database import init_db; asyncio.run(init_db())"
```

### 8.4 镜像构建失败

**现象**：`docker compose build` 报错

**常见原因**：

| 错误 | 原因 | 解决 |
|---|---|---|
| `pip install` 超时 | 网络问题 | 设置国内镜像：`RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple ...` |
| `npm install` / `npm run build` 失败 | Node 版本或内存不足 | 确认 `node:20-alpine`；给 Docker 分配 ≥ 2GB 内存 |
| `COPY failed: file not found` | 构建上下文不完整 | 检查 `.dockerignore` 是否排除了必要文件 |

### 8.5 Nginx 502 Bad Gateway

**现象**：访问页面返回 502

**排查**：

```bash
# 1. 确认 Backend 健康
curl http://localhost:8000/health
# 或
docker compose exec backend python -c "import httpx; print(httpx.get('http://localhost:8000/health').text)"

# 2. 检查 Nginx upstream 能否解析 backend 主机名
docker compose exec frontend ping -c 1 backend

# 3. 查看 Nginx 错误日志
docker compose exec frontend tail -f /var/log/nginx/error.log
```

### 8.6 数据播种失败

**现象**：`mock_desensitized_data_seeder.py` 报错 `Faker` 或数据库连接错误

**排查**：

```bash
# 确定 Faker 依赖已安装
docker compose exec backend pip show faker

# 测试数据库连接
docker compose exec backend python -c "
import asyncio
from app.database import engine
async def test():
    async with engine.connect() as conn:
        result = await conn.execute('SELECT 1')
        print('DB OK:', result.fetchone())
asyncio.run(test())
"
```

### 8.7 大模型调用失败

**现象**：AI 助手接口返回 LLM 相关错误

**排查**：

```bash
# 查看后端日志中的 LLM 错误
docker compose logs backend | grep -i "llm\|deepseek\|qwen"

# 验证 API Key
docker compose exec backend python -c "
import os; print('DEEPSEEK_API_KEY set:', bool(os.getenv('DEEPSEEK_API_KEY')))
"
```

**说明**：未配置 API Key 时，系统降级为 Mock 模式，不影响核心功能（风险扫描、合规干预、模拟引擎）使用。

### 8.8 重置到初始状态

```bash
# 停止并删除所有容器、网络、数据卷
docker compose down -v

# 清理构建缓存（如有需要）
docker builder prune -f

# 重新构建启动
docker compose build --no-cache
docker compose up -d
```

---
## 9. 生产覆盖配置（docker-compose.prod.yml）

项目提供 `docker-compose.prod.yml` 作为生产环境的覆盖配置，用于叠加在基础 `docker-compose.yml` 之上，添加生产级运维组件。

### 9.1 用法

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Docker Compose 会自动合并两份文件，`docker-compose.prod.yml` 中的配置覆盖基础文件中的同名服务设置。

### 9.2 生产覆盖提供的额外能力

| 能力 | 说明 |
|------|------|
| **DB 自动备份** | 新增 `backup` 服务，每日凌晨 2:00 (UTC) 自动执行 `pg_dump` 备份，保留 30 天 |
| **TLS 证书** | PostgreSQL TLS 加密 (`ssl=on`) + Nginx TLS 证书挂载 |
| **多副本** | Backend 副本数从 2 提升至 3，提升高可用性 |
| **Rate Limiting** | Nginx 层 API 限流 (`30r/m` per IP) |
| **连接池调优** | `DB_POOL_SIZE=50`，`DB_MAX_OVERFLOW=20` |
| **DB SSL 强制** | `DB_SSL_MODE=require` 确保数据库传输加密 |
| **内存提升** | Backend 容器内存限制从 512M 提升至 1024M |

### 9.3 服务清单（覆盖后）

| 服务 | 变更 |
|------|------|
| `postgres` | 启用 TLS，挂载 SSL 证书，日志增强 |
| `backend` | 副本 3，池大小 50，内存 1G，健康检查 10s 间隔 |
| `frontend` | 挂载 TLS 证书，启用 API 限流 |
| `backup` | **新增** — PostgreSQL 定时备份服务 |

---
## 10. CI/CD 集成

项目使用 GitHub Actions 自动化流水线（[`.github/workflows/main_deploy.yml`](file:///d:/安永/tax/.github/workflows/main_deploy.yml)）：

### 流水线阶段

| 阶段 | 说明 | 阻断条件 |
|---|---|---|
| **代码质量** | Ruff 代码规范检查 + Bandit 安全扫描 | 风险等级 ≥ HIGH |
| **单元测试** | pytest + coverage（≥90%） | 任意测试失败 |
| **容器构建** | Docker 镜像构建 | 构建失败 |
| **部署** | 推送到服务器 | 以上阶段全部通过 |

### 覆盖率要求

```
core 模块: ≥ 90% (pytest --cov=app/core --cov-fail-under=90)
API 层:   完整端点测试 (httpx.AsyncClient)
E2E:      条件触发 (RUN_E2E_TESTS=1)
```

### 手动触发部署

```bash
# 本地构建 + 测试
docker compose build
pytest tests/ --cov=app --cov-fail-under=90

# 推送到生产服务器（需配置 SSH + Docker Registry）
docker compose push
ssh prod-server "cd /opt/taxmind && docker compose pull && docker compose up -d"
```
