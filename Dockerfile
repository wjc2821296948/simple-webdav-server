FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md LICENSE ./
COPY simple_webdav ./simple_webdav

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["simple-webdav-server", "--config", "/app/config.yaml"]
