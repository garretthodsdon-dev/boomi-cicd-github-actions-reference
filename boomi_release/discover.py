"""Build a release manifest from the Packaged Components in a Boomi folder (and its subfolders)."""
from . import manifest as mf
from .api import BoomiError, all_of, eq


def resolve_folder(client, path):
    """Return the folder id for a path, with or without the account root folder prefix."""
    path = path.strip().strip("/")
    leaf = path.split("/")[-1]
    matches = [
        f for f in client.query("Folder", eq("name", leaf))
        if not f.get("deleted") and (f.get("fullPath") == path or f.get("fullPath", "").endswith("/" + path))
    ]
    if not matches:
        raise BoomiError(f"Folder '{path}' not found")
    if len(matches) > 1:
        paths = ", ".join(f["fullPath"] for f in matches)
        raise BoomiError(f"Folder '{path}' is ambiguous ({paths}) — use the full path")
    return matches[0]["id"], matches[0]["fullPath"]


def folder_tree(client, root_id):
    ids, queue = [root_id], [root_id]
    while queue:
        children = client.query("Folder", eq("parentId", queue.pop(0)))
        for child in children:
            if not child.get("deleted"):
                ids.append(child["id"])
                queue.append(child["id"])
    return ids


def discover(client, folder, branch="main", test_suffix=" - Test", log=print):
    root_id, full_path = resolve_folder(client, folder)
    folder_ids = folder_tree(client, root_id)
    log(f"[discover] {full_path}: {len(folder_ids)} folder(s)")

    components = []
    for fid in folder_ids:
        for c in client.query("ComponentMetadata", all_of(
            eq("folderId", fid), eq("currentVersion", "true"), eq("deleted", "false"),
        )):
            if c.get("type") in mf.DEPLOYABLE_TYPES:
                components.append(c)
    components = list({c["componentId"]: c for c in components}.values())
    harnesses, harness_ids = mf.match_test_harnesses(components, test_suffix)
    log(f"[discover] {len(components)} deployable component(s), {len(harnesses)} test harness(es)")

    entries = []
    for c in components:
        if c["componentId"] in harness_ids:
            continue  # harnesses run in DEV only; never released on their own
        packages = client.query("PackagedComponent", eq("componentId", c["componentId"]))
        latest = mf.pick_latest_package(packages, branch)
        if not latest:
            log(f"[discover] skip {c['name']}: no package on branch '{branch}'")
            continue
        entry = {
            "componentId": c["componentId"],
            "name": c["name"],
            "type": c["type"],
            "packageVersion": latest["packageVersion"],
            "packageId": latest["packageId"],
            "componentVersion": latest.get("componentVersion"),
            "branchName": latest.get("branchName") or "main",
            "createdDate": latest.get("createdDate"),
        }
        if c["componentId"] in harnesses:
            entry["testHarnessId"] = harnesses[c["componentId"]]["componentId"]
        entries.append(entry)
        log(f"  {c['name']} → {entry['packageVersion']}{'  [+test]' if 'testHarnessId' in entry else ''}")

    # No timestamp here: the manifest must only change when a package changes, or every run
    # would look like a new release.
    return {"release": {"folder": full_path, "branch": branch}, "components": entries}
