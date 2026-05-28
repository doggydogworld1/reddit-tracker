FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser

COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser config.py database.py scraper.py analyzer.py scheduler.py app.py discoverer.py ./
COPY --chown=appuser:appuser templates/ ./templates/

RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 5050

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/', timeout=3)"

CMD ["python", "app.py"]