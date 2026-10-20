#!/usr/bin/env python3
"""
Deterministic inventory of one or more Salesforce debug logs.

Purpose: count and group events that are easy to miscount by eye in long logs
(repeated SOQL/DML signatures, code-unit nesting, Flow elements, exceptions,
limit blocks, truncation markers) and print them with log line numbers so the
analyst can go back to the raw log.

It deliberately does NOT assign severity, decide root cause, recommend fixes or
infer relationships that are not written in the log. Unknown event types are
counted and otherwise ignored. The input files are never modified. Values that
look like credentials are redacted in everything printed.

Usage:
  debug_log_inventory.py LOG [LOG ...]                  inventory
  debug_log_inventory.py LOG --timeline                 + compressed timeline
  debug_log_inventory.py LOG --timeline --methods       + METHOD_ENTRY in timeline
  debug_log_inventory.py LOG --timeline --from-line 5000 --to-line 9000
  debug_log_inventory.py -                              read from stdin

Standard library only.
"""

import argparse
import re
import sys
from collections import Counter, defaultdict

# 14:32:08.315 (315123456)|EVENT_TYPE|field|field...
EVENT_RE = re.compile(r"^(\d{1,2}:\d{2}:\d{2}\.\d+)\s+\((\d+)\)\|([A-Z0-9_]+)(?:\|(.*))?$")
HEADER_RE = re.compile(r"^(\d+\.\d+)\s+([A-Za-z_]+,[A-Za-z]+(?:;[A-Za-z_]+,[A-Za-z]+)*);?\s*$")
LIMIT_LINE_RE = re.compile(r"^\s*(.+?):\s*(\d+)\s+out of\s+(\d+)\s*(.*)$")
TRUNC_RE = re.compile(r"\*\*\*\s*Skipped\s+\d+\s+bytes of detailed log|MAXIMUM DEBUG LOG SIZE REACHED", re.I)
SRC_RE = re.compile(r"^\[(\d+|EXTERNAL)\]$")
SFID_RE = re.compile(r"\b(?=[a-zA-Z0-9]*\d)[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?\b")
ASYNC_JOB_ID_RE = re.compile(r"\b707[a-zA-Z0-9]{12}(?:[a-zA-Z0-9]{3})?\b")
ERRORISH_RE = re.compile(r"ERROR|FAULT|FAIL|EXCEPTION")

REDACTIONS = [
    (re.compile(r"\b00D[a-zA-Z0-9]{12,15}![A-Za-z0-9._]+"), "[REDACTED SESSION ID]"),
    (re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(?!\[REDACTED)[^\s,\"'\]]+(\s+[^\s,\"'\]]+)?"),
     r"\1[REDACTED AUTHORIZATION HEADER]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b(session_?id|sid|access_token|refresh_token|id_token|client_secret|api[_-]?key|x-api-key|"
                r"password|passwd|pwd|secret|token|signature|sig|cookie|set-cookie)([\"']?\s*[:=]\s*[\"']?)"
                r"(?!\[REDACTED)[^\s&,;\"'\]]+"),
     r"\1\2[REDACTED]"),
]

TIMELINE_TYPES = {
    "EXECUTION_STARTED", "EXECUTION_FINISHED", "CODE_UNIT_STARTED", "CODE_UNIT_FINISHED",
    "SOQL_EXECUTE_BEGIN", "SOSL_EXECUTE_BEGIN", "DML_BEGIN", "EXCEPTION_THROWN", "FATAL_ERROR",
    "FLOW_CREATE_INTERVIEW_BEGIN", "FLOW_START_INTERVIEW_BEGIN", "FLOW_ELEMENT_BEGIN",
    "CALLOUT_REQUEST", "CALLOUT_RESPONSE", "USER_DEBUG", "VALIDATION_RULE",
    "LIMIT_USAGE_FOR_NS",
}


def redact(text):
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def clip(text, n=220):
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 3] + "..."


def src_of(fields):
    if fields and SRC_RE.match(fields[0]):
        return fields[0]
    return ""


