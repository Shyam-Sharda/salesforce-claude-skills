# Runtime Failure Patterns

How common Salesforce runtime failures show up in a debug log, how to trace them to the cause, and what usually remains unknown. Each pattern: **Signature** (what you see), **Trace** (where to look), **Root vs symptom**, **Smallest fix**, **Cannot Verify** (typical gaps).

## Contents
1. Governor exhaustion
2. SOQL / DML repetition
3. Recursion and re-entry
4. Nested DML failures
5. Flow failures
6. Null dereferences and query exceptions
7. Callout failures
8. Record locking
9. Mixed DML
10. Security and access errors
11. Async failures
12. Successful but slow transactions

---

## 1. Governor exhaustion

**Signature:** `System.LimitException: Too many SOQL queries: 101`, `Too many DML statements: 151`, `Too many query rows: 50001`, `Apex CPU time limit exceeded`, `Apex heap size too large`, too many callouts, too many queueable jobs. Often followed by a limit block with a value above its maximum.

**Trace:** The line where the exception fires is just where the counter ran out. Find what consumed the budget: group SOQL/DML by signature and source line, count per signature, then find the code unit or method that issued the dominant signature. For CPU-limit diagnosis, rely primarily on the CPU values reported by `LIMIT_USAGE_FOR_NS`, `LIMIT_USAGE`, `CUMULATIVE_LIMIT_USAGE`, and relevant profiling events when they are present.

Nanosecond timestamp differences show elapsed request time, not CPU consumption. They can help locate a slow interval, but they do not by themselves prove that Apex, Flow, or another Salesforce component consumed CPU during that interval.

For a successful but slow transaction, elapsed timestamp gaps are still useful for locating where wall-clock time was spent, especially around callouts or other long-running operations.

For heap, look for large query row counts or big collections built just before the failure.

**Root vs symptom:** The exception is the symptom. The root cause is the repeated or oversized work. Name it.

**Smallest fix:** Query once outside the loop and use a map; move DML after the loop on a collection; reduce rows with selective filters or only the fields needed; stop re-entry. Do not suggest async offloading unless the work genuinely cannot fit in one transaction.

**Cannot Verify:** whether other automation in the org also contributes, when its events are absent or truncated.

## 2. SOQL / DML repetition

**Signature:** The same query text at the same `[line]`, or the same `Op:Type` DML at the same `[line]`, many times in one transaction.

**Trace:** Check what sits between repetitions. Same method entry each time, under one trigger code unit → consistent with per-record processing; the loop itself is confirmed only by source. A new trigger code unit between repetitions → re-entry (pattern 3). Separate trigger code units opening sequentially for one original DML → platform chunking; repetition per chunk may be acceptable.

**Root vs symptom:** If the transaction still succeeded, this is a Warning, not Urgent, unless the numbers are close to the reported maximum or will grow with data volume the user described.

**Smallest fix:** Collect keys, query once, map by key; accumulate records, one DML after the loop.

**Cannot Verify:** the exact loop structure when source is not supplied. Say the per-record processing is inferred from the repeated signature and call site.

## 3. Recursion and re-entry

**Signature:** A trigger or record-triggered Flow code unit opening again inside a DML issued by itself or by automation it started:

```text
AccountTrigger (AfterUpdate)
  ↓ DML Update Account
AccountTrigger (AfterUpdate)   ← re-entered
  ↓ ...
```

Or: trigger → Flow Update Records → same trigger again.

**Trace:** For each repeated code unit, find the `DML_BEGIN` it sits inside, and which unit issued that DML. Only call it recursion when the nesting shows the cycle.

**Root vs symptom:** Re-entry often surfaces as a limit exception, a self-reference error, or duplicate side effects. The cycle is the cause.

**Smallest fix:** Skip records already processed in this transaction (a static set of Ids), or only update fields that actually changed so the update does not re-qualify. Avoid blanket static booleans that disable the trigger for later legitimate chunks; mention this trade-off when recommending a guard.

**Cannot Verify:** Flow entry criteria and other automation definitions, unless supplied.

## 4. Nested DML failures

**Signature:** `System.DmlException: Update failed. First exception on row 0 with id ...; first error: <STATUS_CODE>, <message>`.

