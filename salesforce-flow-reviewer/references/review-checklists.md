# Flow Review Checklists

These are prompts for what to look at, not a list of findings to report. Report only what the metadata shows. Apply **Platform facts**, **Architecture**, **Bulkification**, **Database operations**, **Decisions and logic**, **Error handling**, **Security**, **Maintainability**, and **Testing** to every Flow; apply **Record-triggered**, **Scheduled**, and **Screen** sections when they fit.

## Contents
- Platform facts to reason with
- Purpose and architecture
- Bulkification and governor limits
- Record-triggered Flow design
- Scheduled-triggered Flows and scheduled paths
- Database operations
- Decisions and logic
- Error handling and reliability
- Screen Flows
- Security
- Maintainability
- Flow versus Apex
- Testing

---

## Platform facts to reason with

State these only where they bear on a finding. If an exact figure matters to the conclusion, say it should be checked against current Salesforce documentation.

- Flows share the transaction's governor limits with Apex and other automation: SOQL queries (100 synchronous / 200 asynchronous), DML statements (150), records retrieved by SOQL (50,000), records processed by DML (10,000), CPU time (10 s synchronous / 60 s asynchronous).
- Record-triggered Flows process records in chunks of up to 200 per transaction. Flow interviews for those records that reach the **same element** are bulkified together: a Get Records or Update Records on the main path runs as one query or one DML for the whole chunk. Inside a Loop element, each iteration executes the element separately, so the cost of a database element in a loop scales **per iteration** rather than once for the chunk. Exact transaction-wide totals depend on how interviews are grouped when they reach the element (see Bulkification and governor limits).
- Before-save record-triggered Flows can change fields on the triggering
  `$Record` without issuing another DML statement. Use Assignment to modify
  `$Record`; Salesforce applies those values when the original record is saved.

- Before-save Flows support the limited set of operations intended for fast
  field updates, including Assignment, Decision, Get Records, and Loop.
  Custom Error can also be used on before-save and after-save record-triggered
  paths to block the triggering change with a targeted error message.

- Before-save Flows cannot perform related-record DML or invoke the broader
  action/subflow capabilities available after save. Use an after-save Flow when
  related records, actions, email, or external operations are required.
- After-save Flows are needed for related-record DML, actions, emails, and anything needing the new record's Id. An after-save Update Records on `$Record` issues an extra DML on the triggering record and sends it through the save order again (triggers, validation rules, and record-triggered Flows on that object can run again).
- Callouts can't be made in a transaction with uncommitted work. In a record-triggered Flow, callouts belong on the "Run Asynchronously" path (`AsyncAfterCommit`) or a scheduled path, not the immediate path. In Screen and autolaunched Flows, an external-service or callout action that runs after a Create/Update/Delete (or an Apex action that may do DML) in the same transaction, with no screen in between, typically fails with an uncommitted-work error. Some actions expose `<flowTransactionModel>` (for example `CurrentTransaction` vs `NewTransaction`), which changes this; note it when present.
- Scheduled paths and Pause/Wait resumptions run in a separate later transaction.
- Screen Flows: work between two screens runs in one transaction; displaying a screen commits pending changes. Roll Back Records only rolls back changes in the current transaction.
- **Execution context:** determine context from the Flow type, `runInMode`,
  API version, and launch method when those are visible.

  - Record-triggered and schedule-triggered Flows run in system context
    without sharing by default.
  - Screen and autolaunched Flows in default mode can run in user or system
    context depending on how they are launched and the context of their caller.
  - Many direct UI launch methods run Screen Flows in user context, but do not
    assume this when the launch mechanism is not supplied.
  - `SystemModeWithSharing` bypasses object permissions and field-level
    security while respecting record sharing.
  - `SystemModeWithoutSharing` bypasses object permissions, field-level
    security, and record sharing.
  - API version 68.0 and later supports an explicit
    "User Context–Enforces User Permissions" option for Screen and
    Autolaunched Flows, which prevents elevation inherited from a
    system-context caller.
  - If effective context depends on an unseen caller or launch mechanism,
    use **Cannot Verify**.

