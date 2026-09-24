FROM ghcr.io/astral-sh/uv:0.9.30@sha256:538e0b39736e7feae937a65983e49d2ab75e1559d35041f9878b7b7e51de91e4 AS uv
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/agent
ENV OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/agent/lib
COPY runtime-requirements.lock /opt/agent/
RUN uv --no-config pip install --python /usr/local/bin/python --no-python-downloads --only-binary :all: --require-hashes -r runtime-requirements.lock && uv --no-config pip check --python /usr/local/bin/python && uv --no-config pip freeze --python /usr/local/bin/python > installed-packages.txt
COPY lib /opt/agent/lib
COPY app /opt/agent/app
RUN python app/main.py --self-check
EXPOSE 8088
CMD ["python", "app/main.py"]
