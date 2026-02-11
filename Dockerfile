# GrayScope 灰盒测试分析平台 - 后端 Docker 镜像
# 适用于 X86 Linux 服务器部署

FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖（tree-sitter 编译需要 build-essential，git 用于 diff 分析）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential && \
    rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY backend/app ./app

# 复制提示词模板（如有）
COPY backend/prompt_templates ./prompt_templates 2>/dev/null || true

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 18080

# 启动后端服务，绑定 0.0.0.0 允许内网访问
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "18080"]
