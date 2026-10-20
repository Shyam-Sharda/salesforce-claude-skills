# Apex Review Checklists by Code Type

Apply **General** to everything, then the sections matching the code types supplied. These are prompts for what to look at, not a list of findings to report. Report only what the code actually shows.

## Contents
- General (all Apex)
- Triggers and trigger handlers
- Queueable Apex
- Batch Apex
- Schedulable Apex
- Apex REST services
- @AuraEnabled controllers
- Service classes and helpers
- Testing

---

## General (all Apex)

**Bulkification and limits**
- SOQL, DML, callouts, `System.enqueueJob`, `@future` calls, or `Messaging.sendEmail` inside a loop. Trace through helper methods called from loops, since the query often hides one call down.
- Key per-transaction limits: SOQL queries (100 sync / 200 async), DML statements (150), rows returned by SOQL (50,000), DML rows (10,000), CPU time (10 s sync / 60 s async), heap (6 MB sync / 12 MB async), callouts (100). Check current Salesforce documentation if exact figures matter to a finding.
- When stating an exact governor-limit count, count operations for the specific execution path being reviewed. Do not combine separate independently invoked methods into one transaction unless the supplied code shows that they are called together.
- Nested loops over two lists (O(n²) CPU). A `Map<Id, SObject>` or `Map<Id, List<SObject>>` is the usual fix.
- DML on records that did not change. Compare old and new values before adding to the update list.

**Query efficiency**
- Filter selectivity: formula fields, negative operators (`!=`, `NOT IN`), and leading-wildcard `LIKE` can make selective index usage more difficult. Whether that is a practical problem depends on data volume, field indexing, and query selectivity, which are usually **Cannot Verify** items. Consider expressing the desired values positively when practical.
- Selecting only needed fields; `LIMIT` where a bounded result is expected; `FOR` loop (`for (Account a : [SELECT ...])`) for large result sets to manage heap.
- Aggregate queries instead of querying rows just to count or sum.

**Null handling**
- `[SELECT ...][0]` or `.get(0)` without a size check.
- `Map.get()` returning null and being dereferenced immediately.
- Relationship traversal (`a.Owner.Manager.Name`) without null checks; consider safe navigation (`?.`).
- Arithmetic or unboxing on null `Integer`, `Decimal`, `Boolean`, or `Date`.

**Exception handling**
- Empty `catch` blocks, or `catch (Exception e)` that swallows errors and lets processing continue as if it succeeded.
- `Database.insert/update(records, false)` without inspecting `SaveResult` entries, which causes silent partial failure.
- DML or callout wrapped in a try/catch inside a loop, hiding per-record errors with no reporting.
- Callout made after uncommitted DML in the same transaction (this throws). Note that `System.LimitException` cannot be caught.
- Exceptions rethrown with context lost, or internal details exposed to end users.

**Sharing and security**
- Missing sharing declaration. Behavior then depends on the calling context, so the intent is unclear. Prefer an explicit `with sharing`, `without sharing`, or `inherited sharing`.
- `with sharing` enforces record visibility only. It does **not** enforce CRUD or FLS.
- CRUD/FLS enforcement mechanisms to look for: `WITH USER_MODE` or `WITH SECURITY_ENFORCED` in SOQL, `AccessLevel.USER_MODE` on `Database` methods, `Security.stripInaccessible`, and `Schema` describe checks. Their absence in code that serves user-facing callers is a finding. Their absence in clearly system-level automation may be intentional.
- Do not treat `@AuraEnabled` or Apex REST exposure as authorization by itself. For operations involving sensitive actions or elevated system-mode access, inspect whether the code verifies that the caller is authorized to perform the business operation, not merely whether they can invoke the Apex class. "Can this user execute this class?" and "Should this user be allowed to perform this particular action?" (approve a refund, dispatch a technician, cancel a work order, change customer ownership) are different questions. Whether class access is configured is **Cannot Verify**; whether the code checks the business-level authorization is visible and reviewable.
- Dynamic SOQL (`Database.query`) built by concatenating strings. Prefer bind variables (`Database.queryWithBinds`, or binds in static SOQL). Where an identifier (field or object name) must be dynamic, validate against an allow-list or `Schema` describe. `String.escapeSingleQuotes` is a last resort for string values, not a replacement for binds.
- Hardcoded record IDs or org-specific configuration values. Prefer stable identifiers, Custom Metadata, Custom Settings, or other configuration mechanisms where appropriate.
- Logic that checks Profile names or other user labels for authorization is brittle. Prefer Custom Permissions or another explicit permission-based mechanism when the intent is to determine whether a user is allowed to perform an action.

