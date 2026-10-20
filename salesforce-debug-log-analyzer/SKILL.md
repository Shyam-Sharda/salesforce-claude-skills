---
name: "salesforce-debug-log-analyzer"
description: Analyzes Salesforce debug logs to explain what actually happened at runtime - reconstructs the execution path through triggers, Flows, Apex, async jobs and callouts, separates the root cause from wrapper exceptions and downstream symptoms, reads governor usage from the log itself, and recommends the smallest evidence-supported fix. Make sure to use this skill whenever the user pastes, uploads or points to a Salesforce debug log or log excerpt (FATAL_ERROR, EXCEPTION_THROWN, CODE_UNIT_STARTED, SOQL_EXECUTE_BEGIN, FLOW_ELEMENT_ERROR, LIMIT_USAGE_FOR_NS lines), or asks why a Salesforce save, transaction, Flow, Queueable, Batch, future or scheduled job failed or ran slowly, which code caused a governor-limit error, or where recursion or repeated execution comes from, even if they never say "debug log". Do not use for Apex or Flow reviews that have no runtime log or runtime symptom (use the Apex code reviewer or Flow reviewer), or for writing Apex tests.
---

# Salesforce Debug Log Analyzer

A debug log is a record of what the platform actually did. The value of this skill is turning that record into a short, trustworthy answer to five questions:

1. What transaction or execution path ran?
2. Where did the failure or suspicious behavior begin?
3. What root cause does the log support?
4. What is only a symptom or downstream consequence?
5. What should the developer change or inspect next?

The final exception line is usually the least informative part of a log. "Too many SOQL queries: 101" says a limit was hit; the useful answer says which trigger called which method repeatedly, which query repeated and how many times, and how to stop the repetition. Aim for the second kind of answer every time.

## Core principles

1. **Evidence only.** Conclusions come from the log and any supplied source. Do not invent Apex, Flow behavior, metadata, validation rules, other automation, org configuration, record values or permissions. When a conclusion depends on something that is not visible, label it **Cannot Verify** (exact label) and say what would settle it.
2. **Runtime analysis, not code review.** Discuss only the code or Flow elements needed to explain and fix the logged behavior. An unrelated naming issue in the same class, or a maintainability concern in the same Flow, is out of scope. Full reviews belong to `salesforce-apex-code-reviewer` and `salesforce-flow-reviewer`; tests belong to `salesforce-apex-test-generator`. Write tests only if the user asks.
3. **A clean log is a valid result.** If the transaction succeeded with ordinary usage, say so briefly. Manufactured findings erode trust in the real ones.
4. **Trust the log's own numbers.** When the log reports usage and maximums (for example `Number of SOQL queries: 12 out of 100`), use those values. Do not quote remembered limits or remembered platform behavior when the log or supplied metadata says otherwise, because limits and behavior vary by context, edition and API version.
5. **Smallest fix.** Recommend the smallest change that addresses the demonstrated cause. Do not redesign architecture, and do not change production code just to make logs easier to read.

## Workflow

### 0. Size up the input

For a short excerpt, read it directly. For a long log (roughly a few hundred lines or more), or several logs, run the inventory helper first; it counts and groups events deterministically, which is exactly where reading by eye goes wrong:

```bash
python3 <skill-dir>/scripts/debug_log_inventory.py path/to/log.log            # inventory
python3 <skill-dir>/scripts/debug_log_inventory.py path/to/log.log --timeline # + compressed timeline
```

If the log was pasted into chat, save it to a file first. The helper only inventories; it does not judge severity or causes. Use its line numbers to go back and read the relevant stretch of the raw log before concluding anything, and treat anything it marks as unparsed as still needing your attention.

### 1. Transaction context

Identify, when the log shows it: trigger, Flow (record-triggered, autolaunched, screen), synchronous Apex, Queueable, Batch, Schedulable, future, Apex REST, Aura/LWC `@AuraEnabled` call, Platform Event subscriber, anonymous Apex, callout. Note the log's API version and log levels from the header line as log/runtime context (see Version evidence below). Mention the running user or request context only if the log provides it.

### 2. Terminal outcome

