"""Deploy, promote and roll back releases, and apply per-environment configuration."""
import json
import os

from . import gh
from . import manifest as mf
from .api import BoomiError

CONFIG_DIR = os.path.join("config", "environments")


def _package_id(client, component):
    if component.get("packageId"):
        return component["packageId"]
    package = client.find_package(component["componentId"], component["packageVersion"])
    if not package:
        raise BoomiError(f"{component['name']}: package {component['packageVersion']} not found")
    return package["packageId"]


def apply_config(client, env_name, env_id, config_dir=CONFIG_DIR, dry_run=False, log=print):
    """Apply config/environments/<env_name>.json to the environment's extensions (partial update)."""
    path = os.path.join(config_dir, f"{env_name}.json")
    if not os.path.isfile(path):
        log(f"[config] no {path} — extensions unchanged")
        return []
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    try:
        values = mf.resolve_config_values(config.get("properties", {}))
    except ValueError as e:
        raise BoomiError(f"{path}: {e}") from e
    if values and not dry_run:
        client.post(f"EnvironmentExtensions/{env_id}/update", {
            "@type": "EnvironmentExtensions", "id": env_id, "environmentId": env_id, "partial": True,
            "properties": {"property": [{"name": n, "value": v} for n, v, _ in values]},
        })
    for name, _, shown in values:
        log(f"[config] {env_name}: {name} = {shown}{' (dry run)' if dry_run else ''}")
    if values:
        gh.summary(f"\n#### Configuration applied to {env_name}\n\n" + gh.table(["Extension", "Value"], [(n, s) for n, _, s in values]))
    return values


def deploy_release(client, release, env_name, label=None, notes_suffix="", dry_run=False, log=print):
    """Deploy every manifest package that is not already active. Returns ids of deployed components."""
    env_id = client.environment_id(env_name)
    rows, deployed = [], []
    for c in release["components"]:
        package_id = _package_id(client, c)
        active = client.active_deployment(env_id, c["componentId"])
        if active and active["packageId"] == package_id:
            rows.append((c["name"], c["packageVersion"], package_id, "⏸️ already active"))
            continue
        if not dry_run:
            client.deploy(package_id, env_id, f"{c['name']} {c['packageVersion']}{notes_suffix}")
        deployed.append(c["componentId"])
        was = active["packageVersion"] if active else "—"
        log(f"[deploy] {c['name']} {was} → {c['packageVersion']} in {env_name}{' (dry run)' if dry_run else ''}")
        rows.append((c["name"], c["packageVersion"], package_id, "🚀 deployed" + (" (dry run)" if dry_run else "")))
    gh.summary(f"### Deployed to {env_name}" + (f" ({label})" if label else "") + "\n\n"
               + gh.table(["Component", "Version", "Package ID", "Result"], rows))
    apply_config(client, env_name, env_id, dry_run=dry_run, log=log)
    return deployed


def promote(client, release, source_name, target_name, label, ticket="", actor="unknown", dry_run=False, log=print):
    """Promote the packages active in `source_name` to `target_name`. Refuses to skip a stage."""
    if label.upper() == "PROD" and not ticket:
        raise BoomiError("A change ticket is required to promote to PROD.")
    source_id, target_id = client.environment_id(source_name), client.environment_id(target_name)

    plan, problems = [], []
    for c in release["components"]:
        active = client.active_deployment(source_id, c["componentId"])
        if not active:
            problems.append(f"{c['name']}: not deployed in {source_name}")
        elif active["packageId"] != _package_id(client, c):
            problems.append(f"{c['name']}: {source_name} runs {active['packageVersion']}, release is {c['packageVersion']}")
        else:
            plan.append((c, active))
    if problems:
        gh.summary(f"### ❌ Promotion {source_name} → {target_name} blocked\n\n" + "".join(f"- {p}\n" for p in problems)
                   + "\nPromote one stage at a time: the release must be live in the source environment first.\n")
        raise BoomiError("Promotion blocked:\n  " + "\n  ".join(problems))

    suffix = f" | promoted from {source_name} by {actor}" + (f" | {ticket}" if ticket else "")
    rows = []
    for c, source in plan:
        current = client.active_deployment(target_id, c["componentId"])
        if current and current["packageId"] == source["packageId"]:
            rows.append((c["name"], current["packageVersion"], source["packageVersion"], source["packageId"], "⏸️ already active"))
            continue
        if not dry_run:
            client.deploy(source["packageId"], target_id, f"{c['name']} {source['packageVersion']}{suffix}")
        was = current["packageVersion"] if current else "—"
        log(f"[promote] {c['name']} {was} → {source['packageVersion']} in {target_name}{' (dry run)' if dry_run else ''}")
        rows.append((c["name"], was, source["packageVersion"], source["packageId"], "🚀 promoted" + (" (dry run)" if dry_run else "")))

    body = (f"### ✅ Promoted {source_name} → {target_name} ({label})\n\nRequested by **{actor}**"
            + (f" · change **{ticket}**" if ticket else "") + "\n\n"
            + gh.table(["Component", "Was", "Now", "Package ID (same as source)", "Result"], rows))
    gh.summary(body)
    apply_config(client, target_name, target_id, dry_run=dry_run, log=log)
    return body


def rollback(client, release, env_name, label=None, only_ids=(), only_name="", reason="rollback",
             actor="unknown", dry_run=False, log=print):
    """Redeploy the previous package of each component from the environment's deployment history."""
    env_id = client.environment_id(env_name)
    rows = []
    for c in release["components"]:
        if (only_ids and c["componentId"] not in only_ids) or (only_name and c["name"] != only_name):
            continue
        active, previous = mf.previous_deployment(client.deployments(env_id, c["componentId"]))
        if not active:
            rows.append((c["name"], "—", "—", "—", "⚠️ not deployed"))
            continue
        if not previous:
            rows.append((c["name"], active["packageVersion"], "—", "—", "⚠️ no earlier version"))
            continue
        if not dry_run:
            client.deploy(previous["packageId"], env_id,
                          f"{c['name']} ROLLBACK {active['packageVersion']} → {previous['packageVersion']} by {actor} | {reason}")
        log(f"[rollback] {c['name']} {active['packageVersion']} → {previous['packageVersion']} in {env_name}{' (dry run)' if dry_run else ''}")
        rows.append((c["name"], active["packageVersion"], previous["packageVersion"], previous["packageId"],
                     "⏪ rolled back" + (" (dry run)" if dry_run else "")))
    gh.summary(f"### ⏪ Rollback in {env_name}" + (f" ({label})" if label else "") + f"\n\nRequested by **{actor}** · {reason}\n\n"
               + gh.table(["Component", "Was", "Restored", "Package ID", "Result"], rows)
               + "\n`release/release.json` still lists the newer versions — revert the release PR (or merge a fix) before promoting again.\n")
    return rows
