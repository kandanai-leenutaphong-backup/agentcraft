FROM ghcr.io/astral-sh/uv:0.9.30@sha256:538e0b39736e7feae937a65983e49d2ab75e1559d35041f9878b7b7e51de91e4 AS uv
FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /opt/experiment
ENV OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false
COPY wheelhouse /opt/wheelhouse
COPY runtime-requirements.lock dependency-manifest.json /opt/experiment/
RUN uv --no-config pip install --python /usr/local/bin/python --no-python-downloads --no-build-isolation --only-binary :all: --no-index --find-links /opt/wheelhouse --require-hashes -r runtime-requirements.lock && uv pip check --python /usr/local/bin/python && uv pip freeze --python /usr/local/bin/python > installed-packages.txt
RUN /usr/local/bin/python -c 'import importlib.metadata as metadata,json; print(json.dumps([{ "name": item.metadata["Name"], "version": item.version, "location": str(item.locate_file("")) } for item in metadata.distributions()], sort_keys=True))' > installed-locations.json
COPY app /opt/experiment
RUN python deploy/compatibility.py
EXPOSE 8088
CMD ["python", "main.py"]