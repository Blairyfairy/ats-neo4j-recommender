FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ scripts/
COPY data/ data/
COPY index.html .
COPY web/ web/

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Ingest into AuraDB, score outliers, then serve the static recommendation page
CMD ["sh", "-c", "python scripts/parse_and_ingest.py && python scripts/process_outliers.py --min-score 55 --max-missing 2 --pct-low 5 --pct-high 10 && python -m http.server ${PORT} --directory web"]
