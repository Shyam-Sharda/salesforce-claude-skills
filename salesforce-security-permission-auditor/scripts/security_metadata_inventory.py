#!/usr/bin/env python3
"""Deterministic inventory of Salesforce security metadata.

Parses Permission Set, Profile, Permission Set Group and Muting Permission Set
XML (source or mdapi format) and prints facts:

  inventory  per-file grants, with explicit false kept distinct from absent
  compare    side-by-side matrix of two or more permission sources
  group      resolve a Permission Set Group: members, muting, resulting grants

This helper only extracts and compares what is in the supplied files. It does
not assign severity, decide what anyone should have, infer record-level
sharing, assume user assignments, recommend changes, or modify any file.

Standard library only. Python 3.8+.
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

# Symbols used in tables
YES = "Y"        # explicitly true
NO = "n"         # explicitly false (not granted by this source; not a deny)
ABSENT = "-"     # no entry in the file

OBJECT_FLAGS = [
    ("allowRead", "Read"),
    ("allowCreate", "Create"),
    ("allowEdit", "Edit"),
    ("allowDelete", "Delete"),
    ("viewAllRecords", "ViewAll"),
    ("modifyAllRecords", "ModifyAll"),
]
FIELD_FLAGS = [("readable", "Read"), ("editable", "Edit")]

# block tag -> (category, name tag, [(xml flag, label)])
SIMPLE_BLOCKS = {
    "classAccesses": ("class", "apexClass", [("enabled", "Access")]),
    "flowAccesses": ("flow", "flow", [("enabled", "Access")]),
    "pageAccesses": ("page", "apexPage", [("enabled", "Access")]),
    "customPermissions": ("customPermission", "name", [("enabled", "Enabled")]),
    "userPermissions": ("userPermission", "name", [("enabled", "Enabled")]),
    "recordTypeVisibilities": ("recordType", "recordType",
                               [("visible", "Visible"), ("default", "Default")]),
    "applicationVisibilities": ("app", "application",
                                [("visible", "Visible"), ("default", "Default")]),
    "customMetadataTypeAccesses": ("customMetadataType", "name", [("enabled", "Access")]),
    "customSettingAccesses": ("customSetting", "name", [("enabled", "Access")]),
}

CATEGORY_ORDER = ["object", "field", "class", "flow", "page", "customPermission",
                  "userPermission", "recordType", "tab", "app",
                  "customMetadataType", "customSetting"]

# Documented Salesforce prerequisites: muting the key makes the listed
# permissions not effective through the group. These are the only
# dependencies the helper models.
OBJECT_DEPENDENTS = {
    "Read": ["Create", "Edit", "Delete", "ViewAll", "ModifyAll"],
    "Edit": ["Delete", "ModifyAll"],
    "Delete": ["ModifyAll"],
    "ViewAll": ["ModifyAll"],
}
FIELD_DEPENDENTS = {"Read": ["Edit"]}
MODELED_DEPENDENCY_LIMITATION = (
    "only object CRUD / View All / Modify All and field Read/Edit prerequisites are "
    "modeled. Other Salesforce permission dependencies (for example between user "
    "permissions, Custom Permission required permissions, or license requirements) "
    "are not resolved by this helper.")

KIND_BY_ROOT = {
    "PermissionSet": "PermissionSet",
    "Profile": "Profile",
    "PermissionSetGroup": "PermissionSetGroup",
    "MutingPermissionSet": "MutingPermissionSet",
}


def local(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(elem, name):
    for c in elem:
        if local(c.tag) == name:
            return (c.text or "").strip()
    return None


def to_value(text):
    if text is None:
        return None
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    return text


def api_name_from_path(path):
    base = os.path.basename(path)
    return base.split(".", 1)[0]


def parse_file(path):
    """Return a dict describing one security metadata file."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise SystemExit("Cannot parse XML in %s: %s" % (path, exc))
    root_name = local(root.tag)
    kind = KIND_BY_ROOT.get(root_name)
    if kind is None:
        raise SystemExit("%s: unsupported root element <%s>" % (path, root_name))

    info = {
        "file": path,
        "name": api_name_from_path(path),
        "kind": kind,
        "label": child_text(root, "label"),
        "license": child_text(root, "license") or child_text(root, "userLicense"),
        "entries": [],  # dicts: category, target, flag, value
        "members": [],
        "muting": [],
        "status": None,
    }

    if kind == "PermissionSetGroup":
        for c in root:
            tag = local(c.tag)
            if tag == "permissionSets":
                info["members"].append((c.text or "").strip())
            elif tag == "mutingPermissionSets":
                info["muting"].append((c.text or "").strip())
        info["status"] = child_text(root, "status")
        return info

    entries = info["entries"]
    for block in root:
        tag = local(block.tag)
        if tag == "objectPermissions":
            target = child_text(block, "object")
            for xml_flag, label in OBJECT_FLAGS:
                v = to_value(child_text(block, xml_flag))
                if v is not None:
                    entries.append({"category": "object", "target": target,
                                    "flag": label, "value": v})
        elif tag == "fieldPermissions":
            target = child_text(block, "field")
            for xml_flag, label in FIELD_FLAGS:
                v = to_value(child_text(block, xml_flag))
                if v is not None:
                    entries.append({"category": "field", "target": target,
                                    "flag": label, "value": v})
        elif tag in ("tabSettings", "tabVisibilities"):
            target = child_text(block, "tab")
            v = child_text(block, "visibility")
            if v is not None:
                entries.append({"category": "tab", "target": target,
                                "flag": "Visibility", "value": v})
        elif tag in SIMPLE_BLOCKS:
            category, name_tag, flags = SIMPLE_BLOCKS[tag]
            target = child_text(block, name_tag)
            for xml_flag, label in flags:
                v = to_value(child_text(block, xml_flag))
                if v is not None:
                    entries.append({"category": category, "target": target,
                                    "flag": label, "value": v})
    return info


