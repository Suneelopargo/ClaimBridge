# --------------------------------------------------------
# ClaimBridge Backend
# FastAPI + Playwright + Microsoft Graph
# --------------------------------------------------------

FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium
COPY . .

# Create folders used by the application
RUN mkdir -p \
    /app/data \
    /app/logs \
    /app/downloads \
    /app/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]