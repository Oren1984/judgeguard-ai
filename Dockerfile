# One file, three targets: sandbox (worker), tests, app (Streamlit UI).
# All dependencies are installed here; nothing is downloaded at runtime.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /opt/judgeguard
# Two unprivileged users: 10001 owns the job queue and app data, 10002 owns the results.
# Both images create the mount points identically so named volumes inherit this ownership.
RUN groupadd -g 10001 jgapp && useradd -u 10001 -g 10001 -M -s /usr/sbin/nologin jgapp \
 && groupadd -g 10002 jgbox && useradd -u 10002 -g 10002 -M -s /usr/sbin/nologin jgbox \
 && mkdir -p /exchange/jobs /exchange/results /data \
 && chown 10001:10001 /exchange/jobs /data \
 && chown 10002:10002 /exchange/results \
 && chmod 755 /exchange/jobs /exchange/results && chmod 700 /data
COPY docker/pip-install.sh requirements-sandbox.txt ./
RUN --mount=type=secret,id=extra_ca,required=false sh pip-install.sh -r requirements-sandbox.txt
COPY config ./config
COPY fixtures ./fixtures
COPY judgeguard ./judgeguard

FROM base AS sandbox
ENV JG_SANDBOXED=1
USER 10002:10002
CMD ["python", "-m", "judgeguard.worker"]

FROM base AS tests
ENV JG_SANDBOXED=1
COPY tests ./tests
USER 10002:10002
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]

FROM base AS app
COPY requirements-app.txt .
RUN --mount=type=secret,id=extra_ca,required=false sh pip-install.sh -r requirements-app.txt
COPY .streamlit ./.streamlit
COPY app.py .
ENV HOME=/tmp
USER 10001:10001
EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
