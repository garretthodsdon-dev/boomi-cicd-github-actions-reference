"""Run Boomi test-harness processes in an environment and collect JUnit results.

A harness is a process named "<Process Name> - Test" (see manifest.match_test_harnesses). It must
end in a Return Documents step that returns JUnit XML, and raise an error (Exception step) when an
assertion fails. The execution status is the gate; the JUnit document is the evidence.
"""
import os
import re
import time
from xml.sax.saxutils import escape, quoteattr

from . import gh
from .api import BoomiError, all_of, eq

PENDING = {"INPROCESS", "STARTED", "QUEUED", None}


def _slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()


def failure_junit(name, status, message):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name={quoteattr(name)} tests="1" failures="1" errors="0">\n'
        f'  <testcase classname="boomi.harness" name={quoteattr(name + " harness")}>\n'
        f'    <failure message={quoteattr(f"Harness execution {status}")}>{escape(message or "")}</failure>\n'
        "  </testcase>\n</testsuite>\n"
    )


def execute(client, runtime_id, process_id, timeout=300, poll=5):
    request_id = client.post("ExecutionRequest", {
        "@type": "ExecutionRequest", "atomId": runtime_id, "processId": process_id,
    }).json()["requestId"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"ExecutionRecord/async/{request_id}", allow=(202,))
        if resp.status_code == 200:
            record = resp.json()["result"][0]
            if record.get("status") not in PENDING:
                return record
        time.sleep(poll)
    raise BoomiError(f"Execution {request_id} did not finish within {timeout}s")


def _wait_for(fetch, timeout, poll=5):
    """Call fetch() until it returns something truthy or the timeout passes."""
    deadline = time.monotonic() + timeout
    while True:
        result = fetch()
        if result or time.monotonic() >= deadline:
            return result
        time.sleep(poll)


def returned_document(client, execution_id, timeout=180):
    """Download the first document that reached a Return Documents step, or None.

    Execution details can become available shortly after the execution reports COMPLETE, so wait
    for the records to appear.
    """
    connectors = _wait_for(lambda: client.query("ExecutionConnector", all_of(
        eq("executionId", execution_id), eq("connectorType", "return"))), timeout)
    if not connectors:
        return None
    records = _wait_for(lambda: client.query("GenericConnectorRecord", all_of(
        eq("executionId", execution_id), eq("executionConnectorId", connectors[0]["id"]))), timeout)
    if not records:
        return None

    def request_download():
        # The document may not be retrievable immediately (the API answers 400); retry until it is.
        resp = client.post("ConnectorDocument", {"genericConnectorRecordId": records[0]["id"]}, allow=(400,))
        return resp.json().get("url") if resp.status_code != 400 else None

    url = _wait_for(request_download, timeout)
    if not url:
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(url, accept="*/*", allow=(202, 204))
        if resp.status_code == 200 and resp.content:
            return resp.text.replace("\r\n", "\n").strip() + "\n"
        time.sleep(2)
    return None


def run_tests(client, release, env_name, runtime_name, out_dir=".", log=print):
    """Run every harness in the release. Returns a list of failed component names."""
    env_id, runtime_id = client.environment_id(env_name), client.runtime_id(runtime_name)
    rows, failed = [], []
    for c in release["components"]:
        harness_id = c.get("testHarnessId")
        if not harness_id:
            continue
        # Package the harness at the release's version so the two stay in lockstep, and deploy
        # it — an execution request can only run a deployed process.
        package = client.find_package(harness_id, c["packageVersion"]) or client.create_package(
            harness_id, c["packageVersion"], f"Test harness for {c['name']} {c['packageVersion']}")
        active = client.active_deployment(env_id, harness_id)
        if not active or active["packageId"] != package["packageId"]:
            client.deploy(package["packageId"], env_id, f"Test harness for {c['name']} {c['packageVersion']}")

        log(f"[test] {c['name']} {c['packageVersion']}: running harness on {runtime_name}")
        record = execute(client, runtime_id, harness_id)
        status = record.get("status")
        junit = returned_document(client, record["executionId"]) if status == "COMPLETE" else None
        if status != "COMPLETE":
            failed.append(c["name"])
            junit = failure_junit(c["name"], status, record.get("message", ""))
        elif not junit:
            failed.append(c["name"])
            junit = failure_junit(c["name"], "returned no JUnit document", "Harness must end in Return Documents with JUnit XML.")
        with open(os.path.join(out_dir, f"test-{_slug(c['name'])}.xml"), "w", encoding="utf-8") as f:
            f.write(junit)
        rows.append((c["name"], c["packageVersion"], status, "✅ passed" if c["name"] not in failed else "❌ failed"))
        log(f"[test] {c['name']}: {status}")

    gh.summary(f"### Automated tests in {env_name}\n\n" + (
        gh.table(["Component", "Version", "Execution", "Result"], rows) if rows else "No test harnesses in this release.\n"))
    return failed