def matches(entry, flt):
    if not flt:
        return True
    needles = [f.lower() for f in flt]
    hay = ("%s %s %s" % (entry["category"], entry["target"], entry["flag"])).lower()
    return any(n in hay for n in needles)


def key(entry):
    return (entry["category"], entry["target"] or "", entry["flag"])


def sort_key(k):
    cat, target, flag = k
    ci = CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else len(CATEGORY_ORDER)
    return (ci, target.lower(), flag)


def fmt(v):
    if v is True:
        return YES
    if v is False:
        return NO
    if v is None:
        return ABSENT
    return str(v)


def is_grant(v):
    """True when the value grants something. Tab visibility None/Hidden is not a grant."""
    if v is True:
        return True
    if isinstance(v, str):
        return v not in ("None", "Hidden")
    return False


# ---------------------------------------------------------------- rendering

def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_entries(entries):
    """Render one file's entries grouped by category."""
    by_cat = {}
    for e in entries:
        by_cat.setdefault(e["category"], {}).setdefault(e["target"], {})[e["flag"]] = e["value"]
    parts = []
    for cat in sorted(by_cat, key=lambda c: CATEGORY_ORDER.index(c)
                      if c in CATEGORY_ORDER else 99):
        targets = by_cat[cat]
        if cat == "object":
            labels = [l for _, l in OBJECT_FLAGS]
        elif cat == "field":
            labels = [l for _, l in FIELD_FLAGS]
        else:
            labels = sorted({f for t in targets.values() for f in t})
        rows = [[t] + [fmt(targets[t].get(l)) for l in labels]
                for t in sorted(targets, key=lambda s: (s or "").lower())]
        parts.append("**%s**\n\n%s" % (cat, md_table([cat] + labels, rows)))
    return "\n\n".join(parts) if parts else "_No matching entries._"


def legend():
    return ("Legend: `%s` explicitly true, `%s` explicitly false (not granted by this "
            "source; not a deny), `%s` no entry in the file (may be a partial retrieve)."
            % (YES, NO, ABSENT))


def header_line(info):
    bits = ["%s `%s`" % (info["kind"], info["name"])]
    if info["label"]:
        bits.append("label: %s" % info["label"])
    if info["license"]:
        bits.append("license: %s" % info["license"])
    return " | ".join(bits)


# ---------------------------------------------------------------- commands

def cmd_inventory(args):
    results = []
    for path in args.files:
        info = parse_file(path)
        info["entries"] = [e for e in info["entries"] if matches(e, args.filter)]
        results.append(info)
    if args.json:
        print(json.dumps(results, indent=2))
        return
    print(legend())
    for info in results:
        print("\n## %s\n" % header_line(info))
        print("File: %s\n" % info["file"])
        if info["kind"] == "PermissionSetGroup":
            print("Member Permission Sets: %s" % (", ".join(info["members"]) or "none listed"))
            print("Muting Permission Sets: %s" % (", ".join(info["muting"]) or "none listed"))
            if info["status"]:
                print("Status: %s" % info["status"])
            continue
        if info["kind"] == "MutingPermissionSet":
            print("_In a Muting Permission Set, `Y` means the permission is MUTED "
                  "within groups that reference this set._\n")
        print(render_entries(info["entries"]))


