FROM python:3.11-slim

WORKDIR /app

COPY requirements-runtime.txt /app/requirements-runtime.txt
RUN pip install --no-cache-dir -r /app/requirements-runtime.txt

COPY src /app/src
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "cronnecture_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
