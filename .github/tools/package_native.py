#!/usr/bin/env python3
"""Build native discovery and portable guidance from libraries/capabilities.json."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import posixpath
import re
import tomllib
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit


PACKAGE = ".github/skills/harness-guide/framework/src/agentcraft"
LEGACY_PACKAGE = "libraries/framework/src/agentcraft"
LIBRARY_SKILL_NAMES = frozenset({
    "azure-data-connectors", "azure-search", "content-from-a-store", "azure-llm-connectors",
    "managed-identity-model-clients", "azure-access-management", "signed-dev-access",
    "situation-detector", "resource-explorer", "modular-agents", "event-stream", "source-code",
    "llm-interface", "framework-core", "entra-auth",
})
RETIRED_SKILL_NAMES = frozenset({"azure-llm-compat", "search-read-adapter"})
PORTABLE = "com.github.copilot"
MCP_ADAPTERS = {
    "data": ("azure-data-connectors", "libraries/azure-data-connectors/src/azdata/mcp_adapter.py"),
    "model": ("llm-interface", "libraries/llm-interface/src/llm_interface/mcp_adapter.py"),
    "composition": ("app-composition", ".github/skills/portable-app-composition/appcompose/mcp.py"),
    "recovery": ("recoverable-jobs", ".github/skills/recoverable-jobs/workrecovery/mcp.py"),
    "inventory": ("resource-explorer", "libraries/resource-explorer/src/resource_explorer/mcp_adapter.py"),
}
INLINE_LINK = re.compile(r"(!?\[([^\]]*)\])\(\s*(<[^>]+>|[^\s()]+)(\s+[\"'][^\n]*?[\"'])?\s*\)")
REFERENCE = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)(.*)$")
REFERENCE_USE = re.compile(r"!?\[([^\]\n]+)\](?:\[([^\]\n]*)\])?(?!\()")
HTML_LINK = re.compile(r"\b(href|src)=(?P<html_quote>['\"])(.*?)(?P=html_quote)", re.IGNORECASE)
MARKDOWN_ITEM = re.compile(
    r"(?P<code>(?P<ticks>`+)(?!`)[\s\S]*?(?P=ticks)(?!`))"
    r"|(?P<link>" + INLINE_LINK.pattern + r")"
    r"|(?P<html>" + HTML_LINK.pattern + r")"
    r"|(?P<reference>" + REFERENCE_USE.pattern + r")", re.IGNORECASE)


def json_text(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True) + "\n"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def local_path(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Expected a contained source path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise ValueError(f"Source path escapes its root: {relative}")
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Source path escapes its root: {relative}")
    if must_exist and not target.exists():
        raise ValueError(f"Source path does not exist: {relative}")
    return target


def catalogue_source(root: Path) -> dict:
    from repository_inspection.catalogue import contained_file, document, entry_names

    catalogue = document(root, "libraries/capabilities.json")
    plugin = catalogue.get("plugin")
    if (not isinstance(plugin, dict) or not isinstance(plugin.get("name"), str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", plugin["name"])
            or not isinstance(plugin.get("version"), str) or not plugin["version"].strip()):
        raise ValueError("Canonical plugin needs a valid name and a nonempty version string")
    skills = catalogue["skills"]
    protocols = catalogue["protocols"]
    names = entry_names(skills, "skills")
    protocol_names = entry_names(protocols, "protocols")
    for name in LIBRARY_SKILL_NAMES:
        path = root / ".github/skills" / name
        if path.exists() or path.is_symlink():
            raise ValueError(f"Library-owned skill directory is forbidden: {name}")
    reserved = set(names)
    if len(reserved) != len(names) or len(set(protocol_names)) != len(protocol_names):
        raise ValueError("Duplicate task names")
    for protocol in protocols:
        native = protocol["native_name"]
        if not re.fullmatch(r"protocol-[a-z0-9-]+", native) or native in reserved:
            raise ValueError("Invalid or colliding native protocol name")
        reserved.add(native)
        contained_file(root, protocol["guidance"])
        if protocol["name"] != native:
            if protocol["name"] in reserved:
                raise ValueError("Colliding protocol alias")
            reserved.add(protocol["name"])
        if protocol["path"] != f"{native}/SKILL.md":
            raise ValueError("Protocol path must match its native name")
    for skill in skills:
        components = skill.get("components", [])
        for component in components:
            entry_names([component], "components")
            if component["path"] != f"guides/{component['name']}/SKILL.md":
                raise ValueError("Embedded guidance needs its own contained SKILL.md")
        for entry in [skill, *components]:
            candidates = entry.get("aliases", []) + ([entry["name"]] if entry is not skill else [])
            for alias in candidates:
                if alias in reserved:
                    raise ValueError("Duplicate or colliding capability alias")
                reserved.add(alias)
            if "mcp" in entry:
                raise ValueError("Skill MCP claims must reference a canonical conditional target")
            contained_file(root, entry["guidance"])
        contained_file(root, skill["source"])
    if reserved.intersection(LIBRARY_SKILL_NAMES | RETIRED_SKILL_NAMES):
        raise ValueError("Library-owned or retired names cannot be native skills or aliases")
    discovered = {path.parent.name for path in (root / ".github/skills").glob("*/SKILL.md")}
    if discovered - set(names) - {entry["native_name"] for entry in protocols}:
        raise ValueError("Uncatalogued native skill entrypoint")
    capabilities = catalogue["capabilities"]
    identifiers = {entry["id"] for entry in capabilities}
    if len(identifiers) != len(capabilities):
        raise ValueError("Duplicate library capability IDs")
    features = []
    library_tasks = []
    for entry in capabilities:
        if not set(entry["dependencies"]) <= identifiers:
            raise ValueError("Unknown capability dependency")
        if not all(entry.get(field) for field in ("owner", "outcome", "grants", "lifetime", "status")):
            raise ValueError("Capability needs owner, outcome, authority, lifetime and status")
        features.extend(entry.get("feature_ids", []))
        for relative in [*entry["source_paths"], *entry["docs"], *entry["examples"], *entry["checks"]["paths"]]:
            local_path(root, relative)
        for distribution in entry["distributions"]:
            metadata_path = distribution["metadata"]
            raw = contained_file(root, metadata_path).read_bytes()
            metadata = tomllib.loads(raw.decode()) if metadata_path.endswith(".toml") else json.loads(raw)
            if metadata.get("project", metadata)["name"] != distribution["name"]:
                raise ValueError(f"Distribution name disagrees with metadata: {metadata_path}")
        tasks = entry.get("tasks", [])
        entry_names(tasks, "library tasks")
        for task in tasks:
            if entry["id"] not in task["capabilities"] or not set(task["capabilities"]) <= identifiers:
                raise ValueError("Library task needs its owning capability and known dependencies")
            components = task.get("components", [])
            entry_names(components, "library task components")
            for item in [task, *components]:
                if "source" in item or "path" in item or "mcp" in item:
                    raise ValueError("Library tasks cannot declare native projections or MCP bindings")
                guide = contained_file(root, item["guidance"])
                if not guide.is_relative_to(local_path(root, entry["owner"]).resolve()):
                    raise ValueError("Library task guidance must remain under its capability owner")
                library_tasks.append(item)
    library_names = set(LIBRARY_SKILL_NAMES)
    for task in library_tasks:
        library_names.update([task["name"], *task.get("aliases", [])])
    if library_names.intersection(reserved):
        raise ValueError("Library task names and aliases cannot be native skills")
    for name in library_names:
        path = root / ".github/skills" / name
        if path.exists() or path.is_symlink():
            raise ValueError(f"Library-owned skill directory is forbidden: {name}")
    if len(set(features)) != len(features):
        raise ValueError("Duplicate feature ownership")
    if any(not set(entry["capabilities"]) <= identifiers for entry in skills):
        raise ValueError("Unknown skill capability")
    if any(entry.get("status") == "skill-only" and entry["capabilities"] for entry in skills):
        raise ValueError("Skill-only tasks cannot register runtime capabilities")
    for entry in catalogue.get("source_skills", []):
        if entry.get("superseded_by") not in names or entry.get("status") != "historical-not-advertised":
            raise ValueError("Unknown historical alias target")
    mcp = catalogue["mcp"]
    if (set(mcp) - {"status", "verification", "activation", "registered_servers", "default_request",
                    "source", "checks", "targets", "legacy_tools"}
            or mcp["registered_servers"] != [] or mcp.get("activation") != "disabled-by-default"):
        raise ValueError("MCP discovery must remain disabled by default, without host bindings or grants")
    if mcp["status"] not in {"implemented", "unavailable", "retired"}:
        raise ValueError("Unsupported MCP implementation state")
    if mcp["status"] == "implemented":
        request = {"command": "agentcraft", "args": ["mcp", "--offline"],
                   "capabilities": ["app-composition"], "status": "operator-opt-in"}
        if mcp.get("default_request") != request:
            raise ValueError("MCP opt-in requires exactly the installed composition-only host command")
        if (mcp.get("verification") != "offline-verified" or mcp.get("source") != f"{PACKAGE}/mcp.py"
                or mcp.get("checks", {}).get("status") != "offline-verified"
                or not mcp["checks"].get("paths") or not mcp["checks"].get("command")):
            raise ValueError("Implemented MCP requires its canonical host and bounded offline evidence")
        contained_file(root, mcp["source"])
        for relative in mcp["checks"]["paths"]:
            contained_file(root, relative)
    elif mcp.get("default_request") is not None or mcp.get("verification") != "not-run":
        raise ValueError("Unavailable or retired MCP cannot advertise an executable opt-in")
    target_names = set()
    tools = set()
    for target in mcp["targets"]:
        if (set(target) - {"name", "capability", "source", "tools", "status", "availability", "verification", "reason"}
                or target["capability"] not in identifiers
                or (target["capability"], target.get("source")) != MCP_ADAPTERS.get(target["name"])
                or target["status"] not in {"implemented", "unavailable", "retired"}):
            raise ValueError("Unsupported MCP capability or availability claim")
        if target["status"] == "implemented":
            if (mcp["status"] != "implemented" or target.get("availability") != "conditional"
                    or target.get("verification") != "offline-verified"):
                raise ValueError("Implemented MCP targets require conditional availability and offline evidence")
            source = contained_file(root, target["source"])
            tree = ast.parse(source.read_text(encoding="utf-8"))
            schemas = [node.value for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(name, ast.Name) and name.id == "TOOLS" for name in node.targets)]
            if len(schemas) != 1 or not isinstance(schemas[0], ast.List):
                raise ValueError("MCP adapter must declare its public TOOLS schemas")
            declared = [keyword.value.value for tool in schemas[0].elts
                        if isinstance(tool, ast.Call) and isinstance(tool.func, ast.Attribute)
                        and isinstance(tool.func.value, ast.Name) and tool.func.value.id == "types"
                        and tool.func.attr == "Tool" for keyword in tool.keywords
                        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)]
            if not declared or len(declared) != len(schemas[0].elts) or target["tools"] != declared:
                raise ValueError("MCP target tools disagree with the owning public schemas")
        elif target.get("availability") != "unavailable" or target.get("verification") != "not-run":
            raise ValueError("Unavailable or retired MCP targets cannot advertise verified availability")
        if target["name"] in target_names or tools.intersection(target["tools"]):
            raise ValueError("Duplicate MCP target or tool")
        target_names.add(target["name"])
        tools.update(target["tools"])
    if mcp["status"] == "implemented" and not any(
        target["name"] == "composition" and target["status"] == "implemented" for target in mcp["targets"]
    ):
        raise ValueError("The offline MCP opt-in requires implemented composition schemas")
    if any(entry.get("mcp_target") not in target_names for entry in skills if "mcp_target" in entry):
        raise ValueError("Unknown MCP target")
    if any(entry.get("mcp_target") not in target_names for entry in library_tasks if "mcp_target" in entry):
        raise ValueError("Unknown library task MCP target")
    if any(tool is not None and tool not in tools for tool in mcp["legacy_tools"].values()):
        raise ValueError("Unknown replacement MCP tool")
    for relative in [*catalogue["guidance"]["roots"], *catalogue["guidance"]["notices"], *catalogue["guidance"]["redirects"].values()]:
        local_path(root, relative)
    return catalogue


def generation(root: Path, catalogue: dict) -> dict:
    paths = {entry[field] for entry in catalogue["skills"] for field in ("source", "guidance")}
    paths.update(component["guidance"] for entry in catalogue["skills"] for component in entry.get("components", []))
    paths.update(entry["guidance"] for entry in catalogue["protocols"])
    return {"source": "libraries/capabilities.json", "revision": catalogue["revision"],
            "sha256": hashlib.sha256((root / "libraries/capabilities.json").read_bytes()).hexdigest(),
            "source_hashes": {relative: hashlib.sha256(local_path(root, relative).read_bytes()).hexdigest()
                              for relative in sorted(paths)},
            "generator": ".github/tools/package_native.py", "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def skill_view(catalogue: dict, provenance: dict, *, workspace: bool = False) -> dict:
    skills = json.loads(json.dumps(catalogue["skills"]))
    for entry in skills:
        if workspace:
            components = entry.pop("components", [])
            entry["aliases"] = entry.get("aliases", []) + [component["name"] for component in components]
            entry["embedded_guidance"] = [{key: value for key, value in component.items() if key != "path"}
                                          for component in components]
    for protocol in catalogue["protocols"]:
        skills.append({"name": protocol["native_name"], "summary": protocol["summary"],
                       "access": "native workflow skill", "protocol": protocol["name"],
                       **({"source": protocol["guidance"], "guidance": protocol["guidance"]} if workspace else {}),
                       "keywords": protocol.get("keywords", []), "status": protocol["status"]})
    result = {"schema_version": 1, "generation": provenance, "skills": sorted(skills, key=lambda entry: entry["name"]),
              "source_skills": catalogue.get("source_skills", []), "mcp_disposition": catalogue["mcp"]}
    if workspace:
        result.update(schema_version=2, discovery="workspace-source", workspace_root="../..")
    return result


def rewrite_links(text: str, resolve) -> str:
    """Rewrite Markdown/HTML destinations, preserving fenced and inline code."""
    lines = text.splitlines(keepends=True)
    active = []
    fence = None
    for line in lines:
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            active.append(False)
        else:
            active.append(fence is None)
    references = {}
    for number, line in enumerate(lines, 1):
        match = REFERENCE.match(line) if active[number - 1] else None
        if match:
            target = match[2].strip("<>")
            destination, reason = resolve(target, number)
            references[match[1].casefold()] = (destination, reason, target)
            lines[number - 1] = f"[{match[1]}]: {destination}{match[3]}\n" if destination else "\n"
            active[number - 1] = False

    def omitted(label, target, reason):
        return f"{label} ({reason}; source reference: `{target}`)"

    output = []
    offset = 0
    while offset < len(lines):
        if not active[offset]:
            output.append(lines[offset])
            offset += 1
            continue
        end = offset + 1
        while end < len(lines) and active[end]:
            end += 1
        block = "".join(lines[offset:end])

        def replace(item):
            number = offset + 1 + block.count("\n", 0, item.start())
            if item.group("code") is not None:
                return item[0]
            if item.group("link") is not None:
                match = INLINE_LINK.fullmatch(item[0])
                target = match[3].strip("<>")
                destination, reason = resolve(target, number)
                return f"{match[1]}({destination}{match[4] or ''})" if destination else omitted(match[2], target, reason)
            if item.group("html") is not None:
                match = HTML_LINK.fullmatch(item[0])
                destination, reason = resolve(match[3], number)
                return f'{match[1]}="{destination}"' if destination else f'data-guidance-omitted="{reason}"'
            match = REFERENCE_USE.fullmatch(item[0])
            key = (match[2] or match[1]).casefold()
            if key not in references or references[key][0]:
                return match[0]
            _, reason, target = references[key]
            return omitted(match[1], target, reason)

        output.append(MARKDOWN_ITEM.sub(replace, block))
        offset = end
    return "".join(output)


def wrapper(entry: dict, destination: str) -> str:
    return (f"---\nname: {entry['name']}\ndescription: {json.dumps(entry['summary'])}\n---\n\n"
            f"# {entry['name']}\n\nRead [canonical guidance]({destination}).\n\n"
            "Generated from libraries/capabilities.json. Installation and discovery grant no execution, model, cloud or filesystem authority.\n")


def guidance_files(root: Path, catalogue: dict, provenance: dict) -> tuple[dict[str, str], dict[str, str]]:
    from repository_inspection.catalogue import contained_file

    policy = catalogue["guidance"]
    outputs = {}
    sources = {}
    omitted = []
    locations = {".github/skills/README.md": "README.md", ".github/protocols/README.md": "README.md",
                 ".github/skills/catalogue.json": "skills/catalogue.json",
                 f"{PACKAGE}/guidance/README.md": "README.md",
                 f"{PACKAGE}/guidance/provenance.json": "provenance.json"}
    documents = {}
    pending = []

    def read(relative):
        path = contained_file(root, relative)
        text = path.read_text(encoding="utf-8")
        sources[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return text

    def add_document(relative, destination=None):
        if relative not in documents:
            source_name = "harness/" + relative.removeprefix(".github/") if relative.startswith(".github/") else relative
            destination = destination or "references/" + source_name
            documents[relative] = destination
            pending.append(relative)
        return documents[relative]

    for entry in catalogue["skills"]:
        destination = f"skills/{entry['name']}/SKILL.md"
        locations[entry["source"]] = destination
        read(entry["source"])
        guide = add_document(entry["guidance"])
        outputs[destination] = wrapper(entry, posixpath.relpath(guide, posixpath.dirname(destination)))
        for component in entry.get("components", []):
            destination = f"skills/{entry['name']}/{component['path']}"
            guide = add_document(component["guidance"])
            outputs[destination] = wrapper(component, posixpath.relpath(guide, posixpath.dirname(destination)))
    for protocol in catalogue["protocols"]:
        destination = "protocols/" + protocol["path"]
        locations[protocol["guidance"]] = destination
        locations[f".github/skills/{protocol['native_name']}/SKILL.md"] = destination
        add_document(protocol["guidance"], destination)
    for capability in catalogue["capabilities"]:
        if capability["status"] != "retired":
            for relative in capability["docs"]:
                add_document(relative)
            for task in capability.get("tasks", []):
                for entry in [task, *task.get("components", [])]:
                    add_document(entry["guidance"])
    for relative in policy["notices"]:
        add_document(relative)
    native_sources = {}
    for directory, pattern, output_directory in (("agents", "*.agent.md", "agents"), ("instructions", "*.instructions.md", "rules")):
        for path in sorted((root / ".github" / directory).glob(pattern)):
            relative = path.relative_to(root).as_posix()
            add_document(relative)
            native_sources[f"{output_directory}/{path.name}"] = relative

    def resolve(source, output, target, line):
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https", "mailto"} or target.startswith("//"):
            return target, None
        if not parsed.path and not parsed.scheme:
            return target, None
        lexical = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path)))
        lexical = policy["redirects"].get(lexical, lexical)
        if (parsed.scheme or not (lexical in locations or lexical in policy["notices"]
                                  or any(lexical == prefix or lexical.startswith(prefix + "/")
                                         for prefix in policy["roots"]))):
            reason = "outside-guidance-not-advertised"
            omitted.append({"source": source, "line": line, "target": target, "resolved_source": lexical,
                            "exists": None, "classification": reason})
            return None, reason
        path = (root / source).parent / unquote(parsed.path)
        path = path.resolve()
        contained = path.is_relative_to(root.resolve())
        relative = path.relative_to(root.resolve()).as_posix() if contained else target
        relative = policy["redirects"].get(relative, relative)
        if contained:
            path = local_path(root, relative, must_exist=False)
        historical = any(part in policy["historical_segments"] for part in PurePosixPath(relative).parts)
        allowed = contained and any(relative == prefix or relative.startswith(prefix + "/") for prefix in policy["roots"])
        if relative in policy["notices"]:
            allowed, historical = True, False
        if parsed.scheme or not contained:
            reason = "outside-guidance-not-advertised"
        elif relative in locations:
            destination = locations[relative]
            return quote(posixpath.relpath(destination, posixpath.dirname(output)), safe="/.-_") + ("#" + parsed.fragment if parsed.fragment else ""), None
        elif historical:
            reason = "historical-not-advertised"
        elif not allowed:
            reason = "outside-guidance-not-advertised"
        else:
            if path.is_dir() and (path / "README.md").is_file():
                path = path / "README.md"
                relative += "/README.md"
            if not path.exists():
                reason = "missing-not-advertised"
            elif not path.is_file() or not (path.suffix.lower() in {".md", ".txt"} or relative in policy["notices"] or path.name in {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES"}):
                reason = "source-or-asset-not-bundled"
            else:
                destination = add_document(relative)
                return quote(posixpath.relpath(destination, posixpath.dirname(output)), safe="/.-_") + ("#" + parsed.fragment if parsed.fragment else ""), None
        omitted.append({"source": source, "line": line, "target": target, "resolved_source": relative,
                        "exists": path.exists() if contained else None, "classification": reason})
        return None, reason

    while pending:
        relative = pending.pop(0)
        destination = documents[relative]
        if len(documents) > 512:
            raise ValueError("Portable guidance exceeds the 512-document scope bound")
        text = read(relative)
        outputs[destination] = rewrite_links(text, lambda target, line: resolve(relative, destination, target, line))

    provenance = {**provenance, "sources": dict(sorted(sources.items())), "omissions": omitted,
                  "scope": "Markdown inline/reference and HTML href/src destinations outside fenced and inline code; no external fetch, runtime source or unreviewed assets."}
    outputs["provenance.json"] = json_text({"schema_version": 1, **provenance})
    outputs["skills/catalogue.json"] = json_text(skill_view(catalogue, generation(root, catalogue)))
    outputs["protocols/catalogue.json"] = json_text({"schema_version": 1, "generation": generation(root, catalogue), "protocols": catalogue["protocols"]})
    outputs["mcp.json"] = json_text({"mcpServers": {}})
    outputs["README.md"] = guidance_index(catalogue)
    outputs["native-manifest.json"] = json_text({"schema_version": 1, "generation": generation(root, catalogue),
                                                "files": {relative: digest(text) for relative, text in sorted(outputs.items())}})
    native = {}
    for destination, source in native_sources.items():
        original = "guidance/" + documents[source]

        def rebase(target, line):
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path or target.startswith("//"):
                return target, None
            target_path = posixpath.normpath(posixpath.join(posixpath.dirname(original), unquote(parsed.path)))
            return quote(posixpath.relpath(target_path, posixpath.dirname(destination)), safe="/.-_") + ("#" + parsed.fragment if parsed.fragment else ""), None

        native[destination] = rewrite_links(outputs[documents[source]], rebase)
    return outputs, native


def mcp_discovery(catalogue: dict) -> str:
    mcp = catalogue["mcp"]
    text = (f"MCP implementation: {mcp['status']}; verification: {mcp['verification']}. "
            f"Registrations: {len(mcp['registered_servers'])}; disabled by default.")
    if request := mcp.get("default_request"):
        command = " ".join([request["command"], *request["args"]])
        text += (f" With the selected installed `mcp` extra, explicitly run `{command}` for "
                 "composition-only synthetic/offline stdio. No data, model, recovery or inventory binding is created. "
                 "Other targets require a trusted host calling `agentcraft.mcp.create_server` with explicit "
                 "bindings, exact per-binding tool grants, principal and execution context. "
                 "Metadata is not activation, credentials, live-service evidence or installed-client acceptance.")
    return text


def guidance_index(catalogue: dict) -> str:
    lines = ["# Portable Guidance", "", "Generated from libraries/capabilities.json; do not edit this view.", "",
             "This is a contained metadata/guidance package, not a runtime source bundle. Install selected canonical release artifacts separately. No server starts and no credential, model, cloud or user-state permission is granted.", "",
             "Installed CLI: `agentcraft describe [id]` describes capability contracts without provider I/O. With the selected `tooling` extra, use `agentcraft catalogue --find composition` or `agentcraft catalogue --show portable-app-composition --kind skill`; `--kind protocol` selects workflow records. The public `python -m agentcraft.examples` task runs real native data -> rules -> model -> recovery against synthetic transports; its final non-editable combined-wheel acceptance remains parent-owned.", "",
             "Installed API: `agentcraft.catalogue.load_catalogue()` reads capability records, `agentcraft.catalogue.guidance_root()` locates this package, and `agentcraft.catalogue.report(name=\"harness-guide\")` or `report(query=\"composition\")` provides discovery. Search/read uses the declared `repository-inspection` tooling dependency.", "",
             "`repository-catalogue --root <this-guidance-directory> --list --json` uses the same installed reader. Native workflow wrappers live outside this reader root; this preserves its existing schema and unique protocol identities.", "",
             mcp_discovery(catalogue), "",
             "[Provenance and exclusions](provenance.json) records exact source hashes, missing references, historical evidence and unbundled source/assets. Labels are not replacement evidence. Code blocks are canonical source guidance; checkout-only commands are not portable installed examples. Capability tests/live behavior and redistribution of omitted assets are unverified here.", "", "## Tasks", ""]
    for entry in catalogue["skills"]:
        lines.append(f"- [{entry['name']}](skills/{entry['name']}/SKILL.md): {entry['summary']}")
        for component in entry.get("components", []):
            lines.append(f"- [{component['name']}](skills/{entry['name']}/{component['path']}): {component['summary']}")
    lines.extend(["", "## Protocols", ""])
    for entry in catalogue["protocols"]:
        lines.append(f"- [{entry['native_name']}](protocols/{entry['path']}): {entry['summary']}")
    return "\n".join(lines) + "\n"


def workspace_products(catalogue: dict, provenance: dict) -> dict[str, str]:
    products = {".github/skills/catalogue.json": json_text(skill_view(catalogue, provenance, workspace=True)),
                ".github/plugin.json": json_text({
                    "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", **catalogue["plugin"],
                    "description": f"{len(catalogue['skills']) + len(catalogue['protocols'])} native skills; canonical source discovery, no active MCP registrations."}),
                ".github/mcp.json": json_text({"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json", "mcpServers": {}})}
    for entry in catalogue["protocols"]:
        products[f".github/skills/{entry['native_name']}/SKILL.md"] = wrapper(
            {**entry, "name": entry["native_name"]}, f"../../protocols/{entry['path']}")
    lines = ["# Skill Catalogue", "", "Generated from [libraries/capabilities.json](../../libraries/capabilities.json). Do not edit this view.", "",
             "Workspace discovery reads canonical sources; no documentation or runtime copies are generated.", "",
             "[Generated metadata](catalogue.json) declares repository-relative source and guidance paths with source hashes. Library task metadata remains in the authoritative capability records, outside native skill discovery.", ""]
    for entry in catalogue["skills"]:
        lines.append(f"- [{entry['name']}]({posixpath.relpath(entry['source'], '.github/skills')}): {entry['summary']}")
    lines.extend(["", "## Workflows", ""])
    for entry in catalogue["protocols"]:
        lines.append(f"- [{entry['native_name']}]({posixpath.relpath(entry['guidance'], '.github/skills')}): {entry['summary']}")
    lines.extend(["", mcp_discovery(catalogue), ""])
    products[".github/skills/README.md"] = "\n".join(lines)
    return products


def build_products(root: Path, *, portable: bool = False) -> dict[str, str]:
    from repository_inspection.catalogue import contained_file

    catalogue = catalogue_source(root)
    provenance = generation(root, catalogue)
    if not portable:
        return workspace_products(catalogue, provenance)
    guidance, native = guidance_files(root, catalogue, provenance)
    products = {f".github/{PORTABLE}/guidance/{relative}": text for relative, text in guidance.items()}
    products.update({f".github/{PORTABLE}/{relative}": text for relative, text in native.items()})
    snapshot = json.loads(json.dumps(catalogue))
    snapshot["generation"] = provenance
    snapshot["path_evidence"] = []
    for capability in snapshot["capabilities"]:
        for distribution in capability["distributions"]:
            metadata_path = distribution["metadata"]
            raw = contained_file(root, metadata_path).read_bytes()
            metadata = tomllib.loads(raw.decode()) if metadata_path.endswith(".toml") else json.loads(raw)
            project = metadata.get("project", metadata)
            if project["name"] != distribution["name"]:
                raise ValueError(f"Distribution name disagrees with metadata: {metadata_path}")
            distribution.update({"version": project["version"], "metadata_sha256": hashlib.sha256(raw).hexdigest(),
                                 "requirements": project.get("dependencies", []),
                                 "optional_requirements": project.get("optional-dependencies", {}),
                                 "peer_requirements": project.get("peerDependencies", {})})
        for field in ("source_paths", "docs", "examples"):
            for relative in capability[field]:
                snapshot["path_evidence"].append({"capability": capability["id"], "field": field, "path": relative,
                                                  "exists": local_path(root, relative).exists(), "execution": "not-run"})
        for relative in capability["checks"]["paths"]:
            snapshot["path_evidence"].append({"capability": capability["id"], "field": "checks", "path": relative,
                                              "exists": local_path(root, relative).exists(), "execution": "not-run"})
    products[f".github/{PORTABLE}/capabilities.json"] = json_text(snapshot)
    products[".github/skills/catalogue.json"] = json_text(skill_view(catalogue, provenance, workspace=True))
    plugin = {"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", **catalogue["plugin"],
              "description": f"{len(catalogue['skills']) + len(catalogue['protocols'])} native guidance skills with canonical library references; offline discovery, no active MCP registrations."}
    for prefix in (".github", f".github/{PORTABLE}"):
        products[f"{prefix}/plugin.json"] = json_text(plugin)
        products[f"{prefix}/mcp.json"] = json_text({"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json", "mcpServers": {}})
    for entry in catalogue["skills"]:
        products[f".github/{PORTABLE}/skills/{entry['name']}/SKILL.md"] = wrapper(entry, f"../../guidance/skills/{entry['name']}/SKILL.md")
    for entry in catalogue["protocols"]:
        native_entry = {**entry, "name": entry["native_name"]}
        products[f".github/{PORTABLE}/skills/{entry['native_name']}/SKILL.md"] = wrapper(native_entry, f"../../guidance/protocols/{entry['path']}")
        products[f".github/skills/{entry['native_name']}/SKILL.md"] = wrapper(native_entry, f"../../protocols/{entry['path']}")
    products[f".github/{PORTABLE}/README.md"] = ("# Native Guidance Plugin\n\nGenerated build product. "
        "[Start with portable guidance](guidance/README.md). Runtime packages install separately.\n\n"
        + mcp_discovery(catalogue) + "\n")
    products[".github/skills/README.md"] = ("# Skill Catalogue\n\nGenerated from [libraries/capabilities.json](../../libraries/capabilities.json). Do not edit this view.\n\n"
        f"{len(catalogue['skills'])} named skills, {len(catalogue['protocols'])} native protocol workflows and "
        f"{sum(len(entry.get('components', [])) for entry in catalogue['skills'])} embedded guidance entries. "
        "Embedded names are lookup aliases in this workspace view and first-class entries in the contained reader package.\n\n"
        f"[Packaged task index](../../{PACKAGE}/guidance/README.md) links to retained guidance and notices. "
        "[Generated metadata](catalogue.json) preserves native task discovery. "
        f"Use `repository-catalogue --root {PACKAGE}/guidance --list --json`; the workspace catalogue identifies this retained reader package.\n\n"
        "Framework runtimes install separately. Authoring-only skills may own scripts and assets without becoming framework libraries. "
        + mcp_discovery(catalogue) + "\n\n"
        "[Distribution contract](AGENT-PLUGINS-SKILLS.md) separates installation, activation, authorization and publication.\n")
    return products


def native_files(root: Path) -> dict[str, str]:
    return {relative.removeprefix(".github/"): text for relative, text in build_products(root, portable=True).items() if relative.startswith(".github/")}


def native_catalogue(root: Path) -> str:
    catalogue = catalogue_source(root)
    return json_text(skill_view(catalogue, generation(root, catalogue), workspace=True))


def owned(relative: str, *, package: bool = False) -> bool:
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or "\\" in relative or {"state", "records", "drafts", ".venv", "__pycache__"}.intersection(parts.parts):
        return False
    if parts.suffix not in {".md", ".txt", ".json", ""}:
        return False
    if package:
        return relative == "capabilities.json" or relative.startswith("guidance/")
    return (relative in {"skills/catalogue.json", "skills/README.md", "plugin.json", "mcp.json"}
            or bool(re.fullmatch(r"(?:skills|protocols)/protocol-[a-z0-9-]+/SKILL\.md", relative))
            or relative.startswith(PORTABLE + "/"))


def materialize(root: Path, *, check: bool = False, plugin_output: Path | None = None) -> list[str]:
    core = plugin_output if plugin_output is not None else root / ".github"
    if plugin_output is not None:
        if (not core.is_absolute() or ".." in core.parts
                or core.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(core.resolve())
                or any(path.is_symlink() for path in (core, *core.parents))):
            raise ValueError("Plugin output must be an absolute external directory without symlinks")
    products = build_products(root, portable=plugin_output is not None)
    portable = f".github/{PORTABLE}/"
    products = ({".github/" + relative.removeprefix(portable): text for relative, text in products.items()
                 if relative.startswith(portable)} if plugin_output is not None else
                {relative: text for relative, text in products.items()
                 if relative.startswith(".github/") and not relative.startswith(portable)})
    catalogue = catalogue_source(root)
    authored_protocols = {"protocols/" + entry["path"] for entry in catalogue["protocols"]}
    previous_path = core / "native-manifest.json"
    if previous_path.is_symlink() or not previous_path.resolve().is_relative_to(core.resolve()):
        raise ValueError("Native manifest must not be a symlink")
    previous_document = json.loads(previous_path.read_text()) if previous_path.is_file() else {"schema_version": 1, "files": {}}
    if not isinstance(previous_document, dict) or previous_document.get("schema_version") != 1 or not isinstance(previous_document.get("files"), dict):
        raise ValueError("Invalid previous native manifest")
    if plugin_output is not None and previous_document.get("package_files"):
        raise ValueError("Plugin output cannot own workspace package files")
    legacy = core / PORTABLE
    legacy_directories = []
    if plugin_output is None and (legacy.exists() or legacy.is_symlink()):
        known = {core / relative for relative in previous_document["files"] if relative.startswith(PORTABLE + "/")}
        directories = {parent for path in known for parent in path.parents if parent == legacy or legacy in parent.parents}
        for path in (legacy, *legacy.rglob("*")):
            if path.is_symlink():
                raise ValueError("Refusing escaped generated target in retired portable tree")
            if path.is_dir() and path in directories:
                legacy_directories.append(path)
            elif not path.is_file() or path not in known:
                raise ValueError(f"Unowned portable path; preserve before regenerating: {path}")
    stale = []
    targets = {}
    for field, prefix, package in (("files", ".github/", False), ("package_files", LEGACY_PACKAGE + "/", True)):
        previous = previous_document.get(field, {})
        if not isinstance(previous, dict):
            raise ValueError("Invalid previous package manifest")
        base = root / LEGACY_PACKAGE if package else core
        for relative, expected in previous.items():
            ownership_path = PORTABLE + "/" + relative if plugin_output is not None else relative
            if not owned(ownership_path, package=package):
                raise ValueError("Previous native manifest claims a path outside generated ownership")
            if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise ValueError("Invalid previous native hash")
            target = base / relative
            targets[prefix + relative] = target
            if target.is_symlink() or not target.resolve().is_relative_to(base.resolve()):
                raise ValueError("Previous native manifest contains an escaping path")
            if package and target.exists():
                raise ValueError("Legacy package products require owner archival/removal before regeneration")
            if not package and relative in authored_protocols:
                continue
            if target.is_file():
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                planned = products.get(prefix + relative)
                if actual != expected and (planned is None or actual != digest(planned)):
                    label = "Retired native file" if planned is None else "Generated file"
                    raise ValueError(f"{label} was edited: {relative}; preserve it before regenerating")
                if planned is None:
                    stale.append(prefix + relative)
    manifest = {"schema_version": 1, "generator": "tools/package_native.py", "generation": generation(root, catalogue),
                "files": {relative.removeprefix(".github/"): digest(text) for relative, text in sorted(products.items()) if relative.startswith(".github/")},
                "package_files": {relative.removeprefix(PACKAGE + "/"): digest(text) for relative, text in sorted(products.items()) if relative.startswith(PACKAGE + "/")}}
    products[".github/native-manifest.json"] = json_text(manifest)
    if plugin_output is not None:
        expected_files = {core / relative.removeprefix(".github/") for relative in products}
        expected_directories = {parent for path in expected_files for parent in path.parents if core in parent.parents}
        present = set()
        for path in core.rglob("*"):
            if path.is_symlink() or (path.is_dir() and path not in expected_directories):
                raise ValueError(f"Refusing unowned or symlinked plugin output: {path}")
            if not path.is_dir():
                present.add(path)
        if present and present != expected_files:
            raise ValueError("Plugin output must be empty or the complete generated export")
    changed = list(stale)
    for relative, text in products.items():
        prefix = PACKAGE + "/" if relative.startswith(PACKAGE + "/") else ".github/"
        ownership_path = (PORTABLE + "/" if plugin_output is not None else "") + relative.removeprefix(prefix)
        if relative != ".github/native-manifest.json" and not owned(ownership_path, package=prefix != ".github/"):
            raise ValueError(f"Refusing unowned generated target: {relative}")
        base = root / PACKAGE if prefix != ".github/" else core
        target = base / relative.removeprefix(prefix)
        targets[relative] = target
        if target.is_symlink() or not target.resolve().is_relative_to(base.resolve()) or (plugin_output is None and not target.resolve().is_relative_to(root.resolve())):
            raise ValueError(f"Refusing escaped generated target: {relative}")
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            if plugin_output is not None and target.exists():
                raise ValueError(f"Generated file was edited or export changed: {target}; use a fresh output directory")
            changed.append(relative)
    if plugin_output is not None and any(path.is_symlink() for path in (core, *core.parents)):
        raise ValueError("Plugin output changed to a symlink")
    if not check:
        for relative in stale:
            targets[relative].unlink()
        for directory in sorted(legacy_directories, key=lambda path: len(path.parts), reverse=True):
            directory.rmdir()
        for relative in changed:
            if relative in products:
                target = targets[relative]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(products[relative], encoding="utf-8")
    return [str(targets[relative]) for relative in changed] if plugin_output is not None else changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--plugin-output", type=Path, help="Export a standalone plugin to a new or identical absolute external directory")
    options = parser.parse_args()
    try:
        changed = materialize(options.root.resolve(), check=options.check, plugin_output=options.plugin_output)
    except (OSError, ValueError, KeyError, ImportError) as error:
        parser.exit(2, f"Native generation refused: {error}\n")
    if options.check and changed:
        print("Native package is stale: " + ", ".join(changed))
        return 1
    print(f"Native package {'verified' if options.check else 'generated'}: {len(changed)} changed files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())