**Maintainability**
- Methods or classes doing multiple unrelated jobs; deep nesting; very long methods that hide bugs.
- Magic strings and numbers that repeat and could drift apart.
- Misleading names, such as a method called `getX` that performs DML.
- Dead code or unused parameters, only if they create confusion.

---

## Triggers and trigger handlers

- Handles the full collection (`Trigger.new` / `Trigger.old`), not just `Trigger.new[0]`.
- Correct context: same-record field changes belong in **before** triggers (no DML needed); `Trigger.new` is read-only in **after** triggers. `addError` is typically used in before contexts and on `Trigger.new`/`Trigger.old` records.
- Uses `Trigger.oldMap` to detect real field changes before doing work.
- Handles all contexts the trigger declares (`before/after insert/update/delete/undelete`). In delete contexts, `Trigger.new` is null.
- Recursion: DML on the same object from an after trigger can re-fire the trigger. A static Boolean "already ran" flag is a known pitfall because it skips later 200-record chunks of the same transaction. A static `Set<Id>` of processed IDs is safer.
- Logic placed directly in the trigger body versus delegated to a handler. Flag only when it hurts testability or readability.
- Multiple triggers on the same object have no guaranteed order. If only one trigger is supplied, whether others exist is **Cannot Verify**.
- Mixed DML (setup objects such as `User` with non-setup objects in one transaction).
- Interaction with Flows, workflow, or other automation on the same object is **Cannot Verify** unless visible.

## Queueable Apex

- Uses `Database.AllowsCallouts` if it makes callouts.
- Only one child job can be enqueued from `execute`. Chains need a terminating condition to avoid runaway chaining.
- Enqueuing in a loop (limit is 50 jobs per synchronous transaction).
- Constructor captures an `SObject` snapshot versus IDs: data may be stale by execution time. Consider re-querying by ID when freshness matters.
- Member variables must be serializable.
- Failure observability: when the business process requires failed async work to be detected, logged, retried, or surfaced, review whether an appropriate mechanism exists. `System.Finalizer` is one possible approach for Queueable work, but do not recommend it automatically for every Queueable.
- Enqueued from a trigger without a guard against repeated enqueuing.

## Batch Apex

- `start` returns `Database.QueryLocator` for large sets (up to 50 million rows) or an `Iterable` (normal query-row limits apply).
- `Database.Stateful` used only if state truly must persist across `execute` calls; it adds serialization cost. Missing when instance variables are expected to accumulate across batches is a bug.
- `execute` is bulk-safe within one scope; no SOQL or DML in loops.
- `Database.AllowsCallouts` if callouts occur; scope size chosen with callout and CPU limits in mind.
- Partial failure handling: `Database.update(scope, false)` with result inspection and error logging, versus one failure rolling back the whole scope.
- `finish` does something useful (notification, chaining, error summary) or is intentionally empty.
- Sharing declaration present, since batch jobs run in system context.

## Schedulable Apex

- `execute` should be thin and delegate to Batch or Queueable. Heavy logic or callouts directly in `execute` are problems (callouts are not allowed directly).
- Cron expression hardcoded or scheduling logic that self-reschedules without a safeguard. Org limit is 100 scheduled jobs; current usage is **Cannot Verify**.
- Sharing declaration present; scheduled jobs run in system context.
- Handling of overlapping runs if a prior job may still be running.

