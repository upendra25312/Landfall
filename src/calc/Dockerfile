# ca-calc — drives the real Azure Pricing Calculator with Playwright and returns
# its Excel export (PRD E11.16). Chromium + the Playwright runtime are large and
# cannot run in the Flex Consumption Function, so this is a scale-to-zero
# Container App side-car (same pattern as ca-deckgen).
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8080 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
