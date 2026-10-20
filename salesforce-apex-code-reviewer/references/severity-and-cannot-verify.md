# Severity Calibration and Cannot Verify Guide

Use this when deciding how serious a finding is and when something belongs under **Cannot Verify** instead of being reported as a defect.

In the response, Critical findings go under **Urgent - Needs Attention**, Warnings under **Warning - Should Change**, and Improvements under **Suggested Changes**. The calibration below decides the level; the heading only presents it.

## Contents
- Severity calibration
- What changes severity
- Cannot Verify: common unknowns
- Phrasing examples
- Clean review examples

---

## Severity calibration

**Typically Critical**
- SOQL or DML (or a helper that does either) inside a loop over records that can be 200 or more (trigger, batch scope, list input).
- Trigger logic that only processes `Trigger.new[0]`, or a static Boolean recursion flag that skips later chunks.
- Dynamic SOQL concatenating externally supplied input in a method reachable by users or external systems.
- `Database.insert/update(records, false)` with results ignored, where failures cause silent data loss or inconsistency.
- Unguarded `[SELECT ...][0]` on a path where the query can plausibly return no rows.
- Unbounded self-chaining Queueable or self-rescheduling Schedulable with no stop condition.
- Externally reachable method (`@AuraEnabled`, REST, `@InvocableMethod` called by users) that visibly returns or modifies data with no sharing or CRUD/FLS consideration, where the code makes the exposure clear.

**Typically Warning**
- No sharing declaration on a class that queries or modifies data.
- CRUD/FLS not enforced in code that serves user-facing callers, when the actual exposure depends on things you cannot see.
- `catch (Exception e)` that logs and continues, or an empty catch where the failure is non-critical.
- Hardcoded record IDs or org-specific configuration values.
- Profile-name or Profile-ID checks used as an authorization decision (a Custom Permission or other explicit permission mechanism better expresses the intent). Raise to Critical only if the code shows this guarding a sensitive action in a way that is clearly bypassable or wrong.
- Queries that look non-selective but whose object size is unknown.
- Callout directly in a Schedulable, or in a path with a plausible but unconfirmed ordering problem with DML.
- Large method doing several jobs where it already hides a bug risk.

**Typically Improvement**
- Moving trigger body logic into a handler, when the logic is simple.
- Replacing repeated magic strings with constants or Custom Metadata.
- Selecting unneeded fields on a small, bounded query.
- Splitting a long method, renaming misleading identifiers, or removing dead code.
- Adding `Finalizer` or logging for observability on an otherwise correct async job.

## Note on `without sharing`

A `without sharing` declaration is not automatically a vulnerability. Classify it based on what the class exposes and whether system-level record access is necessary for the business operation.

If `without sharing` is deliberate and the externally reachable methods enforce authorization and data-access boundaries appropriately, it may not be a finding at all. This is common in Experience Cloud applications, where a controller may need to read or update records the guest or community user cannot see directly, and then restricts what it returns or changes in code. In that case, review the authorization and data-access checks rather than flagging the keyword itself.

Escalate when the code shows `without sharing` combined with externally reachable methods that accept client-supplied IDs or filters and return or modify records without any visible check that the caller may access them.

## What changes severity

Raise severity when:
- The code is externally reachable (REST, `@AuraEnabled`, `global`, public API surface).
- The affected path is a trigger or other high-volume entry point.
- The consequence is data loss, data exposure, or an unrecoverable failure (limit exceptions cannot be caught).
- The code itself shows the exposure rather than leaving it hypothetical.

Lower severity when:
- The loop is over a small fixed collection (for example, a constant list of three record types), and say so.
- The class is clearly an internal system-level job and the sharing choice is evidently deliberate.
- The concern depends on org configuration the code does not reveal. Convert it to **Cannot Verify** rather than guessing.

Always state the reasoning in one sentence so the author can disagree intelligently.

## Cannot Verify: common unknowns

These are normally **not visible** in Apex files alone. Do not assert them either way:

- Profile or permission set access (object CRUD, field FLS, Apex class access, custom permissions)
- Sharing rules, OWDs, role hierarchy, and whether a record will be visible to a given user
- Whether a field, object, record type, or picklist value referenced in code exists or is writable
- Required fields, validation rules, duplicate rules, lookup filters
- Other triggers, Flows, workflow, or process automation on the same objects, and their order or recursion interaction
- Data volumes, index status, and whether a query is actually selective
- Existing test coverage or tests not supplied
- Org limits in use (scheduled jobs, flex queue, async Apex executions)
- API version of the class and behavior that depends on it
- Who can reach an endpoint (connected app scopes, guest or Experience Cloud access, user-assigned permission sets)
- Contents of called classes, managed-package code, or custom metadata/settings that were not supplied

## Phrasing examples

Good (conditional and honest):

> **Cannot Verify**: whether running users have read access to `Contract_Value__c`. Profiles and permission sets are not in the supplied files. The query in `getContracts` does not enforce FLS itself, so access depends entirely on that configuration; adding `WITH USER_MODE` would remove the dependency.

> **Cannot Verify**: whether other automation on `Opportunity` (Flows, other triggers) updates `Opportunity` after this trigger runs. If one does, the static Boolean in `OpportunityTriggerHandler` could suppress a legitimate second pass.

Bad (asserts unseen facts):

> "The `Region__c` field does not exist on Account." *(metadata is not supplied)*
> "Sales users have no access to this class." *(permission sets are not supplied)*
> "This query will time out on large orgs." *(volume and indexes are not known)*

Better version of the last one:

> The query filters on `Status__c` using a negative operator such as `!=`, which can make selective index usage more difficult.
>
> **Cannot Verify**: whether the object's data volume, field indexing, and query selectivity make this a practical performance problem. Consider expressing the desired values positively when practical and verify the query plan for large-data-volume objects.

## Clean review examples

A clean review is a valid outcome. Short, specific, and still useful:

```
## What This Code Does

`CaseStatusService` closes Cases whose open Tasks are all complete; it is called
from the Task trigger handler. Sharing and access look sound: the class is
`with sharing`, SOQL uses `WITH USER_MODE`, and there is no dynamic SOQL.

## Urgent - Needs Attention

No urgent issues identified.

## Warning - Should Change

No warnings identified.

## Suggested Changes

**1. Repeated status literal**

**Change:** The `'Closed'` status string appears in three methods.

**Fix:** Move it to a constant to prevent the values from drifting.

## Cannot Verify

- **Cannot Verify:** Apex class access for end users, which is configured outside these files.

Would you like me to update and recreate this Apex class with these changes?
```

Do not pad a clean review with generic advice such as "consider adding more comments" or "consider adding logging" unless there is a specific, explained reason.