def cmd_compare(args):
    infos = [parse_file(p) for p in args.files]
    for i in infos:
        if i["kind"] == "PermissionSetGroup":
            raise SystemExit("compare works on permission sources; resolve groups with "
                             "the 'group' command first (%s)" % i["file"])
    names = []
    for i in infos:
        n = i["name"]
        if n in names:
            n = "%s (%s)" % (n, i["file"])
        names.append(n)
    table = {}
    for idx, info in enumerate(infos):
        for e in info["entries"]:
            if matches(e, args.filter):
                table.setdefault(key(e), [None] * len(infos))[idx] = e["value"]
    rows = []
    for k in sorted(table, key=sort_key):
        vals = table[k]
        if args.only_diff and len({is_grant(v) for v in vals}) == 1 \
                and len({v for v in vals if isinstance(v, str)}) <= 1:
            continue
        rows.append((k, vals))

    if args.json:
        print(json.dumps({
            "sources": [{"name": n, "kind": i["kind"], "file": i["file"]}
                        for n, i in zip(names, infos)],
            "rows": [{"category": k[0], "target": k[1], "flag": k[2],
                      "values": dict(zip(names, v))} for k, v in rows],
        }, indent=2))
        return
    print(legend())
    if any(i["kind"] == "MutingPermissionSet" for i in infos):
        print("\nNote: for Muting Permission Set columns, `Y` means MUTED, not granted.")
    if args.only_diff:
        print("\nShowing only rows where grant status differs between sources.")
    print()
    if not rows:
        print("_No matching rows._")
        return
    print(md_table(["category", "target", "flag"] + names,
                   [[k[0], k[1], k[2]] + [fmt(v) for v in vals] for k, vals in rows]))


def find_metadata(search_dirs, api_name, suffixes):
    targets = {api_name + s for s in suffixes}
    hits = []
    for d in search_dirs:
        for dirpath, _, files in os.walk(d):
            for f in files:
                if f in targets:
                    hits.append(os.path.join(dirpath, f))
    return sorted(set(hits))


