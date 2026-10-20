"""Create the connector-free demo components in a Boomi folder (samples/components/*.xml)."""
import glob
import os
import re

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples", "components")


def create_samples(client, folder_id, package_version=None, log=print):
    """Create the sample profile and processes in order, wiring IDs between them."""
    ids = {"FOLDER_ID": folder_id}
    keys = {"01": "PROFILE_ID", "02": "ORDER_ACK_ID", "03": "CUSTOMER_SYNC_ID", "04": "HARNESS_ID"}
    for path in sorted(glob.glob(os.path.join(SAMPLES_DIR, "*.xml"))):
        with open(path, encoding="utf-8") as f:
            xml = f.read()
        for key, value in ids.items():
            xml = xml.replace("{{" + key + "}}", value)
        leftover = re.findall(r"\{\{[A-Z_]+\}\}", xml)
        if leftover:
            raise RuntimeError(f"{os.path.basename(path)}: unresolved placeholders {leftover}")
        created = client.create_component(xml)
        component_id = re.search(r'componentId="([^"]+)"', created).group(1)
        name = re.search(r'\sname="([^"]+)"', created).group(1)
        ids[keys[os.path.basename(path)[:2]]] = component_id
        log(f"[samples] created {name} ({component_id})")

    if package_version:
        for key in ("ORDER_ACK_ID", "CUSTOMER_SYNC_ID"):
            pkg = client.create_package(ids[key], package_version, "Initial sample release")
            log(f"[samples] packaged {ids[key]} as {package_version} ({pkg['packageId']})")
    return ids
