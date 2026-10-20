"""The release manifest (release/release.json) and helpers that need no API access.

A manifest pins one Packaged Component per Boomi component:

    {"components": [{"componentId": "...", "name": "Order Sync", "type": "process",
                     "packageVersion": "1.3", "packageId": "...", "componentVersion": 5,
                     "branchName": "main", "createdDate": "...", "testHarnessId": "..."}]}
"""
import json
import os

DEPLOYABLE_TYPES = {
    "process", "webservice", "webservice.external", "flowservice", "processroute",
    "tpgroup", "customlibrary", "certificate",
}


def load(path):
    """Load a manifest; a missing or unreadable file is an empty release."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"components": []}
    data.setdefault("components", [])
    return data


def save(path, manifest):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    manifest["components"].sort(key=lambda c: c["name"].lower())
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def pick_latest_package(packages, branch="main"):
    """Newest non-deleted package on `branch`, by creation time.

    Package versions are free text ("1.2", "2025.12.22", "hotfix-7"), so creation time — not the
    version string — decides which package is newest. Packages without a branchName predate
    Branch & Merge and belong to main.
    """
    candidates = [
        p for p in packages
        if not p.get("deleted") and (p.get("branchName") or "main") == branch
    ]
    return max(candidates, key=lambda p: p.get("createdDate", ""), default=None)


def match_test_harnesses(components, suffix=" - Test"):
    """Map tested component id → harness component, by naming convention.

    A process named "<Name><suffix>" in the scanned folders is the automated test for the
    process named "<Name>". Returns ({tested_id: harness}, {harness ids}).
    """
    if not suffix:
        return {}, set()
    by_name = {c["name"]: c for c in components if c.get("name")}
    harnesses = {}
    for c in components:
        name = c.get("name", "")
        if name.endswith(suffix) and len(name) > len(suffix):
            tested = by_name.get(name[: -len(suffix)])
            if tested and tested["componentId"] != c["componentId"]:
                harnesses[tested["componentId"]] = c
    return harnesses, {h["componentId"] for h in harnesses.values()}


def diff(old, new):
    """Rows of (change, name, type, from_version, to_version, has_test) between two manifests."""
    before = {c["componentId"]: c for c in old.get("components", [])}
    after = {c["componentId"]: c for c in new.get("components", [])}
    rows = []
    for cid, c in after.items():
        test = bool(c.get("testHarnessId"))
        if cid not in before:
            rows.append(("added", c["name"], c["type"], None, c["packageVersion"], test))
        elif before[cid]["packageId"] != c["packageId"]:
            rows.append(("updated", c["name"], c["type"], before[cid]["packageVersion"], c["packageVersion"], test))
    for cid, c in before.items():
        if cid not in after:
            rows.append(("removed", c["name"], c["type"], c["packageVersion"], None, False))
    return rows


def diff_markdown(old, new):
    """Pull-request body describing a release."""
    labels = {"added": "🆕 Added", "updated": "⬆️ Updated", "removed": "🗑️ Removed"}
    rows = diff(old, new)
    lines = [
        "## Boomi release request",
        "",
        "Generated from Packaged Components in Boomi. Merging this PR releases to **DEV** (deploy, DEV "
        "configuration, automated tests with automatic rollback on failure). **QA** and **PROD** follow with "
        "the *Boomi Promote* workflow, which moves the same packages.",
        "",
    ]
    if rows:
        lines += ["| Change | Component | Type | From | To | Auto-test |", "|---|---|---|---|---|---|"]
        for change, name, ctype, frm, to, test in rows:
            lines.append(f"| {labels[change]} | {name} | {ctype} | {frm or '—'} | {to or '—'} | {'✅' if test else ''} |")
    else:
        lines.append("_No version changes._")
    unchanged = len(new.get("components", [])) - sum(1 for r in rows if r[0] != "removed")
    lines += ["", f"{unchanged} component(s) unchanged. Full manifest: `release/release.json`."]
    return "\n".join(lines) + "\n"


def previous_deployment(history):
    """Return (active, rollback target) from an environment's deployment history.

    The rollback target is what ran before the active package was *first* introduced — not
    simply the last different deployment. After rolling back 1.5 → 1.3, the next rollback must
    go to 1.2, not flip back to 1.5.
    """
    active = next((d for d in history if d.get("active")), None)
    if not active:
        return None, None
    introduced = min(d.get("version", 0) for d in history if d["packageId"] == active["packageId"])
    earlier = [d for d in history if d.get("version", 0) < introduced and d["packageId"] != active["packageId"]]
    previous = max(earlier, key=lambda d: d.get("version", 0), default=None)
    return active, previous


def resolve_config_values(properties, environ=None):
    """Resolve "$env:NAME" values from the environment. Returns [(name, value, display)]."""
    environ = os.environ if environ is None else environ
    resolved = []
    for name, value in properties.items():
        if isinstance(value, str) and value.startswith("$env:"):
            var = value[5:]
            if not environ.get(var):
                # Boomi stores an empty string literally, so never write a missing secret as "".
                raise ValueError(f"{name}: environment variable {var} is not set (map it from a GitHub secret)")
            resolved.append((name, environ[var], "•••• (from secret)"))
        else:
            resolved.append((name, value, value))
    return resolved