**Trace:** Look inside the `DML_BEGIN`/`DML_END` window for the first failure: `VALIDATION_FAIL`, an `EXCEPTION_THROWN` in a trigger, an `addError` message, a `FLOW_ELEMENT_ERROR`, duplicate rule events. The status code tells you the category:
- `FIELD_CUSTOM_VALIDATION_EXCEPTION` — validation rule or `addError`. The message is the rule's error message; the rule name appears only if validation events are logged.
- `CANNOT_EXECUTE_FLOW_TRIGGER` — a Flow or process failed; see pattern 5.
- `REQUIRED_FIELD_MISSING`, `INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST`, `STRING_TOO_LONG`, `DUPLICATE_VALUE` — data shape problems; name the field from the message.
- `INSUFFICIENT_ACCESS_*`, `UNABLE_TO_LOCK_ROW`, `MIXED_DML_OPERATION` — see patterns 10, 8, 9.

**Root vs symptom:** The `DmlException` is the wrapper. The inner check or exception is the cause. If the inner failure is a validation rule, the question is usually whether the data or the rule is wrong; state which the evidence supports.

**Smallest fix:** Fix the data being written, or the specific failing condition. Use partial-success DML (`Database.update(records, false)`) only when the business process genuinely tolerates per-record failure, and then handle the results.

**Cannot Verify:** the validation rule formula, the record values that triggered it, and which row failed beyond row 0, unless logged.

## 5. Flow failures

**Signature:** `FLOW_ELEMENT_ERROR`, `FLOW_ELEMENT_FAULT`, an "An unhandled fault has occurred in this flow" style message, or an outer `CANNOT_EXECUTE_FLOW_TRIGGER`.

**Trace:** Identify the Flow (from `FLOW_CREATE_INTERVIEW_*`), the interview, and the last `FLOW_ELEMENT_BEGIN` before the error. If that element is an Action/Apex call, follow the nested Apex events to the deepest `EXCEPTION_THROWN`. If it is Get/Update/Create Records, look for the DML or SOQL inside it and any failure nested there.

**Root vs symptom:** `CANNOT_EXECUTE_FLOW_TRIGGER` on the outer DML says only that the Flow failed. The cause is the element error or the exception inside the invoked Apex. Report the chain: outer DML → Flow → element → inner failure. The log shows whether any recovery path handled the fault; it does not show whether a fault connector exists or where it routes.

