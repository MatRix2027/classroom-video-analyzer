# ── 阶段1: 构建前端 ──
FROM node:22-alpine AS frontend-builder

WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY web/ ./
RUN npm run build

# ── 阶段2: Python应用 ──
FROM python:3.13-slim

# 安装FFmpeg和系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装Python依赖
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# 复制源码
COPY src/ ./src/
COPY config/ ./config/
COPY prompts/ ./prompts/

# 复制前端构建产物
COPY --from=frontend-builder /app/web/dist ./web/dist/

# 环境变量（通过Render/Railway的环境变量面板配置）
# API_KEYS_JSON - 完整的API密钥配置JSON
# PORT - 服务端口（Render自动设置）

EXPOSE 8001

CMD ["uvicorn", "classroom_analyzer.server.app:app", "--host", "0.0.0.0", "--port", "8001"]