def cmd_group(args):
    group = parse_file(args.group_file)
    if group["kind"] != "PermissionSetGroup":
        raise SystemExit("%s is a %s, not a PermissionSetGroup" % (args.group_file, group["kind"]))
    search_dirs = args.search_dir or [os.path.dirname(os.path.abspath(args.group_file))]

    members, missing, ambiguous = [], [], []
    for name in group["members"]:
        hits = find_metadata(search_dirs, name,
                             [".permissionset-meta.xml", ".permissionset"])
        if not hits:
            missing.append(name)
        elif len(hits) > 1:
            ambiguous.append((name, hits))
            members.append(parse_file(hits[0]))
        else:
            members.append(parse_file(hits[0]))

    mutings, missing_muting = [], []
    for name in group["muting"]:
        hits = find_metadata(search_dirs, name,
                             [".mutingpermissionset-meta.xml", ".mutingpermissionset"])
        if hits:
            mutings.append(parse_file(hits[0]))
        else:
            missing_muting.append(name)

    complete = not missing and not missing_muting and not ambiguous

    granted = {}   # key -> [source names]
    tab_values = {}
    for m in members:
        for e in m["entries"]:
            if not matches(e, args.filter):
                continue
            if e["category"] == "tab":
                if is_grant(e["value"]):
                    tab_values.setdefault(key(e), []).append("%s=%s" % (m["name"], e["value"]))
            elif e["value"] is True:
                granted.setdefault(key(e), []).append(m["name"])

    # Explicitly muted permissions
    muted = set()
    for mu in mutings:
        for e in mu["entries"]:
            if e["value"] is True:
                muted.add(key(e))

    # Expand the muted set through the modeled prerequisite dependencies.
    # dep_muted maps a key to the explicitly muted prerequisite flags causing it.
    dep_muted = {}
    for root in sorted(muted, key=sort_key):
        cat, target, root_flag = root
        deps_map = (OBJECT_DEPENDENTS if cat == "object" else
                    FIELD_DEPENDENTS if cat == "field" else {})
        stack, seen = [root_flag], {root_flag}
        while stack:
            for d in deps_map.get(stack.pop(), []):
                if d in seen:
                    continue
                seen.add(d)
                stack.append(d)
                k2 = (cat, target, d)
                if k2 not in muted:
                    causes = dep_muted.setdefault(k2, [])
                    if root_flag not in causes:
                        causes.append(root_flag)

    def status_of(k):
        if k in muted:
            return "MUTED"
        if k in dep_muted:
            return "MUTED (dependency: %s)" % ", ".join(dep_muted[k])
        return "granted"

    dependency_notes = []
    for k in sorted(set(granted) & set(dep_muted), key=sort_key):
        cat, target, flag = k
        dependency_notes.append(
            "%s `%s` %s is muted. %s `%s` %s is therefore not effective through this "
            "Permission Set Group." % (cat, target, " / ".join(dep_muted[k]),
                                       cat, target, flag))

    result_rows = []
    for k in sorted(granted, key=sort_key):
        result_rows.append((k, ", ".join(granted[k]), status_of(k)))
    muted_not_granted = sorted((k for k in muted if k not in granted and matches(
        {"category": k[0], "target": k[1], "flag": k[2]}, args.filter)), key=sort_key)

    if args.json:
        print(json.dumps({
            "group": group["name"], "file": group["file"], "status": group["status"],
            "complete": complete,
            "members_found": [m["file"] for m in members],
            "members_missing": missing,
            "members_ambiguous": {n: h for n, h in ambiguous},
            "muting_found": [m["file"] for m in mutings],
            "muting_missing": missing_muting,
            "rows": [{"category": k[0], "target": k[1], "flag": k[2],
                      "granted_by": src, "status": st} for k, src, st in result_rows],
            "tabs": [{"tab": k[1], "values": v} for k, v in sorted(tab_values.items())],
            "muted_but_not_granted_by_members": [list(k) for k in muted_not_granted],
            "dependency_notes": dependency_notes,
            "limitation": MODELED_DEPENDENCY_LIMITATION,
        }, indent=2))
        return

    print("## Permission Set Group `%s`\n" % group["name"])
    if group["label"]:
        print("Label: %s" % group["label"])
    if group["status"]:
        print("Status: %s" % group["status"])
    print("Members listed: %s" % (", ".join(group["members"]) or "none"))
    print("Muting listed: %s" % (", ".join(group["muting"]) or "none"))
    print("Members found: %s" % (", ".join(m["name"] for m in members) or "none"))
    if missing:
        print("Members MISSING (file not supplied): %s" % ", ".join(missing))
    for n, hits in ambiguous:
        print("Member `%s` AMBIGUOUS, multiple files: %s (used first)" % (n, ", ".join(hits)))
    if missing_muting:
        print("Muting set MISSING (file not supplied): %s" % ", ".join(missing_muting))
    print()
    if complete:
        print("All member and muting files were found. Rows below are the resulting grants "
              "from this Permission Set Group after supplied muting and modeled permission "
              "dependencies. This is not a user's effective access: it is not proof that "
              "any user is assigned the group, and it excludes grants from other sources "
              "(Profile, directly assigned Permission Sets, other groups, licenses).\n")
    else:
        print("INCOMPLETE: rows below come from the supplied files only and are NOT the "
              "resolved result for this group. Supply the missing files to resolve it.\n")
    if result_rows:
        print(md_table(["category", "target", "flag", "granted by", "result"],
                       [[k[0], k[1], k[2], src, st] for k, src, st in result_rows]))
    else:
        print("_No matching grants from supplied members._")
    if tab_values:
        print("\nTab settings from members (not muted by this helper):")
        for k, v in sorted(tab_values.items()):
            print("- %s: %s" % (k[1], "; ".join(v)))
    if muted_not_granted:
        print("\nMuted in the muting set but not granted by any supplied member "
              "(no effect within this group):")
        for k in muted_not_granted:
            print("- %s `%s` %s" % k)
    if dependency_notes:
        print("\nDependency effects:")
        for n in dependency_notes:
            print("- " + n)
    print("\nLimitation: " + MODELED_DEPENDENCY_LIMITATION)


def build_parser():
    p = argparse.ArgumentParser(
        description="Inventory and compare Salesforce security metadata (facts only).")
    sub = p.add_subparsers(dest="command")
    sub.required = True

    inv = sub.add_parser("inventory", help="per-file permission inventory")
    inv.add_argument("files", nargs="+")
    inv.set_defaults(func=cmd_inventory)

    cmp_ = sub.add_parser("compare", help="compare two or more permission sources")
    cmp_.add_argument("files", nargs="+")
    cmp_.add_argument("--only-diff", action="store_true",
                      help="show only rows where grant status differs")
    cmp_.set_defaults(func=cmd_compare)

    grp = sub.add_parser("group", help="resolve a Permission Set Group with muting")
    grp.add_argument("group_file")
    grp.add_argument("--search-dir", action="append",
                     help="directory to search for member and muting files (repeatable); "
                          "defaults to the group file's directory")
    grp.set_defaults(func=cmd_group)

    for s in (inv, cmp_, grp):
        s.add_argument("--filter", action="append",
                       help="case-insensitive substring on category/target/flag (repeatable)")
        s.add_argument("--json", action="store_true", help="JSON output")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "command") == "compare" and len(args.files) < 2:
        raise SystemExit("compare needs at least two files")
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