Look for `FATAL_ERROR`, unhandled `EXCEPTION_THROWN`, `FLOW_ELEMENT_ERROR` and Flow fault messages, DML failures, callout failures, rollback, or clean completion (`CODE_UNIT_FINISHED` for the outer unit and `EXECUTION_FINISHED`). An exception that was thrown and caught is not the terminal outcome, and the last exception in the log is not automatically the root cause.

### 3. Reconstruct the relevant path

Trace backward from the outcome using code units, method entries, SOQL, DML, Flow interview and element events, callouts, exceptions, user debug lines and limit blocks. Follow only the path that matters to the problem. `references/debug-event-guide.md` explains what each event family establishes and what it does not.

### 4. Separate root cause from symptoms

Common wrappers: a `DmlException` carrying a validation-rule, `addError`, trigger or Flow failure; `CANNOT_EXECUTE_FLOW_TRIGGER` surfacing a failure inside an invoked Apex action or Flow element; a governor exception thrown at one line but caused by repeated work earlier; a null dereference caused by an empty query several calls earlier. Name the deepest failure the log actually shows, and say what is wrapper. When the log exposes a deeper cause, do not stop at the outer error. A typical layered failure:

```text
Case update → after-save Flow → Apex action → Asset query Rows:0 → asset = null
  → NullPointerException            ← deepest evidenced failure
  → FLOW_ELEMENT_ERROR / FAULT      ← Flow-level wrapper
  → CANNOT_EXECUTE_FLOW_TRIGGER / outer DmlException   ← caller-visible wrapper
```

Each link in that chain still needs its own evidence (see the Rows:0 guidance in `references/debug-event-guide.md`). `references/failure-patterns.md` covers how each common failure type presents and how to trace it.

### 5. Resource usage

Read `LIMIT_USAGE_FOR_NS` / `CUMULATIVE_LIMIT_USAGE` blocks for SOQL, query rows, DML statements and rows, CPU, heap, callouts, future calls, queueables, emails. Classify each as an actual limit failure, clearly high usage, or normal. Say "normal" when it is normal. Do not claim a limit was approached unless the reported numbers show it.

### 6. Repetition

Look for the same query or DML signature repeating, the same trigger or Flow interview re-entering, repeated callouts or enqueues. Repetition alone is not proof of a loop or recursion: show the sequence that supports the claim (for example, the same method entry followed by the same query, 100 times, under one trigger code unit), and word it as described in Repetition versus proven loop structure below.

### 7. Map to source, if supplied

Use class, method, line numbers from `[NN]` markers and stack traces, trigger names and Flow element API names to point at the exact place. Show only the affected lines in a fix. Without source, describe the fix in terms of the evidenced method or element and note what you could not see.

### 8. Unknowns

Collect meaningful unknowns: truncated log, missing source or Flow metadata, unknown decision or entry criteria, validation rule definitions, record values, permissions, external system behavior, debug levels too low to show the needed events, an uncertain parent/child relationship between logs. Skip unknowns that do not affect the conclusion. For each: what is unknown, how it affects the conclusion, and what would settle it.

## Confidence language

Match wording to the strength of evidence, and never present a guess as a root cause:

- Strong evidence: "The transaction fails because..."
- Partial evidence: "The log strongly suggests..."
- Insufficient evidence: "**Cannot Verify:** ..."

When several explanations remain possible, say so. Rank them only if the log provides something that distinguishes them. Do not invent probabilities.

## Things that need extra care

- **USER_DEBUG lines are the developer's claims, not platform facts.** A debug message saying "Technician found" does not prove a record existed; check it against the surrounding `SOQL_EXECUTE_END|Rows:` or other platform events. Use debug lines for intent and logged values.
- **Truncated logs.** Signs include `*** Skipped N bytes of detailed log`, `MAXIMUM DEBUG LOG SIZE REACHED`, a log that starts or ends mid-unit, or code units that open but never close. State **Cannot Verify:** the log is truncated before/after [event], then analyze what is present without claiming the full path is known.
- **Multiple logs.** Analyze each transaction separately first. Connect them only with explicit evidence such as a matching async job Id, request Id or an enqueue in one log matching the job in another; shared class names are not enough. When a connection is evidenced, a short cross-log chain helps. When it is not: **Cannot Verify:** whether these logs belong to the same chain, and what Id would settle it.
- **Async work.** An enqueued Queueable, future call or Batch runs in its own transaction with its own log. Do not merge timelines unless evidence connects them.
- **Secrets.** Logs can contain session Ids, OAuth tokens, Authorization headers, passwords, API keys, cookies and signed URLs. Never repeat their values; quote around them as `[REDACTED AUTHORIZATION HEADER]` and similar. Mention a secret only if the log actually contains one.

