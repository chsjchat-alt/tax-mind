# ══════════════════════════════════════════════════════════════════
#  税智·心判 — Railway 单容器多阶段构建
#  Stage 1: Node 20 构建 React 前端（frontend/dist）
#  Stage 2: Python 3.11 运行 FastAPI，托管前端静态产物 + API 同域
#
#  Railway 自动识别根目录 Dockerfile（Railpack 无法解析 docker-compose）。
#  数据库使用 Railway PostgreSQL，通过 DATABASE_URL 注入。
# ══════════════════════════════════════════════════════════════════

# ── Stage 1: 前端构建 ──────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ── Stage 2: 后端运行环境 ──────────────────────────
FROM python:3.11-slim AS runtime

# 中文字体（fpdf2 生成 PDF 报告必需，跨平台检测到 /usr/share/fonts/.../wqy）
# + libpq-dev（asyncpg 编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖以利用 Docker 层缓存
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝后端代码
COPY backend/ ./

# 拷贝前端构建产物（main.py 检测到 frontend/dist 后自动托管 + SPA fallback）
COPY --from=frontend-builder /build/dist /app/frontend/dist

# Railway 通过 PORT 指定监听端口
ENV PORT=8000

EXPOSE 8000

# 启动：等库 → alembic 迁移 → 种子数据（幂等）→ uvicorn
CMD ["sh", "start.sh"]
