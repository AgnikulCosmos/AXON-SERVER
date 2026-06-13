FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api.py main.py /app/
COPY common/ /app/common/
COPY services/ /app/services/
COPY orchestrator/ /app/orchestrator/
COPY prompts/ /app/prompts/

ENV PYTHONPATH=/app

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