### Version evidence

Treat the version shown in the debug-log header as log/runtime context. Use it when discussing the log format, the available event structure and the runtime/debug context.

When a conclusion depends specifically on the API version at which an Apex class or trigger was compiled, prefer the corresponding supplied `.cls-meta.xml` or `.trigger-meta.xml`. Do not claim that the debug-log header proves the metadata API version of every Apex class or trigger executed in the transaction.

If a diagnosis materially depends on a class/trigger compile version and that metadata was not supplied, use:

**Cannot Verify:** the Apex metadata API version of [class/trigger]. The debug log header provides runtime/log context but does not establish that component's compile version. Supplying the corresponding metadata file would settle it.

### Repetition versus proven loop structure

Repeated METHOD_ENTRY, SOQL, DML or other events can strongly support per-record processing, but repetition alone does not prove the exact source-code structure. Without supplied Apex source, prefer wording such as: "`DispatchService.assignTechnician` was called repeatedly from the same handler call site, consistent with per-record processing." Do not say the method "is inside a for-loop" or "is called once per record" unless the supplied source or other runtime evidence establishes that structure. If source is later supplied, promote the conclusion from inferred to confirmed. Repeated query or DML patterns are still the root cause when the runtime evidence supports it; only the description of the code structure is hedged.

When describing scaling failures, state the condition that actually reaches the limit, not a record count the log does not prove. Prefer "Any transaction that causes this query path to execute more than the available SOQL budget can fail with the same limit error", or, when the log establishes one query per execution, "Any transaction that causes this path to execute more than 100 times under the same applicable 100-query limit can exhaust the SOQL budget." Keep record count, qualifying-record count, method execution count and query execution count distinct, and do not assume every record follows the same branch unless the source or log proves it.

### Scope of an observed failure

When the log proves a failure for one runtime path, describe that path precisely: "`CreateWorkOrderAction` fails on this execution path when the Account has no matching Asset and the resulting `asset` value is dereferenced." Do not turn one observed execution into a universal statement such as "fails whenever the Account has no Asset". A universal conclusion is appropriate only when the supplied source establishes that all equivalent inputs take the same path.

### Absence of events

When reasoning from missing events, describe what the log shows, not the implementation in general. Say "No SOQL or DML events were recorded inside `AccountTriggerHandler.beforeUpdate` in this log", not "`AccountTriggerHandler.beforeUpdate` does no database work." When the header's log levels are too low for the absence to mean anything, use **Cannot Verify** instead.

### Flow fault-path evidence

A debug log can prove that an element faulted and whether the transaction recovered afterward. Without the Flow metadata, do not claim that no fault connector exists, where a fault connector points, whether it is misconfigured, or whether another configured path was available but not taken. Prefer: "The log shows that no recovery path successfully handled the `Create_Work_Order` failure before the Flow interview ended." Then: **Cannot Verify:** whether the element has a configured fault connector and where it routes. The Flow metadata would settle it.

## Response format

Keep it proportional: a simple problem gets a simple answer. Use this structure:

```
## What Happened
## Urgent - Needs Attention
## Warning - Should Change
## Suggested Changes
## Cannot Verify            (only when meaningful unknowns remain)
```

**What Happened**: a few sentences on the relevant runtime path, and the root cause versus the wrapper when they differ. Cite timestamps or log line numbers for the key events so the developer can find them, and check each cited number and count against the log or the inventory output before answering; a wrong line number sends the developer to the wrong place. When it helps, add a compact chain:

```text
WorkOrder update (150 records)
  ↓
WorkOrderTrigger (BeforeUpdate)
  ↓
DispatchService.assignTechnician  ← entered repeatedly from the same call site
  ↓
SELECT ... FROM Contact WHERE Id = :tmpVar1   ×100
  ↓
System.LimitException: Too many SOQL queries: 101
```

Do not reproduce the log.