class Event:
    __slots__ = ("line", "ts", "ns", "type", "fields", "extra", "depth", "unit", "method")

    def __init__(self, line, ts, ns, etype, fields):
        self.line, self.ts, self.ns, self.type, self.fields = line, ts, ns, etype, fields
        self.extra = []
        self.depth = 0
        self.unit = ""
        self.method = ""


def parse(text):
    events, header, preamble_unparsed, truncation = [], None, 0, []
    current = None
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r")
        if TRUNC_RE.search(line):
            truncation.append((i, clip(line.strip(), 120)))
        m = EVENT_RE.match(line)
        if m:
            ts, ns, etype, rest = m.groups()
            fields = rest.split("|") if rest is not None else []
            current = Event(i, ts, int(ns), etype, fields)
            events.append(current)
            continue
        if header is None and not events:
            hm = HEADER_RE.match(line.strip())
            if hm:
                header = (i, hm.group(1), hm.group(2))
                continue
        if current is not None:
            current.extra.append((i, line))
        elif line.strip():
            preamble_unparsed += 1
    return events, header, preamble_unparsed, truncation


def annotate(events):
    """Attach code-unit depth, enclosing unit and enclosing method to each event."""
    unit_stack, method_stack, unit_method_base = [], [], []
    unclosed_problems = []
    for ev in events:
        try:
            if ev.type == "CODE_UNIT_STARTED":
                name = ev.fields[-1] if ev.fields else "?"
                ev.depth = len(unit_stack)
                unit_stack.append((name, ev.line))
                unit_method_base.append(len(method_stack))
                ev.unit = name
                continue
            if ev.type == "CODE_UNIT_FINISHED":
                name = ev.fields[-1] if ev.fields else "?"
                if unit_stack:
                    # pop to the matching name if present, else pop one
                    idx = next((k for k in range(len(unit_stack) - 1, -1, -1) if unit_stack[k][0] == name), None)
                    if idx is None:
                        unclosed_problems.append((ev.line, "CODE_UNIT_FINISHED without matching start: " + clip(name, 100)))
                        idx = len(unit_stack) - 1
                    for _ in range(len(unit_stack) - idx):
                        unit_stack.pop()
                        base = unit_method_base.pop()
                        del method_stack[base:]
                else:
                    unclosed_problems.append((ev.line, "CODE_UNIT_FINISHED with no open unit: " + clip(name, 100)))
                ev.depth = len(unit_stack)
                ev.unit = name
                continue
            if ev.type in ("METHOD_ENTRY", "CONSTRUCTOR_ENTRY"):
                method_stack.append(ev.fields[-1] if ev.fields else "?")
            elif ev.type in ("METHOD_EXIT", "CONSTRUCTOR_EXIT"):
                name = ev.fields[-1] if ev.fields else None
                base = unit_method_base[-1] if unit_method_base else 0
                for k in range(len(method_stack) - 1, base - 1, -1):
                    if name and (method_stack[k] == name or method_stack[k].startswith(name) or name in method_stack[k]):
                        del method_stack[k:]
                        break
            ev.depth = len(unit_stack)
            ev.unit = unit_stack[-1][0] if unit_stack else ""
            ev.method = method_stack[-1] if method_stack else ""
        except Exception as exc:  # never fail on odd input
            unclosed_problems.append((ev.line, "could not annotate event: %s" % exc))
    still_open = list(unit_stack)
    return still_open, unclosed_problems


def timeline_key(ev):
    fields = ev.fields
    src = src_of(fields)
    if src:
        fields = fields[1:]
    elif ev.type.startswith("FLOW_") and fields:
        fields = fields[1:]  # drop interview id
    body = "|".join(fields)
    # Ids and numbers vary per iteration (record Ids, counters in debug text);
    # normalising them lets the same block of work collapse into one repeat.
    return ev.type + "|" + src + "|" + re.sub(r"\d+", "#", SFID_RE.sub("<id>", body))


