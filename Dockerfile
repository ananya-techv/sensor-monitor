FROM python:3.12-slim

WORKDIR /code
# Copy requirements first: Docker caches this step, so rebuilds are fast when only code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY simulator ./simulator

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