**Urgent - Needs Attention**: only issues that cause or will cause transaction failure, incorrect data, governor-limit failure, security failure, repeated production errors or serious instability. If none: `No urgent issues identified.`

**Warning - Should Change**: high but non-failing usage, suspicious repetition, fragile error handling, credible future limit risk, behavior that works now but is concerning. If none: `No warnings identified.`

**Suggested Changes**: optional debugging, logging or observability improvements that would genuinely help. Do not fill this section for its own sake. If none: `No additional changes suggested.`

Urgent and Warning items:

```
**1. Short issue title**

**What's wrong:** the problem, grounded in specific log evidence.

**Fix:** the smallest practical correction.
```

Suggested Changes items use **Change:** and **Fix:** instead.

**Cannot Verify**: one short item per unknown, covering what is unknown, its impact, and what would settle it. When an unknown attaches to one finding, it can sit directly under that finding instead; put it in one place, not both. Do not create items for unknowns that would not change the conclusion.

Keep it tight:
- Each finding appears once, under its severity. Do not add Governor Limit Review, Flow Review, Security Review, Performance Review, Overall Assessment or Recommended Next Steps sections; those concerns go inside the three main sections.
- Order by consequence within each section.
- For a successful, ordinary log, the whole response can be four short sections saying exactly that.

### Successful clean logs

When a transaction completes normally, has no meaningful exception, shows no suspicious repetition or re-entry, and has ordinary governor usage, keep the answer short. Do not enumerate every governor metric unless one is relevant, the user asks for the numbers, or the comparison materially helps explain performance. Do not invent bulkification advice, recursion guards, async processing, CPU or query optimizations, or architectural changes for a transaction that does not show those problems. A clean answer can be:

```
## What Happened

The service queried one Account, updated it, the before-update trigger ran once,
and the transaction completed successfully.

Governor usage was low and the supplied log shows no meaningful repetition,
recursion, or runtime concern.

## Urgent - Needs Attention

No urgent issues identified.

## Warning - Should Change

No warnings identified.

## Suggested Changes

No additional changes suggested.
```

### Closing question

When a supplied artifact needs changing, end with one line suited to it:
- Apex: "Would you like me to update and recreate the Apex class with this fix?"
- Flow: "Would you like me to update and recreate the Flow with this fix?"
- Other file: "Would you like me to update and recreate this file with these changes?"

Skip it when the user already asked for the change, when you already made it in this response, when no source was supplied, or when no change is recommended. Do not rewrite a full class or Flow unless asked.

## Fix guidance

Typical smallest fixes: collect Ids and query once outside the loop; move DML after the loop; null-check a map lookup or handle an empty query result; add a fault path to the failing Flow element when the metadata shows it lacks one; guard re-entry for already-processed records; handle a failed callout response before parsing; correct the actual failing validation condition. When several fixes would work, prefer the one that addresses the evidenced cause with the least architectural change, and say in one clause why a bigger change is needed if it is.

When the source code is not supplied, describe the smallest change conceptually, for example: "**Fix:** Collect the technician User Ids first, query the Users once using `WHERE Id IN :techIds`, store them in a `Map<Id, User>`, and use that map while processing the Work Orders." Do not generate speculative replacement Apex with placeholder or invented field API names unless the user asks for illustrative code. When the user wants the exact implementation, ask for the relevant source file.

## Example requests and what a good answer does

- "Analyze this Salesforce debug log. The user gets `Too many SOQL queries: 101` when updating about 150 Work Orders. Tell me where the repeated queries are coming from and what needs to change." → names the trigger and helper method, the repeated query signature and how many times it ran, treats the LimitException as the symptom, recommends one query outside the loop.
- "This save gives me `CANNOT_EXECUTE_FLOW_TRIGGER`, but I can't tell what actually failed. Here's the debug log plus the Flow XML and Apex action. Find the root cause." → follows the outer DML into the Flow interview, names the failing element and the deepest exception in the invoked Apex, separates it from the wrapper, uses the supplied source for the fix.
- "Can you check this debug log? Nothing failed, but this transaction feels slow. Tell me whether the log shows any meaningful governor-limit, recursion, or performance concern. Don't invent issues if it looks normal." → reports actual usage and elapsed time from the log; if ordinary, says so in a short response with no invented advice.
