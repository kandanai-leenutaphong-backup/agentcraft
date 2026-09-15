from __future__ import annotations

import os
import queue
import signal
import socket
import subprocess
import sys
from pathlib import Path
from threading import Thread


def free_port(preferred: int) -> int:
    if not 1024 <= preferred <= 65515:
        raise ValueError("port must be between 1024 and 65515")
    for candidate in range(preferred, preferred + 20):
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", candidate))
                return candidate
            except OSError:
                continue
    raise ValueError("no free port in the requested range")


def serve(environment: dict[str, str], backend_port: int, frontend_port: int, *,
          root: Path, frontend: Path, app_module: str, label: str) -> int:
    if not (frontend / "node_modules").is_dir():
        raise ValueError("frontend dependencies missing; run deploy/deploy.sh setup")
    backend_port, frontend_port = free_port(backend_port), free_port(frontend_port)
    if backend_port == frontend_port:
        frontend_port = free_port(frontend_port + 1)
    environment.update({
        "CYBEREYE_PORT": str(backend_port), "CYBEREYE_FRONTEND_PORT": str(frontend_port),
        "CYBEREYE_CORS_ORIGINS": f"http://127.0.0.1:{frontend_port},http://localhost:{frontend_port}",
    })
    children: list[subprocess.Popen] = []
    completed: queue.Queue = queue.Queue()

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        commands = (
            ([sys.executable, "-m", "uvicorn", app_module, "--host", "127.0.0.1",
              "--port", str(backend_port), "--no-proxy-headers"], root),
            (["npm", "run", "dev", "--", "--port", str(frontend_port)], frontend),
        )
        for command, directory in commands:
            child = subprocess.Popen(command, cwd=directory, env=environment, start_new_session=True)
            children.append(child)
            Thread(target=lambda process=child: completed.put(process.wait()), daemon=True).start()
        print(f"{label}: http://127.0.0.1:{frontend_port}\nAPI: http://127.0.0.1:{backend_port}", flush=True)
        return completed.get() or 1
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()