## Apex REST services

- `@RestResource` URL mapping and HTTP method annotations are correct and unambiguous.
- Apex REST runs in system mode: CRUD/FLS are not enforced automatically, and record sharing follows the class declaration. Check both.
- Request body validated and null-checked; deserialization into typed wrappers preferred over untyped maps when structure is known; malformed JSON handled.
- Accepts and handles lists, not just a single record, where callers may batch.
- Meaningful HTTP status codes set via `RestContext.response`; internal exception messages not leaked to the caller.
- Returns raw SObjects (all fields) versus a purpose-built response wrapper. Raw SObjects can expose more than intended.
- Idempotency for POST/PUT: retries creating duplicates; consider upsert with an external ID.
- Who is allowed to call the endpoint (Apex class access via profile/permission set, connected app scopes, guest access) is **Cannot Verify**.

## @AuraEnabled controllers

- Runs in system mode by default. Check sharing declaration and CRUD/FLS enforcement for both reads and writes.
- `cacheable=true` methods must not perform DML and may return stale data; methods that modify data must not be cacheable.
- Client-supplied record IDs, field names, object names, or filter strings are untrusted. Validate, bind, or allow-list them. Check that the user can actually access a supplied ID's record.
- Errors surfaced via `AuraHandledException` with a safe message (and `setMessage` where the default message would be unhelpful), not raw exceptions or stack details.
- Returns DTO wrappers or only required fields rather than full SObjects with everything.
- Imperative methods that can return large result sets: need `LIMIT` or pagination.
- Methods that can be called with a list or collection from the client: bulk-safe handling.
- Which users can call the method (class access via profile/permission set) is **Cannot Verify**.

## Service classes and helpers

- Single clear responsibility; public methods express intent; a "Utils" class that has become a dumping ground is a maintainability concern only if it causes real confusion.
- Explicit sharing declaration; `inherited sharing` is often appropriate for reusable service code called from varied contexts.
- Hidden SOQL/DML in methods that callers might reasonably invoke inside a loop. Prefer methods that accept collections.
- Errors returned or thrown clearly rather than swallowed.
- Testability: dependencies hard-wired in ways that block unit testing (for example, direct callouts with no mock seam) is a Warning or Improvement depending on severity.

---

## Testing

When reviewing existing tests or recommending scenarios:

- **Bulk:** for triggers and entry points designed to process collections, include realistic bulk tests. For trigger recursion or chunking concerns, testing more than 200 records (for example, 201) can expose logic that incorrectly relies on transaction-wide static state. Do not require artificial bulk tests for single-record APIs that are intentionally designed around one record.
- **Assertions:** `Assert.areEqual` / `System.assertEquals` with meaningful expected values, not tests that merely execute code for coverage.
- **Negative and boundary paths:** invalid input, nulls, empty collections, exception handling, validation failures.
- **Data setup:** `@TestSetup` or a test data factory; avoid `@SeeAllData=true` unless genuinely required.
- **Async:** Queueable, Batch, Schedulable, and `@future` code only executes at `Test.stopTest()`; assertions should come after it.
- **Callouts:** `Test.setMock` with `HttpCalloutMock`; no real callouts.
- **Security:** use `System.runAs` where different user context or record-sharing behavior matters. When testing CRUD/FLS enforcement, verify the behavior of the actual enforcement mechanism used by the production code, such as user-mode operations, `WITH USER_MODE`, `WITH SECURITY_ENFORCED`, `Security.stripInaccessible`, or explicit describe checks. Do not assume that `System.runAs` alone proves CRUD/FLS enforcement.
- **Entry-point-specific:** REST via `RestContext` request/response setup; `@AuraEnabled` success and `AuraHandledException` paths; triggers across insert, update, delete, undelete contexts as declared.
- Whether any tests exist, and what they cover, is **Cannot Verify** unless the test class is supplied.
