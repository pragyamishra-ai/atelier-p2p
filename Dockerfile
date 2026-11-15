FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr poppler-utils libpango-1.0-0 libpangoft2-1.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv sync --extra datagen --extra extraction --extra warehouse --extra copilot --extra app
COPY . .
EXPOSE 8501
CMD ["uv", "run", "streamlit", "run", "src/p2p/app/main.py", "--server.address=0.0.0.0"]
