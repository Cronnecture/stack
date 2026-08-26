FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY master_orchestrator.py /app/master_orchestrator.py
COPY core/ /app/core/
COPY monitoring/ /app/monitoring/
COPY integrations/ /app/integrations/

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command is overridden per Deployment.
CMD ["python", "/app/master_orchestrator.py", "--daemon"]
