# Stage 1: Install Playwright browsers
FROM python:3.11-slim as playwright-deps
RUN pip install playwright
RUN python3 -m playwright install chromium
RUN python3 -m playwright install-deps chromium

# Stage 2: Runtime
FROM python:3.11-slim
WORKDIR /app
COPY --from=playwright-deps /root/.cache /root/.cache
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
RUN python3 -c "import playwright; print('playwright OK')"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