## Purpose and architecture

- Flow type and start configuration: triggering object, trigger type (create/update/delete), before- vs after-save, entry criteria, schedule.
- Major branches and their outcomes; what each branch writes.
- Subflows, Apex actions, external service actions, and AI actions (`generatePromptResponse`, Agentforce-related action types): what is visible about their inputs and outputs, and what is not.
- Synchronous vs asynchronous paths (immediate, Run Asynchronously, scheduled paths, Waits).
- Scope: does the Flow do one coherent job, or several unrelated jobs that will be hard to change independently? Only raise this when it causes a concrete problem (unrelated entry criteria forced together, branches that fight over the same field).

## Bulkification and governor limits

- Get Records, Create Records, Update Records, Delete Records inside a loop body. Typical fix: query once before the loop (the `In` operator on a collection of Ids works for this), match in memory, collect records to change with an Assignment (`Add`), and do one Create/Update/Delete after the loop.
- Apex actions or subflows inside a loop. The Flow invokes them once per loop iteration rather than once for the whole collection. Whether the action or subflow itself performs SOQL/DML is **Cannot Verify** unless its implementation is supplied. If it is supplied, look inside.
- For Apex actions inside loops, describe what the Flow passes and how often the Flow invokes the action. Do not make assumptions about the Apex method's internal batching, implementation, or governor usage unless the Apex code is supplied.
- Callouts, emails, Prompt or AI actions, or other expensive actions inside a loop.
- The same Get Records repeated on several branches or between screens when one query would do.
- Loops whose only purpose is to build a collection that a Collection Filter, a Get Records filter, or a Transform could produce directly (Improvement, not a defect).
- Nested loops over two collections (CPU cost grows with the product of their sizes).
- For record-triggered Flows: reason about a 200-record chunk. A per-iteration query inside a loop over each record's related list can multiply across interviews.
- Be cautious when giving exact governor-limit arithmetic for record-triggered Flows. Salesforce can bulkify database elements across Flow interviews that reach the same element. Database elements inside a Loop still execute per iteration, but transaction-wide counts can depend on how interviews are grouped and reach the element.
- Use exact counts only when the metadata and execution shape make them deterministic. Otherwise describe the scaling pattern (for example, "one query per loop iteration") rather than claiming an exact transaction total.
- Distinguish a loop over a small fixed or naturally bounded collection (a handful of picklist values, a few child records by design) from one over an unbounded query result. Say which it is; if the size is unknown, that is **Cannot Verify**.

## Record-triggered Flow design

- Before-save vs after-save: if the Flow only sets fields on the triggering record, before-save is the efficient choice. An after-save Flow whose only DML is updating `$Record` is a candidate to move.
- Updates to `$Record` in after-save: extra DML and the record re-enters the save order. Check whether entry criteria prevent the Flow from re-running on its own update (`doesRequireRecordChangedToMeetCriteria`, or `IsChanged`/`$Record__Prior` conditions, or criteria the update itself makes false). If the Flow's own update keeps the record meeting the criteria, there is real re-entry risk.
- Updates to other records of the same object (for example a parent Account updating child Accounts): same re-entry question.
- Entry criteria breadth: an update-triggered Flow with no criteria, or without "only when updated to meet the criteria", runs on every save of every record. That is a performance and recursion concern, not automatically a defect; judge from what the Flow does.
- Criteria that check a field's value but not whether it changed, when the logic clearly means "when it becomes X".
- Delete-triggered Flows: what is still available on `$Record`, and whether related data is handled.
- Interaction with other automation: only discuss automation that was supplied. Otherwise, at most a single **Cannot Verify** line when the Flow's correctness genuinely depends on it (for example, it relies on a field being set before it runs).
- Callouts or long-running actions on the immediate path (should be on Run Asynchronously or a scheduled path).
- Custom Error usage: a before- or after-save Flow that needs to block a save should use Custom Error rather than letting an element fail.

