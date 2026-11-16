FROM python:3.13-slim-bookworm
WORKDIR /app
COPY --chown=10001:10001 server.py ./server.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).read(1024)"]
CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "8080"]
