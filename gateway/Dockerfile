# Stage 1: Builder - install dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime - copy installed packages and source code
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local

COPY . /app/gateway

EXPOSE 8000

CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
