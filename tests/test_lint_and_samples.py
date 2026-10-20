import glob
import os
import re

from lxml import etree

from boomi_release.lint import check_xml, load_rules

ROOT = os.path.dirname(os.path.dirname(__file__))
SAMPLES = sorted(glob.glob(os.path.join(ROOT, "samples", "components", "*.xml")))

BAD_PROCESS = """<?xml version="1.0" encoding="UTF-8"?>
<bns:Component xmlns:bns="http://api.platform.boomi.com/" name="New Process 3" type="process">
  <bns:description/>
  <bns:object><process><shapes>
    <shape name="shape1" shapetype="stop"><configuration><stop/></configuration><dragpoints/></shape>
    <shape name="shape2" shapetype="exception"><configuration><exception><exMessage/></exception></configuration><dragpoints/></shape>
    <shape name="shape3" shapetype="decision"><configuration><decision/></configuration>
      <dragpoints><dragpoint identifier="true" toShape="shape1"/><dragpoint identifier="false" toShape="unset"/></dragpoints></shape>
    <shape name="shape4" shapetype="dataprocess"><configuration><dataprocess><step><dataprocessscript language="groovy2"/></step></dataprocess></configuration><dragpoints/></shape>
  </shapes></process></bns:object>
</bns:Component>"""


def fill(xml):
    return re.sub(r"\{\{[A-Z_]+\}\}", "00000000-0000-0000-0000-000000000000", xml)


def test_every_rule_fires_on_a_bad_process():
    fired = {r["id"] for r in check_xml(BAD_PROCESS, load_rules())}
    assert fired == {r["id"] for r in load_rules()}


def test_bundled_samples_are_valid_xml_and_lint_clean():
    assert len(SAMPLES) == 4
    rules = [r for r in load_rules() if r["priority"] != "INFO"]
    for path in SAMPLES:
        with open(path, encoding="utf-8") as f:
            xml = fill(f.read())
        etree.fromstring(xml.encode("utf-8"))
        assert check_xml(xml, rules) == [], os.path.basename(path)


def test_samples_contain_no_account_specific_ids():
    guid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    for path in SAMPLES:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert not guid.search(text), os.path.basename(path)
        assert 'folderId="{{FOLDER_ID}}"' in text
