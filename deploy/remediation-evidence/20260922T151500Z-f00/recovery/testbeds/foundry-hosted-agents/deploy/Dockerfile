FROM python:3.12-slim
WORKDIR /opt/experiment
ENV OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false
COPY libraries /opt/libraries
COPY requirements.txt /opt/experiment/requirements.txt
RUN pip install --no-cache-dir /opt/libraries/framework-core '/opt/libraries/llm-interface[foundry]' /opt/libraries/modular-agents -r requirements.txt && pip freeze > /opt/experiment/installed-packages.txt
COPY app /opt/experiment
RUN python deploy/compatibility.py
EXPOSE 8088
CMD ["python", "main.py"]