**Smallest fix:** Fix the inner failure (null handling in the Apex action, the failing update's data). Add a fault path on the failing element only when the business process should continue or report gracefully; a fault path that swallows errors can hide data problems.

**Cannot Verify:** fault connectors, entry conditions and element configuration without Flow metadata; Apex action logic without its source.

## 6. Null dereferences and query exceptions

**Signature:** `System.NullPointerException: Attempt to de-reference a null object`, `System.QueryException: List has no rows for assignment to SObject`, `List has more than 1 row for assignment to SObject`, `List index out of bounds`.

**Trace:** Go back from the exception's `[line]` to the value's origin: a `SOQL_EXECUTE_END|Rows:0`, a map lookup on a key that was never added, a lookup field that was null on the record, an empty collection. Logged `VARIABLE_ASSIGNMENT` values at fine levels can show the null directly.

**Root vs symptom:** The dereference line is the symptom; the empty query or missing key is the cause once the log or source connects it to the failing value. Describe the observed path, not every possible input, and do not invent which record was missing data.

**Smallest fix:** Query into a list and handle empty; check `map.containsKey` or null before use; guard the specific lookup.

**Cannot Verify:** the record values, when not logged.

## 7. Callout failures

**Signature:** `CALLOUT_RESPONSE` with non-2xx `StatusCode`, `System.CalloutException` (read timed out, unauthorized endpoint, uncommitted work pending), `JSONException` or `TypeException` right after a response.

**Trace:** Pair each request with its response, note status and elapsed nanoseconds. A parse exception after a 4xx/5xx means the code parsed an error body. "Uncommitted work pending" → find the DML earlier in the same transaction. Many callouts in sequence → check the callout limit block.

**Root vs symptom:** A remote 500 is outside the org; the in-org defect is usually the missing status check or the DML-before-callout ordering.

**Smallest fix:** Check status before parsing; move the callout before the DML, or move it to a Queueable when DML must come first.

**Cannot Verify:** the external system's behavior and why it returned the error. Redact any credentials, tokens or Authorization headers in quoted lines.

## 8. Record locking

**Signature:** `UNABLE_TO_LOCK_ROW, unable to obtain exclusive access to this record`.

**Trace:** Identify the object and record from the DML and message. Note repeated updates to the same record or to children of one parent in this transaction (child updates can lock the parent, especially with master-detail or roll-ups). Only what is in this log can be described.

**Root vs symptom:** Locking errors usually involve another transaction holding the lock. That other transaction is not visible in this log.

**Smallest fix:** Reduce updates on the shared parent, order records consistently, reduce batch size for the contending job, or add a retry where the operation is idempotent.

**Cannot Verify:** the competing transaction. A log from the same time window, or the job schedule, would settle it.

## 9. Mixed DML

**Signature:** `MIXED_DML_OPERATION, DML operation on setup object is not permitted after you have updated a non-setup object (or vice versa)`.

**Trace:** Find the two `DML_BEGIN` events: one on a setup object (User, Group, GroupMember, PermissionSetAssignment, UserRole and similar) and one on a regular object, in the same transaction.

**Smallest fix:** Move one of the DMLs to a separate transaction (`@future` or Queueable). In tests, `System.runAs` separates them.

## 10. Security and access errors

**Signature:** `INSUFFICIENT_ACCESS_OR_READONLY`, `INSUFFICIENT_ACCESS_ON_CROSS_REFERENCE_ENTITY`, `System.NoAccessException`, `Insufficient permissions: secure query included inaccessible field`, Apex class access errors on `@AuraEnabled` or REST entry.

**Trace:** Classify which layer the message points to, and keep them separate:
- record sharing (insufficient access on a specific record or cross-reference)
- object CRUD (cannot create/update the object at all)
- field-level security (inaccessible field in a user-mode or `WITH SECURITY_ENFORCED` query, or `stripInaccessible` effects)
- Apex class access (user's profile or permission set lacks the class)
- business authorization (custom checks throwing exceptions)

**Root vs symptom:** The error names the failing layer; it does not explain why the user lacks access. `with sharing` affects record sharing only; it does not enforce CRUD or FLS. User mode enforces all three. `System.runAs` exists only in tests and applies the user's record sharing, not their CRUD or FLS, so a passing `runAs` test does not prove production access.

**Smallest fix:** Correct the specific missing access for the intended users, or run the operation in the intended mode. Do not recommend `without sharing` to make an error go away unless the use case genuinely needs system access.

**Cannot Verify:** the user's profile, permission sets, sharing settings and OWDs.

## 11. Async failures

**Signature:** The entry code unit is a Queueable `execute`, Batch `start`/`execute`/`finish`, a future method, or a Schedulable `execute`. Failures often appear only in the child log, not the parent.

**Trace:** Identify the job type from the entry unit. In the parent log, `System.enqueueJob`, `Database.executeBatch` or a future call shows what was started. Connect parent and child only through a matching job Id or explicit logged identifier. In Batch, each `execute` chunk is its own transaction with its own limits; a failure in one chunk does not mean all chunks failed.

**Root vs symptom:** A child failure surfacing as a failed job in the UI is the symptom; the exception inside the child log is the cause. Repeated enqueues of the same class in one parent can cause duplicate processing or "too many queueable jobs".

**Smallest fix:** Address the child exception; guard against duplicate enqueues; size batch scope to the work per record.

**Cannot Verify:** whether two logs are parent and child, without a matching Id.

## 12. Successful but slow transactions

**Signature:** No exception; the user reports slowness.

**Trace:** Use the nanosecond clock to find where time went: total from `EXECUTION_STARTED` to `EXECUTION_FINISHED`, then the largest gaps. Common contributors visible in logs: callouts (request-to-response time), many Flow interviews or elements, re-entry, large query row counts. Compare the limit block values to their maximums.

**Root vs symptom:** If total time and usage are modest, say the log does not show a runtime problem; the slowness may be outside this transaction (page rendering, network, other transactions).

**Smallest fix:** Only for a specific evidenced hotspot. Otherwise none.

**Cannot Verify:** client-side or network time, which a debug log does not record.
