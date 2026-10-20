"""Lint the exact packaged version of every component in a manifest against XPath rules."""
import json
import os

from lxml import etree

from . import gh

NAMESPACES = {"bns": "http://api.platform.boomi.com/"}
RULES_FILE = os.path.join(os.path.dirname(__file__), "lint_rules.json")


def load_rules(path=None):
    with open(path or RULES_FILE, encoding="utf-8") as f:
        return json.load(f)["rules"]


def check_xml(xml_text, rules):
    """Return the rules that fire for one component XML document."""
    root = etree.fromstring(xml_text.encode("utf-8"))
    return [r for r in rules if root.xpath(r["xpath"], namespaces=NAMESPACES)]


def lint(client, release, fail_on=(), rules_path=None, report_path="lint-report.md", log=print):
    rules = load_rules(rules_path)
    findings = []
    for c in release["components"]:
        xml = client.component_xml(c["componentId"], c.get("componentVersion"))
        for rule in check_xml(xml, rules):
            findings.append((c["name"], c["packageVersion"], rule["id"], rule["description"], rule["priority"]))

    fail_on = {p.strip().upper() for p in fail_on if p.strip()}
    blocking = [f for f in findings if f[4] in fail_on]

    report = f"### Boomi lint — {len(release['components'])} component(s), {len(findings)} finding(s)\n\n"
    report += gh.table(["Component", "Version", "Rule", "Finding", "Priority"], findings) if findings else "No findings. ✅\n"
    if fail_on:
        report += f"\nFails on: {', '.join(sorted(fail_on))} — {len(blocking)} blocking finding(s).\n"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    gh.summary(report)
    for f_ in findings:
        log(f"[lint] {f_[4]:<5} {f_[0]} {f_[1]}: {f_[3]}")
    log(f"[lint] {len(findings)} finding(s), {len(blocking)} blocking")
    return blocking
