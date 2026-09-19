"""Loopback HTTP adapter with a fixed operator, same-origin writes and static allowlist."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
from urllib.parse import parse_qs, unquote, urlsplit

from .contracts import LOCAL_OPERATOR, Refusal, canonical

_RUN = r"([a-f0-9]{32})"
_STATIC_TYPES = {".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif",
                 ".ico", ".woff", ".woff2", ".ttf"}


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refusal("duplicate_json_key")
        result[key] = value
    return result


def make_server(service, host: str = "127.0.0.1", port: int = 8765,
                dist: str | Path | None = None) -> ThreadingHTTPServer:
    """Bind only a literal loopback address. Caller owns serve/shutdown/service.close."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise Refusal("loopback_bind_required") from error
    if not address.is_loopback or not isinstance(port, int) or not 0 <= port <= 65535:
        raise Refusal("loopback_bind_required")
    directory = Path(dist) if dist is not None else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    allowed = {}
    if directory.is_dir() and not directory.is_symlink():
        for path in directory.rglob("*"):
            relative = path.relative_to(directory)
            if (path.is_file() and not any(part.is_symlink() for part in [path, *path.parents]
                                          if part != directory.parent)
                    and (relative.as_posix() == "index.html" or
                         (path.suffix.lower() in _STATIC_TYPES and
                          (relative.parts[0] == "assets" or len(relative.parts) == 1)))):
                allowed["/" + relative.as_posix()] = path.resolve()
    root = directory.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "OptimizationLocal/1"

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass

        def _send(self, status, content, content_type="application/json; charset=utf-8", filename=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, private")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(content)

        def _guard(self, write):
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                raise Refusal("loopback_peer_required", 403)
            hosts = self.headers.get_all("Host", [])
            bound = f"[{host}]" if address.version == 6 else host
            permitted = {f"{bound}:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if len(hosts) != 1 or hosts[0] not in permitted:
                raise Refusal("invalid_host", 403)
            origins = self.headers.get_all("Origin", [])
            if (write and not origins) or (origins and origins != ["http://" + hosts[0]]):
                raise Refusal("invalid_origin", 403)
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise Refusal("cross_site_request", 403)
            if any(name.lower() in {"x-owner", "x-owner-id", "x-user", "x-user-id", "x-operator", "authorization"}
                   for name in self.headers):
                raise Refusal("caller_identity_not_configurable", 403)

        def _body(self, fields):
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get_all("Transfer-Encoding") or len(lengths) != 1:
                raise Refusal("content_length_required", 411)
            if not lengths[0].isdigit() or not 0 < int(lengths[0]) <= 65536:
                raise Refusal("invalid_body_length", 413)
            if self.headers.get_content_type() != "application/json":
                raise Refusal("json_content_type_required", 415)
            payload = self.rfile.read(int(lengths[0]))
            if len(payload) != int(lengths[0]):
                raise Refusal("incomplete_body")
            try:
                body = json.loads(payload, object_pairs_hook=_json_object,
                                  parse_constant=lambda value: (_ for _ in ()).throw(Refusal("invalid_json")))
            except (ValueError, UnicodeError, RecursionError) as error:
                raise Refusal("invalid_json") from error
            if not isinstance(body, dict) or set(body) != set(fields):
                raise Refusal("invalid_request_fields")
            for key, value in body.items():
                if key == "candidate_id" and value is None and fields[key]:
                    continue
                if not isinstance(value, str):
                    raise Refusal("invalid_" + key)
            return body

        def _route(self, write):
            self._guard(write)
            parsed = urlsplit(self.path)
            path = unquote(parsed.path, errors="strict")
            if (parsed.scheme or parsed.netloc or parsed.fragment or not path.startswith("/")
                    or "\\" in path or "%" in path or "\x00" in path
                    or any(part in {".", ".."} for part in path.split("/")) or "//" in path):
                raise Refusal("invalid_path")
            if parsed.query and not re.fullmatch("/api/runs/" + _RUN + "/report", path):
                query = parse_qs(parsed.query, keep_blank_values=True)
                if (write or path != "/" or set(query) != {"run"}
                        or len(query["run"]) != 1 or not re.fullmatch(_RUN, query["run"][0])):
                    raise Refusal("unexpected_query")
            owner = LOCAL_OPERATOR
            if not write:
                if path == "/api/health":
                    return {"status": "ok"}
                if path == "/api/tasks":
                    return {"tasks": service.tasks()}
                if path == "/api/runs":
                    return {"runs": service.list_runs(owner)}
                match = re.fullmatch("/api/runs/" + _RUN + "(/report)?", path)
                if match:
                    run_id, report = match.groups()
                    if report:
                        query = parse_qs(parsed.query, keep_blank_values=True)
                        if set(query) - {"format"} or len(query.get("format", ["json"])) != 1:
                            raise Refusal("invalid_report_query")
                        format = query.get("format", ["json"])[0]
                        content, content_type = service.report(owner, run_id, format)
                        self._send(200, content, content_type, f"run-{run_id}.{format}")
                        return None
                    return service.get_run(owner, run_id)
                if path.startswith("/api/"):
                    raise Refusal("route_not_found", 404)
                static_path = "/index.html" if path == "/" else path
                asset = allowed.get(static_path)
                if asset is None or not asset.is_relative_to(root):
                    raise Refusal("static_not_found", 404)
                if any(part.is_symlink() for part in [asset, *asset.parents]):
                    raise Refusal("unsafe_static_path", 403)
                descriptor = os.open(asset, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(descriptor, "rb") as stream:
                    content = stream.read()
                self._send(200, content, mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
                return None
            if path == "/api/runs":
                body = self._body({"task_id": False, "executor": False, "idempotency_key": False})
                return service.start(owner, **body)
            match = re.fullmatch("/api/runs/" + _RUN + "/(cancel|restore|feedback)", path)
            if match:
                run_id, action = match.groups()
                if action == "cancel":
                    self._body({})
                    return service.cancel(owner, run_id)
                if action == "restore":
                    body = self._body({"candidate_id": False, "idempotency_key": False})
                    return service.restore(owner, run_id, **body)
                body = self._body({"text": False, "candidate_id": True, "idempotency_key": False})
                return service.submit_feedback(owner, run_id, body["text"], body["candidate_id"], body["idempotency_key"])
            match = re.fullmatch("/api/runs/" + _RUN + "/feedback/" + _RUN + "/respond", path)
            if match:
                body = self._body({"disposition": False, "reason": False, "candidate_id": True, "idempotency_key": False})
                return service.respond_feedback(owner, *match.groups(), **body)
            raise Refusal("route_not_found", 404)

        def _handle(self, write):
            try:
                result = self._route(write)
                if result is not None:
                    self._send(200, canonical(result))
            except Refusal as error:
                self._send(error.status, canonical({"error": error.code}))
            except (UnicodeError, ValueError):
                self._send(400, canonical({"error": "invalid_request"}))
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                self.close_connection = True
            except Exception:
                self._send(500, canonical({"error": "internal_error"}))

        def do_GET(self):
            self._handle(False)

        def do_POST(self):
            self._handle(True)

    class Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        daemon_threads = False
        block_on_close = True

    return Server((host, port), Handler)