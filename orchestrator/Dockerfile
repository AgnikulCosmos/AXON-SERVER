FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ /app/common/
COPY orchestrator/ /app/

ENV PYTHONPATH=/app

CMD ["uvicorn", "orchestrator.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