## Scheduled-triggered Flows and scheduled paths

- Start filters: a schedule-triggered Flow with an object and no filters runs over every record of that object.
- Get Records inside a scheduled Flow that runs per record is bulkified across the batch like a record-triggered Flow; inside a loop it isn't.
- Scheduled paths: does the path re-check that the record still qualifies? Records may have changed between the trigger and the scheduled time.
- Salesforce limits how many schedule-triggered and scheduled-path interviews run per 24 hours; mention this only when the design clearly depends on very high volume, and say the exact figure should be checked in current documentation.

## Database operations

- Get Records filters that match more records than the logic needs, or a "first record only" query without a sort where the result is ambiguous (which record is first is not guaranteed).
- `<queriedFields>` listing fields never referenced (minor Improvement), or logic referencing fields that are not queried when fields are chosen manually (likely a defect: the value will be empty).
- No-record handling: after a Get Records, does the Flow check for null/empty before using the result? Failure modes: Update Records on a null variable fails; an action receives a null Id; a Decision treats a missing record as a real one; a loop over an empty collection is harmless.
- Create/Update/Delete on a collection: one failing record can fail the whole operation (and in a record-triggered Flow, the whole save). Note partial-failure behavior where it matters.
- Update Records using filter criteria (`object` + `filters`) that could match many more records than intended, especially when a filter value can be null.
- Duplicate operations: the same record updated twice in one path, or created on every run with no check for an existing record when the logic clearly expects one.

## Decisions and logic

- Outcomes evaluated in order with overlapping conditions, where an earlier outcome makes a later one unreachable.
- Missing outcome for a value the Flow clearly handles elsewhere, or a default outcome that silently treats unexpected values as a specific business case.
- Conditions on fields that may be null (`EqualTo` on a null field, numeric comparisons with null).
- Custom condition logic that references the wrong condition numbers, or AND/OR combinations that don't match the outcome label.
- Text comparisons on picklist values or labels that would break with a label change or translation (compare API values).
- The same decision repeated in several places (Improvement if it creates real drift risk).
- Formulas that are hard to read or fragile (deeply nested IFs, hardcoded IDs, division without a zero check).

## Error handling and reliability

- Fault-capable elements without fault connectors. Decide whether it matters:
  - Record-triggered: an unhandled failure fails the save and rolls back the transaction, showing the user an error that is often unhelpful. Sometimes that's the right outcome (the save shouldn't succeed). A Custom Error with a clear message is better when blocking is intended.
  - Screen Flows: an unhandled failure shows a generic error. A fault path to a screen with a clear message is usually worth it on user-facing database operations and actions.
  - Autolaunched or invoked: failure propagates to the caller; whether that is right depends on the caller (often **Cannot Verify**).
  - Scheduled or async paths: no user sees the failure. Whether it's noticed depends on org error-email settings, which aren't visible.
- Fault paths that swallow errors: a fault connector that ends the Flow or continues the main path without recording or surfacing anything. In a record-triggered after-save Flow this means the save succeeds while the related work silently did not happen: a data integrity concern.
- Fault paths that lose context: logging without `{!$Flow.FaultMessage}`, the element that failed, or the record involved.
- Fault paths that themselves perform DML with no fault handling of their own (a failing error log masks the original error).
- Apex action and subflow failures, callout failures, AI action failures: is there a fallback or a meaningful message?
- Waits/Pauses that never resume if the event never happens.

## Screen Flows

- Required inputs marked required; validation (`<validationRule>`) on inputs that feed record operations; values validated before DML rather than relying on the save to fail.
- Navigation: Back after a DML screen can lead users to resubmit and create duplicates. Note only when the path shows it.
- Error messages: fault paths that show users something actionable.
- Repeated queries between screens for data already held in variables.
- Exposure: screens or output variables that show or return fields the user may not otherwise see, especially in system mode.
- Unnecessary screens: only when they cause a concrete problem (a confirmation screen before a destructive action is a reasonable choice, not a defect).
- UX preferences (wording, field order, number of screens) are not defects. Raise as a question only if there's a reason.

