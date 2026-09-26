"""Turn pytest JUnit failures into GitHub annotations, so they can be read through the REST API
(check-run annotations) when job logs are not reachable."""

import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
count = 0
for case in root.iter("testcase"):
    for problem in list(case.findall("failure")) + list(case.findall("error")):
        name = f"{case.get('classname')}.{case.get('name')}"
        text = (problem.get("message") or "") + "\n" + (problem.text or "")
        text = text.strip().replace("%", "%25").replace("\r", "").replace("\n", "%0A")[:3500]
        print(f"::error title={name}::{text}")
        count += 1
        if count >= 20:
            sys.exit(0)