def timeline_text(ev):
    f = ev.fields
    t = ev.type
    if t == "CODE_UNIT_STARTED":
        return "▶ %s" % (f[-1] if f else "")
    if t == "CODE_UNIT_FINISHED":
        return "◀ %s" % (f[-1] if f else "")
    if t in ("SOQL_EXECUTE_BEGIN", "SOSL_EXECUTE_BEGIN"):
        return "SOQL %s %s" % (src_of(f), clip("|".join(f[2:]) if len(f) > 2 else "|".join(f), 160))
    if t == "DML_BEGIN":
        return "DML %s" % " ".join(f)
    if t == "FLOW_ELEMENT_BEGIN":
        return "FLOW element %s" % " ".join(f[1:])
    if t == "METHOD_ENTRY":
        return "→ %s %s" % (src_of(f), f[-1] if f else "")
    return "%s %s" % (t, clip("|".join(f), 180))


def compress(items, key, max_cycle=12):
    """Collapse consecutive repeats of a block of 1..max_cycle items (>=3 repeats)."""
    keys = [key(x) for x in items]
    out, i, n = [], 0, len(items)
    while i < n:
        best = None
        for k in range(1, max_cycle + 1):
            if i + 3 * k > n:
                break
            r = 1
            while i + (r + 1) * k <= n and keys[i + r * k: i + (r + 1) * k] == keys[i: i + k]:
                r += 1
            if r >= 3 and (best is None or r * k > best[0] * best[1]):
                best = (r, k)
        if best:
            r, k = best
            for j in range(k):
                out.append(("item", items[i + j]))
            out.append(("repeat", k, r - 1, items[i + k].line, items[i + r * k - 1].line))
            i += r * k
        else:
            out.append(("item", items[i]))
            i += 1
    return out


def section(title):
    print()
    print("## " + title)


