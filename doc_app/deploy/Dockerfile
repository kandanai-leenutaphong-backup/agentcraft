# Vocs static build, served by the same gate as the hand-built writeup:
# Entra principal headers or an Ed25519 signed request.
ARG BASE
FROM ${BASE}

COPY deploy/app/server.py /app/server.py
COPY docs/dist/ /app/site/

# Plaintext dumps of the whole site are a single scrape target; not shipped.
RUN rm -f /app/site/llms.txt /app/site/llms-full.txt

ENV CONTENT_ROOT=/app/site
EXPOSE 8080
USER app

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