## Security

Treat each layer separately and say which one a concern belongs to.

- **Execution context**: `runInMode` and Flow type (see Platform facts). System mode is not automatically a vulnerability; it matters when the Flow is reachable by users or external callers and reads or changes data based on their input.
- **Record-level access**: in system mode without sharing, the Flow can read or change records the user can't see. Look at where record Ids come from: an input variable (`recordId`), a screen field, or the triggering record.
- **Object permissions and field-level security**: bypassed in system mode; enforced for the running user in user context. Whether the user actually has them is **Cannot Verify** (profiles and permission sets aren't in the Flow).
- **Business-level authorization**: "can this user run the Flow" is configuration (**Cannot Verify**); "should this user be allowed to do this action" can sometimes be checked in the Flow itself (a Decision on `$Permission`, ownership, status). For sensitive actions in elevated context (approving, cancelling, changing ownership, deleting), look for such a check.
- **Flow access**: which profiles or permission sets can run the Flow, and whether it is exposed to Experience Cloud or guest users, isn't in the Flow XML. Only make claims about external or guest access if the related metadata is supplied; otherwise a **Cannot Verify** line when it matters.
- **Apex actions**: don't call the Apex secure or insecure unless its implementation is supplied. Note what the Flow passes into it (for example, user-supplied Ids) and mark the rest **Cannot Verify**.
- **Data returned**: output variables and screen components that expose data back to the caller or user.
- Hardcoded IDs and Profile-name checks used for authorization are brittle; Custom Permissions (`$Permission`) express the intent better.

## Maintainability

- Element API names that hide what the element does (`Get_Records_1`, `Decision_3`) when the Flow is large enough that it matters. A short Flow with default names is a minor Improvement at most.
- Descriptions on complex Decisions, formulas, and any non-obvious design choice.
- Very large or deeply branched Flows where branches duplicate logic; suggest a Subflow only when it removes real duplication or enables real reuse.
- Subflows that add a layer of indirection with no reuse.
- Dead elements: elements not reachable from the start, unused variables or formulas (only when they create confusion).
- Hardcoded Ids (record types, users, queues, groups) and environment-specific values: they differ between sandboxes and production. Fix: query by `DeveloperName`, or use Custom Metadata, Custom Labels, or Custom Settings as appropriate.
- Long chains of Assignments or nested formulas that make intent hard to follow.

## Flow versus Apex

Only raise when there is something concrete to say.

- A portion may be better as Apex when: transactional logic is complex (multi-object with careful rollback), the logic is genuinely hard to bulkify declaratively (per-record queries that need maps), substantial computation is reused across several automations, error handling needs more control than fault paths give, or Flow can't express it cleanly.
- Complexity alone isn't a reason. Many complex Flows are fine.
- The reverse also applies: an Apex action that only does what a standard Flow element can do (a single query, a field assignment, sending a standard email) may be unnecessary. Say so only if the Apex is supplied or its purpose is evident from its name and inputs, and frame it as **Cannot Verify** if you can't see the body.

## Testing

Name concrete scenarios for this Flow:

- The expected path with realistic data.
- Each alternate Decision outcome, including the default.
- No-record results from each Get Records whose result is used.
- Bulk: for record-triggered Flows, insert or update a full chunk (200 records) in one transaction, ideally with related records that exercise any loops.
- Re-entry: update a record so the Flow's own update fires again.
- Fault paths: force a failure (a validation error, a missing required field, an Apex action that throws) and confirm the fault path does what it should.
- Permissions: run as a user without access when the Flow runs in user context or relies on an authorization check.
- Async and scheduled paths: confirm they still behave when the record changes before they run.

Flow tests (`*.flowtest-meta.xml`) and Apex tests that perform DML can both exercise Flows. If supplied, review what they assert. Don't comment on coverage percentages.
