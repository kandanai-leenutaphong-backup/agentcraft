# Copilot Terminal

Native GitHub Copilot CLI over a Unix PTY, with React/xterm. Adopted as source, not an
import/build dependency on another repository. [Provenance](PROVENANCE.md).

## Public Surface

Python: `from app.components.copilot_terminal import ProviderConfig, TerminalService`.
React: `CopilotTerminal` and `TerminalAction` from `@components/copilot_terminal/frontend`.
The host supplies React, lucide-react, `@xterm/xterm` 6.0.0 and `@xterm/addon-fit` 0.11.0.

Construct `TerminalService(cli, provider, workspace_root, token_provider, path=...)` with an
absolute standalone CLI, HTTPS model endpoint/deployment, private workspace, server-side
token/expiry callback and explicit PATH. The application owns identity, API mounting and
shutdown. Call `handle(action, headers, payload)` off the ASGI event loop; it returns
`(status, JSON body)`. Output polling may block for 15 seconds.

Native operations: info, start, output, input, resize, source, stop. Optional host callbacks:
`workspace_initializer`, `allowed_executables`, `operations`, `task_operations`. Operations
require the control key; task operations also accept a separate task key. React takes
`apiBase`, `active`, optional source and prepared actions. Keep mounted across view changes;
sessionStorage supports reconnect. `close()` terminates all service sessions.

## Access and Limits

Requires loopback Host, exactly matching HTTP Origin, JSON and `X-Copilot-Terminal: 1`.
The application must add its own owner check; this is not multi-user login. Never expose on
a shared/cloud host by relying on loopback alone. CyberEye mounts only in its workstation
composition and preserves Host through Vite's proxy.

The provider token never goes to browser state. Private HOME and explicit child environment
avoid ambient settings. The CLI secret-environment flag excludes the token from shell/MCP
environments. PTY redacts provider/task credentials including split reads. Do not log request
bodies, keys or environments. Task keys are mode-0600 files beside, not inside, the workspace.

Defaults: four sessions, five-minute disconnected idle expiry, one-hour lifetime bounded by
provider expiry, one million replay characters. Stop revokes the session and kills its process
group; private files remain. No CLI binary is bundled. Version 1.0.83 was used for CyberEye.
A VS Code shim may fail under private HOME: use the standalone path.

Only supplied workspace executables receive shell preapproval. Native limited autopilot can
auto-deny other requests; it is not blanket permission. A private workspace is **not an OS
sandbox**: approved programs run as the host OS user. Stronger isolation requires another
user/container and is not implemented here. CyberEye's
[integration contract](../../../docs/AGENT_OPTIMIZATION.md) owns GUIDE semantics, helper
operations, cancellation, immutable artifacts and browser acceptance.