"""Call an existing Azure model deployment using an async Azure credential."""

import argparse
import asyncio

from azure.identity.aio import AzureCliCredential
from azure_foundry import respond


def call(prompt: str, *, endpoint: str, deployment: str, credential) -> str:
    return asyncio.run(respond(
        prompt, endpoint=endpoint, deployment=deployment, credential=credential,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--tenant-id", required=True)
    args = parser.parse_args()

    credential = AzureCliCredential(tenant_id=args.tenant_id)
    try:
        print(call(
            args.prompt,
            endpoint=args.endpoint,
            deployment=args.deployment,
            credential=credential,
        ))
    finally:
        asyncio.run(credential.close())