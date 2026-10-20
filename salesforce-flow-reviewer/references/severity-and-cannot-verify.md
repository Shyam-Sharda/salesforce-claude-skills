# Severity Calibration and Cannot Verify Guide

Use this when deciding how serious a finding is, and when something belongs under **Cannot Verify** instead of being reported as a defect.

In the response, Critical findings go under **Urgent - Needs Attention**, Warnings under **Warning - Should Change**, and Improvements under **Suggested Changes**. The calibration below decides the level; the heading only presents it.

## Contents
- Severity calibration
- What changes severity
- Cannot Verify: common unknowns
- Phrasing examples
- Clean review example

---

## Severity calibration

**Typically Critical** (when the metadata shows the path)
- Get, Create, Update, or Delete Records inside a loop over a collection that can be large: a query result, a related list, or the records of a record-triggered or scheduled batch.
- An after-save Flow that updates `$Record` (or records of the same object) with entry criteria that remain true after its own update, so it can re-trigger itself.
- A callout or callout-making action on the immediate path of a
  record-triggered Flow when it executes in the current transaction and the
  save has uncommitted work. This is typically a failure path.

  Do not classify it automatically if the supplied metadata shows that the
  action executes in a separate transaction or asynchronous path. Check
  `flowTransactionModel`, async/scheduled paths, and surrounding transaction
  boundaries when visible.
- An Update or Delete Records using filter criteria where a filter value can be null or empty, so the operation can hit far more records than intended.
- A fault path in an after-save or autolaunched Flow that ends silently after a failed operation the business clearly relies on (record saves, related work silently missing).
- A Flow running in `SystemModeWithoutSharing` that accepts a record Id or other input from the user and reads or changes that record with no visible authorization check, where the Flow's purpose shows it is user-facing.
- Logic that is visibly wrong: an unreachable outcome that the Flow's purpose depends on, a condition that can never be true, an Update on a variable that is never populated.

**Typically Warning**
- Apex action or subflow inside a loop where its implementation isn't supplied (pair with **Cannot Verify** about what it does internally).
- No null check after a Get Records whose result is used, where a missing record is plausible.
- Missing fault path on a user-facing database operation or action in a Screen Flow.
- Update-triggered Flow without "only when updated to meet the criteria" or `IsChanged` logic, where the work done is non-trivial.
- After-save Flow whose only DML is updating `$Record` fields (move to before-save) without visible re-entry risk.
- Hardcoded record type, user, queue, or group Ids.
- Profile-name checks used for authorization.
- "First record only" Get Records with no sort when several records can match and the choice matters.
- Fault paths that log without `$Flow.FaultMessage` or record context.

**Typically Improvement**
- Default element names (`Decision_1`) in a Flow large enough that they slow down understanding.
- Missing descriptions on complex Decisions or formulas.
- Unused variables, formulas, or disconnected elements that cause confusion.
- A loop that a Collection Filter, Get Records filter, or Transform could replace.
- Querying fields that are never used.
- Duplicated logic that could drift (only with a concrete reuse or drift argument).

## What changes severity

Raise severity when:
- The element is in a record-triggered or scheduled Flow (high volume by nature).
- The loop is over an unbounded query result or a related list.
- The consequence is silent data loss or inconsistency, or an exposure of records to users who shouldn't see them.
- The Flow is reachable by users or external callers and runs in system mode.

Lower severity when:
- The loop is over a small, fixed or clearly bounded collection; say so.
- The Flow is a Screen Flow handling one record at a time, so a per-iteration query over a short list is unlikely to approach limits.
- The concern depends on org configuration or code not supplied; convert it to **Cannot Verify**.

State the reasoning in one sentence.

## Cannot Verify: common unknowns

These are normally not visible in Flow XML alone. Don't assert them either way:

- What an Apex action, invocable method, Apex plug-in, or subflow does internally (SOQL, DML, callouts, sharing, CRUD/FLS).
- What an external service, Prompt Builder template, or Agentforce action does, returns, or how it fails.
- Whether objects, fields, record types, picklist values, queues, or Ids referenced in the Flow exist in the target org.
- Profiles, permission sets, flow access settings, Experience Cloud or guest exposure.
- Sharing settings, OWDs, role hierarchy.
- Validation rules, duplicate rules, required fields that might make an operation fail.
- Other Flows, Apex triggers, Process Builder, Workflow Rules on the same object, and their ordering.
- Record volumes and how many records a query or loop will actually handle.
- How an autolaunched Flow is launched, and therefore its effective context in `DefaultMode`.
- Existing Flow tests or Apex tests that weren't supplied.

## Phrasing examples

Good:

> **Cannot Verify**: what `CalculateDiscount` (Apex action, called inside `Loop_Lines`) does internally. The Flow invokes it once per line item, passing a single `OrderItem`; if it queries or performs DML per call, that cost scales with the number of lines. Supplying the class, or confirming it is pure computation, would settle this.

> **Cannot Verify**: which users can launch `Cancel_Work_Order`. Flow access is configured in profiles or permission sets, which weren't supplied. This matters because the Flow runs in system mode without sharing and acts on whatever `recordId` it receives.

Bad (asserts unseen facts):

> "The `Region__c` field doesn't exist on Account." *(object metadata not supplied)*
> "There's another Flow on Opportunity that will conflict." *(no other Flow supplied)*
> "This Apex action does a SOQL query per call." *(Apex not supplied)*
> "Inserting 200 Opportunities will use exactly 200 SOQL queries." *(transaction totals depend on how interviews reach the looped element; describe the per-iteration pattern instead)*
> "Guest users can run this Flow." *(site and access metadata not supplied)*

## Clean review example

A clean review is short and still useful:

```
## What This Flow Does

Before-save Flow on Case (create) that sets Priority from Origin. It has no loops,
no database elements, and no fault-capable elements, and only sets fields on
`$Record`, so it is bulk-safe and has no exposure concern.

## Urgent - Needs Attention

No urgent issues identified.

## Warning - Should Change

No warnings identified.

## Suggested Changes

**1. Undocumented priority rule**

**Change:** `Decision_1` gives Web cases Medium priority with no explanation.

**Fix:** Add a description to `Decision_1` stating why, so the next maintainer
does not "fix" it.

Would you like me to update and recreate this Flow metadata with these changes?
```

Don't pad a clean review with generic advice ("consider adding logging", "consider a Subflow") without a specific, explained reason.
