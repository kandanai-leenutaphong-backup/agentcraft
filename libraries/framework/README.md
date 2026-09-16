# Agentcraft Framework

One public composition and discovery surface over canonical capabilities. The framework
does not contain another data client, model loop, authorization system or lifecycle engine.
`appcompose` validates the dependency graph and owns startup/shutdown.

Install the selected package extras from reviewed wheels or a published registry. Local
workspace development uses `uv run --project libraries --package agentcraft`; no runtime
imports a skill or assumes a sibling checkout. Registry publication is separate.

```python
import asyncio
from agentcraft import Binding, Framework

class Example:
    async def read(self):
        return {"fixture": True, "value": 7}
    async def aclose(self):
        pass

async def main():
    async with Framework({"example": Binding("example.read", Example(), owned=True)}) as app:
        result = await app.get("example", Example).read()
        assert result["value"] == 7

asyncio.run(main())
```

Bind real `azdata.connect(...)` and `llm_interface.connect(...)` values explicitly; their
configuration, credentials, grants and specialized requests remain typed. `app.data(name)`
and `app.model(name)` validate the bound type. Plain construction and `describe()` perform
no service call, credential acquisition, thread startup or state write.

Bindings are borrowed unless `owned=True`. Owned repeated handles close once, dependents
close before dependencies, and appcompose retains unsafe shutdown state. New access after
close refuses. Creating a run context never grants access; native capability policies are
still required. Use `ExecutionContext` for shared bounded calls, without automatic retries.

The optional MCP host loads only operator-configured bindings and installed public APIs.
Pure Python use, frontend source rendering and rule execution need no MCP or hosted service.