def inventory(path, text, args):
    events, header, preamble_unparsed, truncation = parse(text)
    still_open, nesting_problems = annotate(events)
    total_lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)

    print("=" * 78)
    print("# Inventory: %s" % path)
    print("=" * 78)
    print("Log lines: %d | timestamped events: %d | non-event lines before first event: %d"
          % (total_lines, len(events), preamble_unparsed))
    if header:
        print("Header (line %d): API version %s | levels %s" % header)
    else:
        print("Header: none found (log may be an excerpt)")
    if events:
        first, last = events[0], events[-1]
        print("First event: line %d %s (%d ns) %s" % (first.line, first.ts, first.ns, first.type))
        print("Last event:  line %d %s (%d ns) %s" % (last.line, last.ts, last.ns, last.type))
        print("Elapsed by nanosecond clock: %.1f ms" % ((last.ns - first.ns) / 1e6))
    else:
        print("No timestamped events parsed. Read the log directly.")
        return set()

    types = Counter(e.type for e in events)

    # ---- completeness ---------------------------------------------------
    section("Completeness / truncation evidence")
    notes = []
    for ln, txt in truncation:
        notes.append("line %d: %s" % (ln, txt))
    if "EXECUTION_STARTED" not in types:
        notes.append("no EXECUTION_STARTED event (log may begin mid-transaction or be an excerpt)")
    if "EXECUTION_FINISHED" not in types:
        notes.append("no EXECUTION_FINISHED event (log may end mid-transaction or be an excerpt)")
    for name, ln in still_open:
        notes.append("code unit opened at line %d never finished: %s" % (ln, clip(name, 100)))
    for ln, txt in nesting_problems[:20]:
        notes.append("line %d: %s" % (ln, txt))
    print("\n".join("- " + n for n in notes) if notes else "- none found")

    # ---- errors ---------------------------------------------------------
    section("Exceptions, fatal errors and error-like events (all, in order)")
    errs = [e for e in events if ERRORISH_RE.search(e.type)]
    if not errs:
        print("- none")
    for e in errs:
        print("- line %d %s [%s] %s%s" % (e.line, e.ts, e.type, src_of(e.fields) + " " if src_of(e.fields) else "",
                                          redact(clip("|".join(e.fields[1:] if src_of(e.fields) else e.fields), 400))))
        ctx = []
        if e.unit:
            ctx.append("unit: " + clip(e.unit, 100))
        if e.method:
            ctx.append("method: " + clip(e.method, 100))
        if ctx:
            print("    (" + "; ".join(ctx) + ")")
        if e.type == "FATAL_ERROR":
            for ln, l in e.extra[:25]:
                if l.strip():
                    print("    line %d stack: %s" % (ln, redact(clip(l.strip(), 200))))

    # ---- code units -----------------------------------------------------
    section("Code units (start order, indented by nesting)")
    units = [e for e in events if e.type == "CODE_UNIT_STARTED"]
    unit_counts = Counter(e.fields[-1] if e.fields else "?" for e in units)
    shown = 0
    for e in units:
        if shown >= args.max_units:
            print("  ... %d more code units not listed (see counts below)" % (len(units) - shown))
            break
        print("  line %-7d %s%s" % (e.line, "  " * e.depth, clip(e.fields[-1] if e.fields else "?", 140)))
        shown += 1
    multi = [(n, c) for n, c in unit_counts.most_common() if c > 1]
    if multi:
        print("  Units started more than once:")
        for n, c in multi[:20]:
            print("    %4d × %s" % (c, clip(n, 140)))

    # ---- SOQL -----------------------------------------------------------
    section("SOQL / SOSL")
    soql_sig = Counter()
    soql_rows = defaultdict(int)
    soql_lines = defaultdict(list)
    soql_ctx = defaultdict(Counter)
    pending = None
    total_q = 0
    for e in events:
        if e.type in ("SOQL_EXECUTE_BEGIN", "SOSL_EXECUTE_BEGIN"):
            total_q += 1
            q = "|".join(e.fields[2:]) if len(e.fields) > 2 else "|".join(e.fields[1:])
            sig = (src_of(e.fields), re.sub(r"\s+", " ", q).strip())
            soql_sig[sig] += 1
            soql_lines[sig].append(e.line)
            soql_ctx[sig][(e.unit, e.method)] += 1
            pending = sig
        elif e.type in ("SOQL_EXECUTE_END", "SOSL_EXECUTE_END") and pending is not None:
            for f in e.fields:
                if f.startswith("Rows:"):
                    try:
                        soql_rows[pending] += int(f[5:])
                    except ValueError:
                        pass
            pending = None
    print("Query executions: %d | distinct signatures (source line + text): %d" % (total_q, len(soql_sig)))
    for sig, c in soql_sig.most_common(args.top):
        ls = soql_lines[sig]
        print("  %4d × %s %s" % (c, sig[0] or "[?]", redact(clip(sig[1], 200))))
        print("         rows returned total: %d | log lines %d..%d" % (soql_rows[sig], ls[0], ls[-1]))
        for (unit, meth), n in soql_ctx[sig].most_common(3):
            print("         %d in unit '%s'%s" % (n, clip(unit or "?", 80), (" / method '%s'" % clip(meth, 80)) if meth else ""))

    # ---- DML ------------------------------------------------------------
    section("DML")
    dml_sig = Counter()
    dml_rows = defaultdict(int)
    dml_lines = defaultdict(list)
    dml_ctx = defaultdict(Counter)
    for e in events:
        if e.type == "DML_BEGIN":
            op = next((f[3:] for f in e.fields if f.startswith("Op:")), "?")
            ty = next((f[5:] for f in e.fields if f.startswith("Type:")), "?")
            rows = next((f[5:] for f in e.fields if f.startswith("Rows:")), "0")
            sig = (src_of(e.fields), op, ty)
            dml_sig[sig] += 1
            dml_lines[sig].append(e.line)
            dml_ctx[sig][(e.unit, e.method)] += 1
            try:
                dml_rows[sig] += int(rows)
            except ValueError:
                pass
    print("DML statements: %d | distinct signatures: %d" % (sum(dml_sig.values()), len(dml_sig)))
    for sig, c in dml_sig.most_common(args.top):
        ls = dml_lines[sig]
        print("  %4d × %s Op:%s Type:%s | rows total %d | log lines %d..%d"
              % (c, sig[0] or "[?]", sig[1], sig[2], dml_rows[sig], ls[0], ls[-1]))
        for (unit, meth), n in dml_ctx[sig].most_common(3):
            print("         %d in unit '%s'%s" % (n, clip(unit or "?", 80), (" / method '%s'" % clip(meth, 80)) if meth else ""))

    # ---- Flow -----------------------------------------------------------
    flow_events = [e for e in events if e.type.startswith("FLOW_")]
    section("Flow")
    if not flow_events:
        print("- no FLOW_* events")
    else:
        created = [e for e in events if e.type == "FLOW_CREATE_INTERVIEW_BEGIN"]
        started = [e for e in events if e.type == "FLOW_START_INTERVIEW_BEGIN"]
        print("Interviews created: %d | interview starts: %d" % (len(created), len(started)))
        for label, evs in (("created", created), ("started", started)):
            names = Counter(clip(e.fields[-1], 120) for e in evs if e.fields)
            for n, c in names.most_common(10):
                print("  %4d × %s: %s (first at line %d)"
                      % (c, label, n, next(e.line for e in evs if e.fields and clip(e.fields[-1], 120) == n)))
        elems = Counter()
        elem_lines = defaultdict(list)
        for e in events:
            if e.type == "FLOW_ELEMENT_BEGIN" and len(e.fields) >= 2:
                k = " ".join(e.fields[1:])
                elems[k] += 1
                elem_lines[k].append(e.line)
        if elems:
            print("Element executions (type + API name):")
            for k, c in elems.most_common(args.top):
                print("  %4d × %s | log lines %d..%d" % (c, clip(k, 140), elem_lines[k][0], elem_lines[k][-1]))
        ftypes = Counter(e.type for e in flow_events)
        print("FLOW_* event types: " + ", ".join("%s:%d" % kv for kv in sorted(ftypes.items())))

    # ---- Callouts -------------------------------------------------------
    section("Callouts")
    calls = [e for e in events if e.type in ("CALLOUT_REQUEST", "CALLOUT_RESPONSE") or e.type.startswith("NAMED_CREDENTIAL")]
    if not calls:
        print("- none")
    last_req = None
    for e in calls:
        txt = redact(clip("|".join(e.fields), 300))
        if e.type == "CALLOUT_REQUEST":
            last_req = e
            print("- line %d %s REQUEST %s" % (e.line, e.ts, txt))
        elif e.type == "CALLOUT_RESPONSE":
            el = (" (+%.1f ms after request at line %d)" % ((e.ns - last_req.ns) / 1e6, last_req.line)) if last_req else ""
            print("- line %d %s RESPONSE %s%s" % (e.line, e.ts, txt, el))
            last_req = None
        else:
            print("- line %d %s %s %s" % (e.line, e.ts, e.type, txt))

    # ---- USER_DEBUG -----------------------------------------------------
    section("USER_DEBUG (developer-written; not platform facts)")
    dbg = [e for e in events if e.type == "USER_DEBUG"]
    print("Count: %d" % len(dbg))
    for e in dbg[: args.max_debug]:
        msg = "|".join(e.fields[2:]) if len(e.fields) > 2 else "|".join(e.fields)
        if e.extra:
            msg += " " + " ".join(l.strip() for _, l in e.extra[:5])
        print("  line %d %s %s" % (e.line, src_of(e.fields), redact(clip(msg, 200))))
    if len(dbg) > args.max_debug:
        print("  ... %d more not shown" % (len(dbg) - args.max_debug))

    # ---- Limits ---------------------------------------------------------
    section("Governor usage reported by the log")
    blocks = [e for e in events if e.type == "LIMIT_USAGE_FOR_NS"]
    point = [e for e in events if e.type == "LIMIT_USAGE"]
    if not blocks and not point:
        print("- no LIMIT_USAGE_FOR_NS / LIMIT_USAGE events (profiling level may be too low, or log truncated)")
    maxes = {}
    for b in blocks:
        ns_name = b.fields[0] if b.fields else "?"
        for _, l in b.extra:
            m = LIMIT_LINE_RE.match(l)
            if m:
                metric, used, mx, tail = m.group(1).strip(), int(m.group(2)), int(m.group(3)), m.group(4).strip()
                key = (ns_name, metric)
                if key not in maxes or used > maxes[key][0]:
                    maxes[key] = (used, mx, tail, b.line)
    if blocks:
        print("%d LIMIT_USAGE_FOR_NS block(s); highest value per metric across blocks:" % len(blocks))
        for (ns_name, metric), (used, mx, tail, ln) in sorted(maxes.items()):
            pct = (" %5.1f%%" % (100.0 * used / mx)) if mx else "      "
            print("  %-14s %-42s %8d / %-8d%s  (block at line %d)%s"
                  % (clip(ns_name, 14), clip(metric, 42), used, mx, pct, ln, ("  " + tail) if tail else ""))
    for e in point[:30]:
        print("  LIMIT_USAGE line %d: %s" % (e.line, clip("|".join(e.fields), 160)))

    # ---- methods --------------------------------------------------------
    meth = Counter(e.fields[-1] for e in events if e.type in ("METHOD_ENTRY", "CONSTRUCTOR_ENTRY") and e.fields)
    section("Most-entered methods / constructors")
    if not meth:
        print("- no METHOD_ENTRY events (APEX_CODE level may be too low to record them)")
    for m_, c in meth.most_common(args.top):
        print("  %5d × %s" % (c, clip(m_, 160)))

    # ---- event types ----------------------------------------------------
    section("All event types (count)")
    print(", ".join("%s:%d" % kv for kv in sorted(types.items())))

    # ---- timeline -------------------------------------------------------
    if args.timeline:
        wanted = set(TIMELINE_TYPES)
        if args.methods:
            wanted.add("METHOD_ENTRY")
        lo, hi = args.from_line or 0, args.to_line or 10 ** 12
        items = [e for e in events if lo <= e.line <= hi and (e.type in wanted or ERRORISH_RE.search(e.type))]
        section("Timeline (key events; repeated blocks collapsed; line = log line)")
        out = compress(items, timeline_key)
        printed = 0
        for entry in out:
            if printed >= args.max_timeline:
                print("  ... timeline cut at %d entries; use --from-line/--to-line to view a window" % args.max_timeline)
                break
            if entry[0] == "item":
                e = entry[1]
                print("  %-7d %s %s%s" % (e.line, e.ts, "  " * e.depth, redact(timeline_text(e))))
            else:
                _, k, extra_reps, a, b = entry
                print("  %-7s %s ↻ previous %d line(s) repeated %d more time(s) (log lines %d..%d)"
                      % ("", " " * 12, k, extra_reps, a, b))
            printed += 1

    return set(ASYNC_JOB_ID_RE.findall(text))


