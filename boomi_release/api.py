"""Minimal client for the Boomi Platform API (AtomSphere REST API).

Configuration comes from environment variables:

    BOOMI_ACCOUNT_ID   e.g. mycompany-AB12CD
    BOOMI_USERNAME     API user; "BOOMI_TOKEN." is prefixed automatically if missing
    BOOMI_API_TOKEN    Platform API token for that user
    BOOMI_API_URL      optional, defaults to https://api.boomi.com/api/rest/v1
"""
import os
import time

import requests

DEFAULT_API_URL = "https://api.boomi.com/api/rest/v1"
_RETRY_STATUS = {429, 503}


class BoomiError(RuntimeError):
    """Raised when the Platform API returns an error."""


class BoomiClient:
    def __init__(self, account_id=None, username=None, token=None, api_url=None, min_interval=0.2):
        self.account_id = account_id or os.environ.get("BOOMI_ACCOUNT_ID", "")
        username = username or os.environ.get("BOOMI_USERNAME", "")
        token = token or os.environ.get("BOOMI_API_TOKEN", "")
        if not (self.account_id and username and token):
            raise BoomiError("Set BOOMI_ACCOUNT_ID, BOOMI_USERNAME and BOOMI_API_TOKEN.")
        if not username.startswith("BOOMI_TOKEN."):
            username = f"BOOMI_TOKEN.{username}"
        root = (api_url or os.environ.get("BOOMI_API_URL") or DEFAULT_API_URL).rstrip("/")
        if not root.endswith("/api/rest/v1"):
            root += "/api/rest/v1"  # accept a bare host such as https://api.boomi.com
        self.base = f"{root}/{self.account_id}"
        self.session = requests.Session()
        self.session.auth = (username, token)
        self.min_interval = min_interval  # stay well under the Platform API rate limit
        self._last_call = 0.0

    # -- transport -----------------------------------------------------------------------------

    def request(self, method, path, *, json_body=None, data=None, accept="application/json",
                content_type="application/json", allow=()):
        """Send a request, retrying on 429/503. Returns the response; raises BoomiError otherwise."""
        url = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
        headers = {"Accept": accept}
        if json_body is not None or data is not None:
            headers["Content-Type"] = content_type
        for attempt in range(6):
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            resp = self.session.request(method, url, json=json_body, data=data, headers=headers, timeout=60)
            if resp.status_code in _RETRY_STATUS and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            if resp.ok or resp.status_code in allow:
                return resp
            raise BoomiError(f"{method} {path} → HTTP {resp.status_code}: {resp.text[:500]}")
        raise BoomiError(f"{method} {path} → gave up after retries")

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, json_body=body, **kw)

    def query(self, obj, expression=None):
        """Run an object query and follow queryMore pages. Returns all result records."""
        body = {"QueryFilter": {"expression": expression}} if expression else {}
        page = self.post(f"{obj}/query", body).json()
        results = list(page.get("result", []))
        while page.get("queryToken"):
            page = self.request("POST", f"{obj}/queryMore", data=page["queryToken"],
                                content_type="text/plain").json()
            results.extend(page.get("result", []))
        return results

    # -- lookups used across commands ----------------------------------------------------------

    def environment_id(self, name):
        found = self.query("Environment", eq("name", name))
        if not found:
            raise BoomiError(f"Boomi environment '{name}' not found")
        return found[0]["id"]

    def runtime_id(self, name):
        found = self.query("Atom", eq("name", name))
        if not found:
            raise BoomiError(f"Boomi runtime '{name}' not found")
        return found[0]["id"]

    def deployments(self, environment_id, component_id, active_only=False):
        """DeployedPackage records for a component in an environment, newest first."""
        clauses = [eq("environmentId", environment_id), eq("componentId", component_id)]
        if active_only:
            clauses.append(eq("active", "true"))
        records = self.query("DeployedPackage", all_of(*clauses))
        return sorted(records, key=lambda r: r.get("version", 0), reverse=True)

    def active_deployment(self, environment_id, component_id):
        records = self.deployments(environment_id, component_id, active_only=True)
        return records[0] if records else None

    def deploy(self, package_id, environment_id, notes):
        resp = self.post("DeployedPackage", {"environmentId": environment_id, "packageId": package_id, "notes": notes[:255]})
        return resp.json()["deploymentId"]

    def find_package(self, component_id, package_version):
        found = self.query("PackagedComponent", all_of(eq("componentId", component_id), eq("packageVersion", package_version)))
        live = [p for p in found if not p.get("deleted")]
        return live[0] if live else None

    def create_package(self, component_id, package_version, notes="", branch_name=None):
        body = {"componentId": component_id, "packageVersion": package_version, "notes": notes}
        if branch_name:
            body["branchName"] = branch_name
        return self.post("PackagedComponent", body).json()

    def component_xml(self, component_id, version=None):
        ref = f"{component_id}~{version}" if version else component_id
        return self.get(f"Component/{ref}", accept="application/xml").text

    def create_component(self, xml):
        return self.request("POST", "Component", data=xml.encode("utf-8"),
                            content_type="application/xml", accept="application/xml").text


def eq(prop, value):
    return {"argument": [value], "operator": "EQUALS", "property": prop}


def all_of(*clauses):
    return {"operator": "and", "nestedExpression": list(clauses)}
