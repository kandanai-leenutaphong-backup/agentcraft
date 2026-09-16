---
name: web-resource
description: "Use when acquiring public documentation, reference images or screenshots with guarded transport, robots policy, rate limits and verifiable provenance."
---

# Web Resource

Install `harness-web-resource`; use `webres.fetch`, `Catalogue`, `Provenance`, `validate_url`
and the `web-resource-*` commands. Read the canonical [guide](../../../libraries/web-resource/GUIDE.md)
and [installation and verification](../../../libraries/web-resource/README.md).

Python 3.11+; screenshots additionally require the declared `browser` extra and existing Chromium.
Public-only URLs, DNS/redirect checks, robots.txt, rate limits and provenance remain mandatory.
No login, private-network access, paywall bypass or acquisition permission follows from installation.
Host chooses output/catalogue locations; downloaded material remains untrusted publisher-owned content.
Tests use local fixtures, never public acquisition or collection refresh.