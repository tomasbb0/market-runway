FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pipeline/requirements.txt /app/pipeline/requirements.txt
RUN pip install -r /app/pipeline/requirements.txt gunicorn==23.0.0
COPY pipeline /app/pipeline
RUN mkdir -p /app/pipeline/workspaces /app/pipeline/cache
EXPOSE 8765
# one worker on purpose: the per-session key store lives in process memory
CMD ["gunicorn", "--chdir", "/app/pipeline", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8765", "--timeout", "600", "app:app"]
