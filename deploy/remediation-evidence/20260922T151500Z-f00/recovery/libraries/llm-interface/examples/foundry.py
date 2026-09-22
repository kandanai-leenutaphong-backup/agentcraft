"""Explicit opt-in live example. Default invocation only describes the connection."""

import argparse
import asyncio
import json

from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential

from llm_interface import connect


def add(left: int, right: int) -> dict:
    """Add two integer values without any external side effect."""
    return {"sum": left + right}


async def main(args):
    identity = ManagedIdentityCredential() if args.identity == "managed" else AzureCliCredential()
    async with identity, connect(args.endpoint, args.model, credential=identity,
                                 allow_model_calls=args.confirm_live,
                                 allowed_tools=("add",) if args.agent else ()) as model:
        if not args.confirm_live:
            print(json.dumps(model.describe(), indent=2))
            return
        if not args.agent:
            print((await model.chat.get_response(args.prompt)).text)
            return
        agent = model.agent(instructions="Use add for arithmetic and answer briefly.", tools=[add])
        async with agent.run(args.prompt, stream=True) as stream:
            async for event in stream:
                if event.text:
                    print(event.text, end="", flush=True)
            await stream.get_final_response()
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--identity", choices=("managed", "cli"), default="managed")
    parser.add_argument("--prompt", default="What is 12 plus 30?")
    parser.add_argument("--agent", action="store_true")
    parser.add_argument("--confirm-live", action="store_true", help="Authorize paid inference against this exact target.")
    asyncio.run(main(parser.parse_args()))