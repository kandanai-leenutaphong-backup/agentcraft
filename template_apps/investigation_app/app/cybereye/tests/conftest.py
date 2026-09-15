"""Offline test coordinates, installed before application configuration is imported."""

import os


os.environ.update({
    "ADX_CLUSTER_URI": "https://fixture.australiaeast.kusto.windows.net",
    "ADX_DATABASE": "PerthCyber",
    "CYBEREYE_TABLE": "EventsUnified",
    "CYBEREYE_EXTRA_TABLES": "",
    "CYBEREYE_OPENAI_ENDPOINT": "https://fixture.openai.azure.com/openai/v1/",
    "CYBEREYE_SEARCH_ENDPOINT": "https://fixture.search.windows.net",
    "CYBEREYE_MITRE_SEARCH_INDEX": "mitre-fixture",
    "GREMLIN_ACCOUNT": "",
    "DEV_PUBLIC_KEY_ED25519": "",
    "DEV_REPLAY_LEDGER": "",
    "AUTH_TENANT_ID": "",
    "AUTH_CLIENT_ID": "",
})