def main():
    ap = argparse.ArgumentParser(description="Inventory Salesforce debug logs (no diagnosis).")
    ap.add_argument("logs", nargs="+", help="log file path(s), or - for stdin")
    ap.add_argument("--timeline", action="store_true", help="print a compressed timeline of key events")
    ap.add_argument("--methods", action="store_true", help="include METHOD_ENTRY in the timeline")
    ap.add_argument("--from-line", type=int, help="timeline window start (log line)")
    ap.add_argument("--to-line", type=int, help="timeline window end (log line)")
    ap.add_argument("--top", type=int, default=15, help="rows per grouped list (default 15)")
    ap.add_argument("--max-units", type=int, default=150)
    ap.add_argument("--max-debug", type=int, default=40)
    ap.add_argument("--max-timeline", type=int, default=400)
    args = ap.parse_args()

    job_ids = []
    for p in args.logs:
        try:
            if p == "-":
                text = sys.stdin.read()
            else:
                with open(p, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
        except OSError as exc:
            print("Could not read %s: %s" % (p, exc), file=sys.stderr)
            continue
        job_ids.append((p, inventory(p, text, args)))
        print()

    if len(job_ids) > 1:
        print("=" * 78)
        print("# Across logs")
        print("Async-job-style Ids (707 prefix) appearing in more than one log. A shared Id is a lead to check,")
        print("not proof that the logs belong to one chain:")
        seen = defaultdict(list)
        for p, ids in job_ids:
            for i in ids:
                seen[i].append(p)
        shared = {i: ps for i, ps in seen.items() if len(ps) > 1}
        if not shared:
            print("- none")
        for i, ps in sorted(shared.items()):
            print("- %s in: %s" % (i, ", ".join(ps)))


if __name__ == "__main__":
    main()
