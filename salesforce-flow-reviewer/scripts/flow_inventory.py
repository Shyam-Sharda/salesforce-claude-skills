#!/usr/bin/env python3
"""
flow_inventory.py - structural map of a Salesforce Flow (*.flow-meta.xml).

Prints a review-oriented inventory of one or more Flow files:
  * flow type, status, run mode, start / trigger configuration
  * every element with its review-relevant settings
  * a rough execution outline built from the connectors
  * loop bodies, with database / action / subflow elements inside them flagged
  * fault-capable elements that have no fault connector
  * elements unreachable from the start, and cycles that are not Loop elements
  * possible hardcoded Salesforce record Ids
  * variables (input / output) and resources that appear unused

The script reports structure only. It does not decide severity: confirm
anything you report as a finding against the XML itself.

Usage:
  python flow_inventory.py MyFlow.flow-meta.xml [More.flow-meta.xml ...] [--json]
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict, deque

ELEMENT_TYPES = {
    "recordLookups": "Get Records",
    "recordCreates": "Create Records",
    "recordUpdates": "Update Records",
    "recordDeletes": "Delete Records",
    "recordRollbacks": "Roll Back Records",
    "assignments": "Assignment",
    "decisions": "Decision",
    "loops": "Loop",
    "collectionProcessors": "Collection Processor",
    "transforms": "Transform",
    "actionCalls": "Action",
    "apexPluginCalls": "Apex Plug-in",
    "subflows": "Subflow",
    "screens": "Screen",
    "waits": "Wait/Pause",
    "customErrors": "Custom Error",
    "orchestratedStages": "Orchestrated Stage",
    "steps": "Step",
}
RESOURCE_TYPES = {
    "variables": "Variable",
    "formulas": "Formula",
    "constants": "Constant",
    "textTemplates": "Text Template",
    "choices": "Choice",
    "dynamicChoiceSets": "Dynamic Choice Set",
    "stages": "Stage",
}
FAULT_CAPABLE = {
    "recordLookups", "recordCreates", "recordUpdates", "recordDeletes",
    "actionCalls", "apexPluginCalls", "subflows",
}
DATABASE = {"recordLookups", "recordCreates", "recordUpdates", "recordDeletes"}
EXPENSIVE = DATABASE | {"actionCalls", "apexPluginCalls", "subflows"}
CONNECTOR_TAGS = {
    "connector", "defaultConnector", "faultConnector",
    "nextValueConnector", "noMoreValuesConnector",
}
START = "__START__"

ID_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?)(?![A-Za-z0-9])")


# ---------------------------------------------------------------- helpers
def tag(el):
    return el.tag.split("}", 1)[-1]


def kids(el, name=None):
    return [c for c in el if name is None or tag(c) == name]


def kid(el, name):
    for c in el:
        if tag(c) == name:
            return c
    return None


def txt(el, name, default=None):
    c = kid(el, name)
    if c is None or c.text is None:
        return default
    return c.text.strip()


def render_value(v):
    """Render a <value> / <leftValueReference> style node compactly."""
    if v is None:
        return None
    for c in v:
        t = tag(c)
        val = (c.text or "").strip()
        if t == "elementReference":
            return "{!" + val + "}"
        if t == "stringValue":
            return repr(val)
        return val
    return (v.text or "").strip() or None


def render_filters(el, field_tag="filters"):
    out = []
    for f in kids(el, field_tag):
        field = txt(f, "field") or txt(f, "leftValueReference")
        op = txt(f, "operator")
        val = render_value(kid(f, "value") if kid(f, "value") is not None else kid(f, "rightValue"))
        out.append(f"{field} {op} {val}")
    return out


def render_conditions(rule):
    out = []
    for c in kids(rule, "conditions"):
        left = txt(c, "leftValueReference")
        op = txt(c, "operator")
        right = render_value(kid(c, "rightValue"))
        out.append(f"{left} {op} {right}")
    return out


def looks_like_sf_id(s):
    if len(s) not in (15, 18):
        return False
    if not s.isalnum():
        return False
    digits = sum(ch.isdigit() for ch in s)
    letters = sum(ch.isalpha() for ch in s)
    if digits < 4 or letters < 1:
        return False
    # Key prefixes: standard objects start with a digit (001, 005, 012, 00G...);
    # custom objects usually look like a0X, a1B...
    return s[0].isdigit() or (s[0].isalpha() and s[1].isdigit())


# ---------------------------------------------------------------- parsing
class Flow:
    def __init__(self, path):
        self.path = path
        self.root = ET.parse(path).getroot()
        self.elements = {}  # name -> (type, el)
        self.resources = {}  # name -> (type, el)
        self.edges = []  # (src, dst, kind, label)
        self.start = None
        self._parse()

    def _parse(self):
        r = self.root
        self.meta = {
            "label": txt(r, "label"),
            "description": txt(r, "description"),
            "processType": txt(r, "processType"),
            "status": txt(r, "status"),
            "apiVersion": txt(r, "apiVersion"),
            "runInMode": txt(r, "runInMode") or "(not set in metadata)",
        }
        for c in r:
            t = tag(c)
            if t in ELEMENT_TYPES:
                self.elements[txt(c, "name")] = (t, c)
                self._collect_edges(txt(c, "name"), c, None)
            elif t in RESOURCE_TYPES:
                self.resources[txt(c, "name")] = (t, c)
        self.start = kid(r, "start")
        if self.start is not None:
            self._collect_edges(START, self.start, None)
        ser = txt(r, "startElementReference")
        if ser:
            self.edges.append((START, ser, "connector", "start"))

    def _collect_edges(self, src, el, label):
        for c in el:
            t = tag(c)
            if t in CONNECTOR_TAGS:
                target = txt(c, "targetReference")
                if target:
                    is_goto = txt(c, "isGoTo") == "true"
                    kind = t + (" (GoTo)" if is_goto else "")
                    self.edges.append((src, target, kind, label))
            elif t in ("rules", "waitEvents", "scheduledPaths"):
                lbl = txt(c, "label") or txt(c, "name")
                if t == "scheduledPaths":
                    pt = txt(c, "pathType")
                    lbl = f"scheduled path: {lbl}" + (f" [{pt}]" if pt else "")
                self._collect_edges(src, c, lbl)

    # graph utilities
    def out_edges(self, n):
        return [e for e in self.edges if e[0] == n]

    def succ(self, n):
        return [e[1] for e in self.edges if e[0] == n]

    def pred(self, n):
        return [e[0] for e in self.edges if e[1] == n]

    def reachable(self, starts, blocked=()):
        seen, q = set(), deque(s for s in starts if s not in blocked)
        while q:
            n = q.popleft()
            if n in seen:
                continue
            seen.add(n)
            for m in self.succ(n):
                if m not in seen and m not in blocked:
                    q.append(m)
        return seen

    def reaches(self, target):
        seen, q = set(), deque([target])
        while q:
            n = q.popleft()
            for m in self.pred(n):
                if m not in seen and m != target:
                    seen.add(m)
                    q.append(m)
        return seen

    def etype(self, n):
        if n == START:
            return "start"
        return self.elements.get(n, ("?", None))[0]

    def elabel(self, n):
        if n == START:
            return "Start"
        el = self.elements.get(n, (None, None))[1]
        lab = txt(el, "label") if el is not None else None
        return f"{lab} [{n}]" if lab and lab != n else n

    # analyses
    def start_info(self):
        s = self.start
        info = {}
        if s is None:
            ser = txt(self.root, "startElementReference")
            if ser:
                info["startElementReference"] = ser
            return info
        for k in ("triggerType", "recordTriggerType", "object", "filterLogic",
                  "filterFormula", "doesRequireRecordChangedToMeetCriteria",
                  "flowRunAsUser"):
            v = txt(s, k)
            if v is not None:
                info[k] = v
        f = render_filters(s)
        if f:
            info["filters"] = f
        sched = kid(s, "schedule")
        if sched is not None:
            info["schedule"] = {tag(c): (c.text or "").strip() for c in sched}
        paths = []
        for p in kids(s, "scheduledPaths"):
            paths.append({tag(c): (c.text or "").strip() for c in p
                          if tag(c) != "connector"} | {
                "connector": txt(kid(p, "connector"), "targetReference")
                if kid(p, "connector") is not None else None})
        if paths:
            info["scheduledPaths"] = paths
        return info

    def element_details(self, name):
        t, el = self.elements[name]
        d = {"type": ELEMENT_TYPES[t], "xmlTag": t, "label": txt(el, "label")}
        desc = txt(el, "description")
        if desc:
            d["description"] = desc
        if t == "recordLookups":
            d.update({
                "object": txt(el, "object"),
                "getFirstRecordOnly": txt(el, "getFirstRecordOnly"),
                "filterLogic": txt(el, "filterLogic"),
                "filters": render_filters(el),
                "storeOutputAutomatically": txt(el, "storeOutputAutomatically"),
                "outputReference": txt(el, "outputReference"),
                "queriedFields": [c.text for c in kids(el, "queriedFields")],
                "sort": (txt(el, "sortField"), txt(el, "sortOrder")),
                "assignNullValuesIfNoRecordsFound": txt(el, "assignNullValuesIfNoRecordsFound"),
            })
        elif t in ("recordCreates", "recordUpdates", "recordDeletes"):
            d.update({
                "inputReference": txt(el, "inputReference"),
                "object": txt(el, "object"),
                "filterLogic": txt(el, "filterLogic"),
                "filters": render_filters(el),
                "fieldsSet": [f"{txt(a, 'field')} = {render_value(kid(a, 'value'))}"
                              for a in kids(el, "inputAssignments")],
            })
        elif t in ("actionCalls", "apexPluginCalls"):
            d.update({
                "actionType": txt(el, "actionType"),
                "actionName": txt(el, "actionName") or txt(el, "apexClass"),
                "flowTransactionModel": txt(el, "flowTransactionModel"),
                "inputs": [f"{txt(p, 'name')} = {render_value(kid(p, 'value'))}"
                           for p in kids(el, "inputParameters")],
                "outputs": [f"{txt(p, 'name')} -> {txt(p, 'assignToReference')}"
                            for p in kids(el, "outputParameters")],
                "storeOutputAutomatically": txt(el, "storeOutputAutomatically"),
            })
        elif t == "subflows":
            d.update({
                "flowName": txt(el, "flowName"),
                "inputs": [f"{txt(p, 'name')} = {render_value(kid(p, 'value'))}"
                           for p in kids(el, "inputAssignments")],
            })
        elif t == "loops":
            d.update({"collection": txt(el, "collectionReference"),
                      "iterationOrder": txt(el, "iterationOrder")})
        elif t == "decisions":
            d["outcomes"] = [{
                "name": txt(r, "name"), "label": txt(r, "label"),
                "logic": txt(r, "conditionLogic"),
                "conditions": render_conditions(r),
                "next": txt(kid(r, "connector"), "targetReference")
                if kid(r, "connector") is not None else None,
            } for r in kids(el, "rules")]
            d["defaultOutcome"] = {
                "label": txt(el, "defaultConnectorLabel"),
                "next": txt(kid(el, "defaultConnector"), "targetReference")
                if kid(el, "defaultConnector") is not None else None,
            }
        elif t == "assignments":
            d["items"] = [f"{txt(a, 'assignToReference')} {txt(a, 'operator')} "
                          f"{render_value(kid(a, 'value'))}"
                          for a in kids(el, "assignmentItems")]
        elif t == "screens":
            d.update({
                "allowBack": txt(el, "allowBack"), "allowFinish": txt(el, "allowFinish"),
                "allowPause": txt(el, "allowPause"),
                "fields": [{
                    "name": txt(f, "name"), "fieldType": txt(f, "fieldType"),
                    "dataType": txt(f, "dataType"),
                    "required": txt(f, "isRequired"),
                    "hasValidationRule": kid(f, "validationRule") is not None,
                } for f in kids(el, "fields")],
            })
        elif t == "collectionProcessors":
            d.update({"subtype": txt(el, "elementSubtype"),
                      "collection": txt(el, "collectionReference")})
        elif t == "customErrors":
            d["messages"] = [txt(m, "errorMessage") for m in kids(el, "customErrorMessages")]
        if t in FAULT_CAPABLE:
            d["hasFaultConnector"] = kid(el, "faultConnector") is not None
        return d

    def loops(self):
        res = {}
        for name, (t, el) in self.elements.items():
            if t != "loops":
                continue
            nv = kid(el, "nextValueConnector")
            first = txt(nv, "targetReference") if nv is not None else None
            if not first:
                res[name] = {"body": [], "leaves_loop": [], "expensive_in_body": []}
                continue
            fwd = self.reachable([first], blocked={name})
            back = self.reaches(name)
            body = sorted(fwd & back)
            leaves = sorted(fwd - back)
            res[name] = {
                "collection": txt(el, "collectionReference"),
                "body": body,
                "leaves_loop": leaves,
                "expensive_in_body": [n for n in body if self.etype(n) in EXPENSIVE],
                "expensive_on_exit_paths": [n for n in leaves if self.etype(n) in EXPENSIVE],
            }
        return res

    def non_loop_cycles(self):
        # Tarjan SCC, iterative
        nodes = [START] + list(self.elements)
        index, low, onstack, stack, sccs = {}, {}, set(), [], []
        counter = [0]
        adj = defaultdict(list)
        for s, d, *_ in self.edges:
            adj[s].append(d)
        for root in nodes:
            if root in index:
                continue
            work = [(root, iter(adj[root]))]
            index[root] = low[root] = counter[0]; counter[0] += 1
            stack.append(root); onstack.add(root)
            while work:
                v, it = work[-1]
                advanced = False
                for w in it:
                    if w not in index:
                        index[w] = low[w] = counter[0]; counter[0] += 1
                        stack.append(w); onstack.add(w)
                        work.append((w, iter(adj[w])))
                        advanced = True
                        break
                    elif w in onstack:
                        low[v] = min(low[v], index[w])
                if advanced:
                    continue
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop(); onstack.discard(w); comp.append(w)
                        if w == v:
                            break
                    if len(comp) > 1 or v in adj[v]:
                        sccs.append(comp)
        return [sorted(c) for c in sccs
                if not any(self.etype(n) == "loops" for n in c)]

    def missing_fault(self):
        return sorted(n for n, (t, el) in self.elements.items()
                      if t in FAULT_CAPABLE and kid(el, "faultConnector") is None)

    def fault_paths(self):
        out = []
        for s, d, kind, _ in self.edges:
            if kind.startswith("faultConnector"):
                out.append((s, d, self.etype(d)))
        return out

    def unreachable(self):
        reach = self.reachable([START])
        return sorted(n for n in self.elements if n not in reach)

    def dangling(self):
        known = set(self.elements) | {START}
        return sorted({(s, d) for s, d, *_ in self.edges if d not in known})

    def possible_ids(self):
        hits = []

        def walk(el, owner):
            t = tag(el)
            if t in ELEMENT_TYPES or t in RESOURCE_TYPES:
                owner = txt(el, "name") or owner
            if t == "start":
                owner = "Start"
            if el.text and t not in ("name", "label", "description", "locationX",
                                     "locationY", "targetReference", "interviewLabel"):
                for m in ID_RE.finditer(el.text):
                    if looks_like_sf_id(m.group(1)):
                        hits.append((owner, t, m.group(1)))
            for c in el:
                walk(c, owner)

        walk(self.root, None)
        return hits

    def record_self_updates(self):
        return sorted(n for n, (t, el) in self.elements.items()
                      if t == "recordUpdates" and txt(el, "inputReference") == "$Record")

    def variables(self):
        out = []
        for n, (t, el) in self.resources.items():
            if t != "variables":
                continue
            out.append({
                "name": n, "dataType": txt(el, "dataType"),
                "objectType": txt(el, "objectType"),
                "isCollection": txt(el, "isCollection"),
                "isInput": txt(el, "isInput"), "isOutput": txt(el, "isOutput"),
            })
        return out

    def unused_resources(self):
        texts = []

        def walk(el):
            t = tag(el)
            if el.text and t not in ("name", "label", "description"):
                texts.append(el.text)
            for c in el:
                walk(c)

        walk(self.root)
        blob = "\n".join(texts)
        unused = []
        for n, (t, _) in self.resources.items():
            if not n:
                continue
            if not re.search(r"(?<![\w$])" + re.escape(n) + r"(?![\w])", blob):
                unused.append(f"{n} ({RESOURCE_TYPES[t]})")
        return sorted(unused)

    def outline(self, max_lines=400):
        lines, seen = [], set()

        def fmt(n):
            t = self.etype(n)
            extra = ""
            if n in self.elements:
                el = self.elements[n][1]
                if t in ("actionCalls", "apexPluginCalls"):
                    extra = f" ({txt(el, 'actionType')}: {txt(el, 'actionName') or txt(el, 'apexClass')})"
                    ftm = txt(el, "flowTransactionModel")
                    if ftm:
                        extra += f" [transaction: {ftm}]"
                elif t == "subflows":
                    extra = f" (subflow: {txt(el, 'flowName')})"
                elif t in DATABASE:
                    obj = txt(el, "object") or txt(el, "inputReference")
                    extra = f" ({obj})" if obj else ""
                elif t == "loops":
                    extra = f" (over {txt(el, 'collectionReference')})"
            return f"{self.elabel(n)} <{ELEMENT_TYPES.get(t, t)}>{extra}"

        def visit(n, depth):
            if len(lines) >= max_lines:
                return
            ind = "  " * depth
            if n in seen:
                lines.append(f"{ind}↺ (continues at {self.elabel(n)})")
                return
            seen.add(n)
            if n not in self.elements and n != START:
                lines.append(f"{ind}?? missing element {n}")
                return
            lines.append(ind + fmt(n))
            outs = self.out_edges(n)
            normal = [e for e in outs if e[2] in ("connector",) and e[3] is None]
            branches = [e for e in outs if e not in normal]
            # order: branches (rules, default, loop body, fault, scheduled) then normal
            order = {"nextValueConnector": 0, "connector": 1, "defaultConnector": 2,
                     "faultConnector": 3, "noMoreValuesConnector": 4}
            branches.sort(key=lambda e: order.get(e[2].split(" ")[0], 9))
            for s, d, kind, label in branches:
                k = kind.split(" ")[0]
                name = {
                    "nextValueConnector": "for each item",
                    "noMoreValuesConnector": "after last item",
                    "faultConnector": "FAULT",
                    "defaultConnector": "default",
                }.get(k, label or kind)
                if k == "connector" and label:
                    name = label
                if k == "defaultConnector":
                    dl = txt(self.elements[n][1], "defaultConnectorLabel") if n in self.elements else None
                    name = f"default: {dl}" if dl else "default"
                if "GoTo" in kind:
                    name += " (GoTo)"
                lines.append(f"{ind}  ├─[{name}]")
                visit(d, depth + 2)
            if self.etype(n) == "decisions":
                el = self.elements[n][1]
                if kid(el, "defaultConnector") is None:
                    dl = txt(el, "defaultConnectorLabel")
                    lines.append(f"{ind}  ├─[default{': ' + dl if dl else ''}] → (end)")
                for r in kids(el, "rules"):
                    if kid(r, "connector") is None:
                        lines.append(f"{ind}  ├─[{txt(r, 'label') or txt(r, 'name')}] → (end)")
            for s, d, kind, label in normal:
                visit(d, depth)

        visit(START, 0)
        if len(lines) >= max_lines:
            lines.append("... (outline truncated)")
        return lines


# ---------------------------------------------------------------- report
def report(flow):
    p = []
    m = flow.meta
    p.append(f"# Flow inventory: {flow.path}")
    for k, v in m.items():
        if v:
            p.append(f"- {k}: {v}")
    si = flow.start_info()
    p.append("\n## Start / trigger")
    if not si:
        p.append("- (no <start> element details; screen or autolaunched flow)")
    for k, v in si.items():
        if isinstance(v, list):
            p.append(f"- {k}:")
            for i in v:
                p.append(f"    - {i}")
        else:
            p.append(f"- {k}: {v}")

    counts = defaultdict(int)
    for t, _ in flow.elements.values():
        counts[ELEMENT_TYPES[t]] += 1
    p.append("\n## Element counts")
    p.append(", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "(none)")

    p.append("\n## Execution outline (from connectors; ↺ = joins a path shown above)")
    p.append("```")
    p.extend(flow.outline())
    p.append("```")

    p.append("\n## Loops")
    loops = flow.loops()
    if not loops:
        p.append("- none")
    for n, info in loops.items():
        p.append(f"- {n} over {info.get('collection')}")
        p.append(f"    - body: {', '.join(info['body']) or '(empty)'}")
        if info["expensive_in_body"]:
            p.append("    - DATABASE/ACTION/SUBFLOW ELEMENTS IN BODY (run once per iteration): "
                     + ", ".join(f"{x} <{ELEMENT_TYPES[flow.etype(x)]}>"
                                 for x in info["expensive_in_body"]))
        if info.get("leaves_loop"):
            p.append(f"    - reachable from body but not returning to loop: "
                     f"{', '.join(info['leaves_loop'])}")
        if info.get("expensive_on_exit_paths"):
            p.append("    - database/action elements on those exit paths: "
                     + ", ".join(info["expensive_on_exit_paths"]))

    cyc = flow.non_loop_cycles()
    if cyc:
        p.append("\n## Cycles not driven by a Loop element (check for termination)")
        for c in cyc:
            p.append(f"- {' -> '.join(c)}")

    p.append("\n## Fault handling")
    mf = flow.missing_fault()
    p.append(f"- fault-capable elements WITHOUT fault connector: {', '.join(mf) or 'none'}")
    fps = flow.fault_paths()
    if fps:
        p.append("- fault connectors:")
        for s, d, t in fps:
            p.append(f"    - {s} → {d} <{ELEMENT_TYPES.get(t, t)}>")

    su = flow.record_self_updates()
    if su:
        p.append("\n## Update Records on $Record")
        p.append(f"- {', '.join(su)}  (trigger type: {si.get('triggerType', 'n/a')})")

    ur = flow.unreachable()
    dg = flow.dangling()
    if ur or dg:
        p.append("\n## Structural problems")
        if ur:
            p.append(f"- elements not reachable from Start: {', '.join(ur)}")
        for s, d in dg:
            p.append(f"- connector from {s} points to missing element {d}")

    ids = flow.possible_ids()
    p.append("\n## Possible hardcoded record Ids (heuristic; confirm in XML)")
    if not ids:
        p.append("- none found")
    for owner, t, v in ids:
        p.append(f"- {v} in {owner} (<{t}>)")

    p.append("\n## Variables")
    vs = flow.variables()
    if not vs:
        p.append("- none")
    for v in vs:
        flags = [f for f in ("isInput", "isOutput", "isCollection") if v[f] == "true"]
        typ = v["dataType"] + (f"<{v['objectType']}>" if v["objectType"] else "")
        p.append(f"- {v['name']}: {typ} {' '.join(flags)}".rstrip())
    un = flow.unused_resources()
    if un:
        p.append(f"- resources with no references found: {', '.join(un)}")

    p.append("\n## Element details")
    for n in flow.elements:
        d = flow.element_details(n)
        p.append(f"\n### {n} <{d.pop('type')}>")
        d.pop("xmlTag", None)
        for k, v in d.items():
            if v in (None, [], "", (None, None)):
                continue
            if isinstance(v, list):
                p.append(f"- {k}:")
                for i in v:
                    p.append(f"    - {i}")
            elif isinstance(v, dict):
                p.append(f"- {k}: {v}")
            else:
                p.append(f"- {k}: {v}")
    return "\n".join(p)


def as_json(flow):
    return {
        "path": flow.path,
        "meta": flow.meta,
        "start": flow.start_info(),
        "elements": {n: flow.element_details(n) for n in flow.elements},
        "edges": [{"from": s, "to": d, "kind": k, "label": l} for s, d, k, l in flow.edges],
        "loops": flow.loops(),
        "nonLoopCycles": flow.non_loop_cycles(),
        "missingFaultConnector": flow.missing_fault(),
        "recordSelfUpdates": flow.record_self_updates(),
        "unreachable": flow.unreachable(),
        "danglingConnectors": flow.dangling(),
        "possibleHardcodedIds": flow.possible_ids(),
        "variables": flow.variables(),
        "unusedResources": flow.unused_resources(),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    a = ap.parse_args()
    results, rc = [], 0
    for f in a.files:
        try:
            flow = Flow(f)
        except ET.ParseError as e:
            print(f"# {f}: XML parse error: {e}", file=sys.stderr)
            rc = 1
            continue
        if tag(flow.root) != "Flow":
            print(f"# {f}: root element is <{tag(flow.root)}>, not <Flow>", file=sys.stderr)
            rc = 1
            continue
        results.append(flow)
    if a.json:
        print(json.dumps([as_json(f) for f in results], indent=2, default=str))
    else:
        print("\n\n".join(report(f) for f in results))
    sys.exit(rc)


if __name__ == "__main__":
    main()
