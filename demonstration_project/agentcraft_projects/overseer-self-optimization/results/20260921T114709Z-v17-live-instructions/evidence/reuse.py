"""Pinned reuse and explicit existing dependency paths; no installation."""

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
WORKSPACE = ROOT.parents[5]
REPAIR = PROJECT / 'results/20260921T110854Z-v17-capture-repair/evidence'
PRIOR = PROJECT / 'results/20260921T102309Z-v17-native-development/evidence'
SITE = Path('/tmp/agentcraft-investigation-browser-env/lib/python3.12/site-packages')
sys.path.append(str(SITE))
sys.path.append(str(WORKSPACE / 'libraries/signed-dev-access/src'))
sys.path.append(str(REPAIR))
ORIGINS = {
    'native.py': 'cc26124d67701a8085fe76c0505fe45a64cb3f09fe2ac55bee0ab248c9c87a81',
    'capture.py': '23da86a1729c2d349bd3645e6d5264dd98d6ecdd827c0e740aea923e0b745e33',
    'live_inputs.py': '51fc1a85ff7820e419434771e1664efaee6463aacd580951e5a22dc27ef05795',
    'oracle.json': 'cc496ad31bef8b95cf02298d07fe5c9d258f699d80f18ca6a73969bd95a0372f',
}
REPAIR_PINS = {
    'capture.py': '22b86cc6e2d5f430bcb5aa18fbd9a5f0ba82e397131e0a3633fc206c062f05a4',
    'verify.py': '22aa08fbc1fe254b07288dfd63c10039ce53ac1600785292121a796890dec10d',
    'test_capture.py': 'cfe4fc2cd3bd0fd6c25229ff859f93111ff3d0ff7d79a116a5bff8558827fa26',
    'evaluate.py': '90e6929322ebd84bb7d7bba599b79b3d8e0761d2cfe944e775f01451dd165abb',
}
PINS = {
    PROJECT / 'constitution/constitution.yaml': 'b9c699eb03171cbc10afaead895e271a69367d6f46e3f193e8a648daf81d33ab',
    PROJECT / 'records/v2/20260921T114607631721Z-v17-live-instructions-20260921-authorized/record.json': '45fc27b491ade2cbcfe3d0bac7f3960f55e1de8cc5556bb7002d8d60dfed1295',
    PROJECT / 'records/v2/20260921T114607680099Z-v17-live-instructions-20260921-prestate/record.json': 'f057b9d2574b76ba8f33511a64e37ccaf7674e380f9928fa2736a72e71d2317e',
    WORKSPACE / '.github/agents/local-dev-test-subject.agent.md': '3249899b68faee39e431fc2432221119430c785216d5087a826596936c4cee0a',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(content):
    return hashlib.sha256(content).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    assert json.loads(path.read_text()) == value


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def now():
    return datetime.now(timezone.utc).isoformat()


def receipts(kind):
    return sorted(ROOT.glob('[0-9]*Z-' + kind + '.json'))


def load(name, repair=False):
    base, pins = (REPAIR, REPAIR_PINS) if repair else (PRIOR, ORIGINS)
    path = base / (name + '.py')
    assert sha(path) == pins[path.name]
    spec = importlib.util.spec_from_file_location(('repair_' if repair else 'prior_') + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assert sha(REPAIR / 'capture.py') == REPAIR_PINS['capture.py']


def pins():
    for path, expected in PINS.items():
        assert sha(path) == expected, path.name
    for base, entries in ((PRIOR, ORIGINS), (REPAIR, REPAIR_PINS)):
        for name, expected in entries.items():
            assert sha(base / name) == expected, name


def acquire(phase):
    owner = load('live_inputs')
    owner.ROOT = ROOT
    return owner.collect(phase)