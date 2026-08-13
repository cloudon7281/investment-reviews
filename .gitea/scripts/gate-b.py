#!/usr/bin/env python3
"""Gate B, pre-merge half (deploy-model §1a.3, SDI §1.2b).

Fails the PR when it changes a field that would relocate the service's live state. Stdlib only: the
jarvis Actions runner is host-mode and carries python3/curl/git and nothing else.

This is the *cheap conversation* half of Gate B. The authoritative one runs at registration and
fails closed; a pre-merge check can always be bypassed. It exists because blocking after merge
leaves `main` carrying a manifest that cannot be deployed — and, with auto-tag-on-merge, possibly a
released tag that will never run, which is its own silent divergence.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

# SDI §1.2b: the fields that decide where state lives. Everything else is safe to change while
# deployed. Keep in step with _SERVICE_YAML_FIELDS in tier2-project's parser.
UNSAFE_FIELDS = ("stack", "srvName")

REGISTRY = "/Users/cl/srv/tier2-project/state/exports/registered-services.json"


def _api(path: str):
    req = urllib.request.Request(
        os.environ["API_BASE"] + path,
        headers={"Authorization": "token " + os.environ["TOKEN"]},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _manifest_at(ref: str) -> dict | None:
    """deploy/service.yaml at `ref`, or None if the repo has none (not a service repo)."""
    import base64
    try:
        obj = _api(f"/repos/{os.environ['REPO']}/contents/deploy/service.yaml?ref={ref}")
    except Exception:
        return None
    raw = base64.b64decode((obj.get("content") or "").replace("\n", "")).decode("utf-8")
    # Deliberately not PyYAML: the runner has no third-party packages, and the two fields we need
    # are top-level scalars. Anything more structured is the registration gate's job.
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if line[:1].isspace() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.split("#", 1)[0].strip().strip("'\"")
        if key.strip() in UNSAFE_FIELDS and value:
            out[key.strip()] = value
    return out


def _is_deployed(stack: str) -> bool | None:
    """True/False from the registry when it is readable here, else None (unknown).

    The runner is a host process on jarvis, so it usually can read this. Treated as advisory: an
    unknown answer still fails the check, because the safe default pre-merge is to have the
    conversation.
    """
    try:
        with open(REGISTRY) as fh:
            services = (json.load(fh) or {}).get("services") or {}
    except Exception:
        return None
    for rec in services.values():
        if isinstance(rec, dict) and rec.get("stack") == stack:
            return True
    return False


def main() -> int:
    head = _manifest_at(os.environ["HEAD_SHA"])
    base = _manifest_at(os.environ["BASE_REF"])
    if head is None or base is None:
        print("[gate-b] no deploy/service.yaml on one side — nothing to check.")
        return 0

    changed = {f: (base.get(f), head.get(f)) for f in UNSAFE_FIELDS
               if base.get(f) != head.get(f)}
    if not changed:
        print(f"[gate-b] {', '.join(UNSAFE_FIELDS)} unchanged — safe to merge while deployed.")
        return 0

    deployed = _is_deployed(base.get("stack") or "")
    print("[gate-b] REFUSED: this PR changes a field that decides where the service's state lives.")
    for field, (was, now) in changed.items():
        print(f"    {field}: {was!r} -> {now!r}")
    if deployed is False:
        print("  The registry says this service is not registered, so there may be nothing to")
        print("  abandon — but confirm before merging: registration will make the final call.")
    elif deployed is None:
        print("  Could not read the registry from here, so this cannot tell whether the service is")
        print("  deployed. Treated as unsafe: the point of a pre-merge check is the conversation.")
    else:
        print("  This service IS registered. Applying this would leave its real state stranded at")
        print("  the old path while the registry, backups and monitoring point at a new, empty one.")
    print("  Registration cannot move data, only describe it (deploy-model §1a.2, SDI §1.2b).")
    print("  Supported route: undeploy first, then register and deploy, restoring from backup if")
    print("  the state matters — backup artefacts are keyed by stack and survive both.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
