# CMIT Housekeeping – Web V1 (Module 1). Image chạy Streamlit dưới user không phải root.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CMIT_AUTH_MODE=proxy \
    CMIT_USER_HEADER=X-Auth-Request-Email \
    CMIT_WORKSPACE=/data/workspace \
    CMIT_TEMP_DIR=/data/tmp \
    CMIT_MEMORY_LIMIT=2GB

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN groupadd --system cmit \
 && useradd --system --gid cmit --uid 10001 --home-dir /app --shell /usr/sbin/nologin cmit \
 && mkdir -p /data/workspace /data/tmp \
 && chown -R cmit:cmit /data

COPY cleaning ./cleaning
COPY app ./app
COPY scripts ./scripts
COPY run_cleaning.py ./
COPY .streamlit ./.streamlit

USER cmit

EXPOSE 8501
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).status == 200 else 1)"

CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
