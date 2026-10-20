---
name: "salesforce-apex-test-generator"
description: "Analyzes Salesforce Apex production code and generates or improves meaningful Apex test classes that prove behavior (decision paths, bulk handling, failure paths, async outcomes, callouts, security) rather than chasing 75% coverage. Make sure to use this skill whenever the user supplies or points to Apex (class, trigger, handler, service, @AuraEnabled controller, Apex REST, Queueable, Batch, Schedulable, @future, Invocable, or callout code) and asks to write, generate, fix, extend, or improve a test class, add bulk, negative, async, callout, or security tests, write an HttpCalloutMock, raise or fix coverage, or just says 'test this', even if they never say 'test class'. Do not use for a general Apex code review with no request for tests, for Flow tests, or for LWC Jest tests."
---

# Salesforce Apex Test Generator

A good Apex test proves that the production code does what it is supposed to do, and would fail if that behavior broke. Salesforce requires 75% coverage to deploy, which pushes many teams toward tests that execute lines without checking anything. That is the failure mode this skill exists to avoid: a smaller suite whose every method asserts a real outcome is worth more than a large suite of coverage padding.

The second failure mode is invention. Tests run inside a real org with real validation rules, required fields, record types, flows and permissions. Code that references a field or record type the org does not have will not compile or will fail at runtime, and the developer then has to unpick what was guessed. So everything the tests depend on must be either visible in the supplied files or created by the test itself. Anything else is labelled **Cannot Verify**.

## Core principles

1. **Analyze before writing.** Understand what the code does and where it branches before producing any test code. The test plan is the plan; the test class implements it. Skip the analysis only when the user explicitly asks for only the code.
2. **Behavior over coverage.** Each test method asserts an observable outcome: a returned value, a field value read back from the database, records created or deleted, an expected exception and its message, an HTTP status, an async side effect. If a test cannot assert anything meaningful, question whether it should exist.
3. **Scenarios come from the code.** Every row of the test plan should trace to a branch, guard, loop, catch block, or contract visible in the supplied code. A clean 30-line service may need three tests. Do not pad the plan with edge cases the code cannot encounter.
4. **Evidence only.** Do not invent field API names, required fields, picklist values, record types, Custom Metadata records, users, queues, permission sets, or the response contract of an API whose code was not supplied. Mark them **Cannot Verify** and say what would settle it.
5. **Test through public entry points.** Assert on what callers can observe so a behavior-preserving refactor does not break the suite. Use `@TestVisible` members when the production code already exposes them and doing so is justified. Do not add `@TestVisible` to production code yourself. If meaningful behavior cannot be reached through a public entry point and a small seam (`@TestVisible`, dependency injection) would materially improve the design, propose it under Suggested Changes and let the user decide.
6. **Do not change production code silently.** This skill writes tests. If a branch is genuinely untestable as written (for example, a callout or `Datetime.now()` with no seam), say so, test what you can, and suggest the smallest production change that would make it testable. A dependency that exists but was not supplied (a called class, Custom Metadata records, object metadata) is a missing-file gap, not an architecture problem: ask for the files first, and propose a seam only if the dependency would still block deterministic testing once supplied. This order applies even where a reference file suggests a seam. Do not add `Test.isRunningTest()` branches to production code.
7. **Respect what exists.** Follow the project's naming, assertion style, and data-factory conventions when they are visible. Improve an existing test class rather than replacing it.

## Workflow

1. **Inventory.** List the supplied files and the type of each (trigger, handler, service, `@AuraEnabled` controller, REST resource, Queueable, Batch, Schedulable, `@future`, Invocable, callout class, existing test, data factory, metadata). Note classes or metadata that are referenced but not supplied. When a `.cls-meta.xml` (or `.trigger-meta.xml`) is supplied, record each production class's API version: security defaults differ materially between API 66.0 and earlier (system mode) and API 67.0 and later (user mode). If security behavior affects the test strategy and the API version is not supplied, mark the effective default access mode **Cannot Verify** rather than assuming either mode.
2. **Establish purpose.** 2 to 4 sentences on what the code does, who calls it, and what data it changes. If inferring, say so and proceed with the assumption.
3. **Find entry points.** Public/global methods, trigger contexts actually declared, `@AuraEnabled`, `@HttpGet/@HttpPost/...`, `@InvocableMethod`, `execute`/`start`/`finish`, `@future` methods. These are what the tests call.
4. **Trace paths.** For each entry point, follow the branches, guards, loops, early returns, and catch blocks across all supplied files, including helpers. Note which inputs drive each branch.
5. **Identify dependencies and data.** SObjects and fields read or written, records that must exist, referenced classes, Custom Metadata/Settings, record types, users and permissions, callouts, async work, platform events. Include every object the tests depend on, not only the ones the test inserts: an object that production code inserts or updates during the test and the test then queries back (a log, an audit record) is a dependency too. Read `references/test-data-and-dependencies.md` for what a test can and cannot create and how to handle each dependency.
6. **Identify platform concerns.** Bulk/collection handling, async execution, callouts, DML and SOQL patterns, exceptions, sharing and CRUD/FLS behavior (explicit mechanisms and the API-version default). A sharing declaration, user-mode operations, or the API-version default alone does not call for a security test. Plan one only when security is part of the supplied code's own contract (an explicit `stripInaccessible`, CRUD/FLS or Custom Permission check, deliberate access-mode switching, or an observable security branch), or when the user asks for security tests. Otherwise test the business behavior and stop; see "Do not generate security tests by default" in section 12 of the patterns reference. Read `references/test-patterns-by-apex-type.md` for the sections that match the code types in the inventory.
7. **Build the test plan** (format below).
8. **Decide on each unknown**: whether the test can proceed as written, proceed with a clearly marked placeholder, should be skipped, or blocks the class.
9. **Write or update the test class.**
10. **Report only the production and testability issues that materially affect the tests**, under the severity headings in the response format.

Steps 1 to 6 are your analysis. They shape the plan and the class but are not printed as their own sections.

## Test plan

A compact table: one row per test method, and what it proves.

```markdown
| Test | Proves |
| --- | --- |
| dispatchesValidWorkOrder | Happy path: status Dispatched, technician assigned |
| rejectsMissingTechnician | Null-technician guard at the top of `dispatch` |
| dispatchesInBulk | 200 work orders in one call; method accepts a List |
| syncsWithErp | Skipped: response contract is in unsupplied `ErpClient` |
```

Keep "Proves" short and specific to the code (which guard, which branch, which contract). When a scenario depends on a **Cannot Verify** item or is skipped, say so in the row. When improving an existing class, add a Status column (New, Changed, Unchanged). If a limitation of the test context matters (for example, true multi-scope batch behavior cannot be reproduced), add one line under the table.

## Writing the test class

- Organize test classes around meaningful entry points or cohesive units of behavior. One test class per production class is fine when the project already follows that convention, but do not mechanically create separate test classes for handlers or helpers whose behavior is already exercised through their public entry point (for example, a trigger handler that exists only to serve one trigger). Avoid duplicate tests that merely mirror the production file structure. Name classes after the project's convention (commonly `<ClassName>Test`).
- Use `@TestSetup` when multiple tests genuinely share meaningful base data and centralizing it reduces duplication without making individual scenarios harder to understand. Prefer local setup when records are specific to one scenario. Do not decide based on a count of test methods. Do not introduce a test-data factory class for a small suite; use an existing factory if one is supplied.
- Avoid `@SeeAllData=true`. That a dependency cannot be created with test DML does not by itself justify it: Custom Metadata, record types, profiles, and other setup records are already visible to tests. Use it only when the test genuinely requires org data that cannot be isolated or supplied another way, and explain why that org dependency is acceptable. Prefer deployed metadata, mocks, dependency injection, test-created data, or **Cannot Verify**.
- Do not reset or mutate `@TestVisible` static state merely to protect tests from hypothetical automation that was not supplied.
- Use `@TestVisible` state only when testing that state is itself necessary to demonstrate behavior visible in the supplied production implementation.
- Do not neutralize possible org automation by resetting production state. If unseen automation causes the test to behave differently in the target org, treat that as **Cannot Verify** rather than hiding the interaction.
- Use `Test.startTest()` / `Test.stopTest()` around the action under test when it runs async work or needs a fresh governor-limit context. Only one pair is allowed per test method.
- After DML or async work, query the records back before asserting. In-memory sObjects do not reflect trigger or workflow changes.
- Every assertion carries a message that says what was expected, so a failure is self-explaining.
- **Assertion style:** match the existing test class or project. With no evidence, use the `Assert` class (`Assert.areEqual`, `Assert.isTrue`, `Assert.fail`), which needs API version 56.0 or later; mention that assumption once. Use `System.assertEquals` if the project's API version is visible and older than 56.0.
- **Expected exceptions:** catch the specific expected type, put `Assert.fail(...)` directly after the call inside the `try`, and assert on the message in the `catch`. Catching a broad `Exception` lets a wrong exception type pass as success.
- Keep the tests themselves bulk-safe: no SOQL or DML inside loops in test code.
- Name test methods for the behavior they prove (`closesCaseWhenAllTasksComplete`), not `test1`.

## Improving an existing test class

1. Work out what the current tests actually prove, test by test. Tests that execute code without meaningful assertions, or that cannot fail, are unreliable tests: report them under Urgent - Needs Attention. Weaker problems go under Warning or Suggested Changes.
2. Identify the gaps against the paths you traced.
3. Keep good tests unchanged. Strengthen weak assertions in place rather than rewriting the method. Remove or rewrite a test only when it is wrong, redundant, or depends on org data.
4. Add the missing scenarios (bulk, negative, async, callout, security) only where the production code makes them relevant.
5. When the user asked you to improve, fix, or extend the class, return the full updated class, with the Status column in the Test Plan. When the user only asked for an assessment of the existing tests, give the findings and end with: "Would you like me to update and recreate this test class with these changes?"

## Cannot Verify

Use the exact label **Cannot Verify** whenever a meaningful test decision depends on information that is not in the supplied files. Check every object the generated tests rely on, including records the production code writes during the test and the test then queries back, not only the objects whose scenarios were skipped.

Format: **Cannot Verify:** *what is unknown*. *Why it affects the test, and what file or information would settle it.*

Example: **Cannot Verify:** whether `Work_Order__c` has required fields or validation rules beyond those referenced in the code. The insert in `@TestSetup` may fail in the org. Supplying the object's field metadata, or running the test once, would settle it.

Example: **Cannot Verify:** the Case organization-wide default and sharing configuration. Without that metadata, a negative record-sharing test may not prove what it is intended to prove. Outcome: skip the sharing scenario.

Example: **Cannot Verify:** required fields, validation rules, and automation on `Integration_Log__c`. Both tests rely on `finish()` inserting a Summary log using only `Status__c` and `Message__c`. Supplying the object metadata would settle it. Outcome: proceed, because those are the only fields the supplied production code shows as needed.

State the unknown and its effect on the test, then stop. Do not append generalizations about what orgs typically or by default have configured; that is guessing presented as context, and it undercuts the evidence discipline this label exists for.

Then choose one of four outcomes and say which:

- **Proceed** when the tests use only what the supplied code shows is needed and there is nothing for the developer to fill in. Say why proceeding is justified.
- **Proceed with a marked placeholder** when the gap is minor and the developer can fill it in seconds (for example, an extra required field). Add an Apex comment `// CANNOT VERIFY: ...` at that exact line.
- **Skip the scenario** when the test would be meaningless without the missing information (for example, a callout response contract hidden in an unsupplied class). Keep it in the Test Plan marked as skipped.
- **Stop short of a full class** when the missing information makes the core tests incorrect. Say so plainly and generate only what can be supported.

Do not invent configuration to make code look compilable. A test that references a made-up field is worse than an honest gap.

Placement: put a Cannot Verify note directly under the issue it affects, or in the Test Plan row it affects. Use a short `## Cannot Verify` section after the test class only for unknowns that matter but are not attached to an issue or a single row, one line each. Do not build a large Cannot Verify section unless several unknowns materially affect the result.

## Production defects

### Production defects discovered while generating tests

If the production code clearly violates an intended behavior and a correct regression test would currently fail:

- Report the production defect clearly, under Urgent - Needs Attention.
- Do not silently weaken the test to match the bug.
- Do not include a knowingly failing regression test inside a test class presented as deployment-ready unless the user explicitly asks for TDD, a failing regression test, or tests to accompany the production fix.
- Instead, place the regression test in a separate **Pending Regression Test** section and state that it should be added after the production defect is fixed.
- If the user asks for tests that demonstrate the existing bug, generating the failing test is appropriate, but label it explicitly as intentionally failing.

The reason: a deployment-ready class that fails on purpose blocks the deployment it was meant to enable, while a test weakened to pass locks the bug in. Keeping the regression test separate avoids both. When the intended behavior is unclear rather than clearly violated, ask, or test the current behavior and flag the doubt.

### Scope boundary with code review

While analyzing production code, you may discover implementation defects.

Report a production defect in this skill when it directly affects:
- whether a meaningful test can be written,
- what the expected behavior should be,
- whether a generated test would intentionally fail, or
- the reliability of the test strategy.

Do not perform a general production-code review anywhere in the response.

Security, architecture, error-handling, or integration defects that do not materially affect test generation belong to the Apex Code Reviewer skill. If useful, mention in one sentence that a separate production review may reveal additional issues.

When a production defect must be mentioned, place it directly under Urgent - Needs Attention or Warning - Should Change. Do not create a separate production-code-review section. Frame it by its effect on the tests: which test fails, at which step, or what it can no longer prove (title it that way too, for example "`start()` can fail before this test reaches its assertions"). In the Fix, offer the test-side resolution first (supply the metadata, confirm the environment), then a production change as the alternative if intended behavior calls for one.

## Response format

This skill's primary job is to produce a test class, so the response leads to it. Use these sections in this order:

```
## What Needs To Be Tested
## Test Plan
## Urgent - Needs Attention   (only when there are production/testability issues)
## Warning - Should Change    (only when there are production/testability issues)
## Suggested Changes          (only when there are production/testability issues)
## Generated Test Class       (or "Updated Test Class")
## Pending Regression Test    (only when a production defect blocks a correct test)
## Cannot Verify              (only when necessary)
```

- **What Needs To Be Tested**: a short explanation of the production behavior under test: what it does, its entry points, and anything that shapes the tests (async work, callouts, the API-version access mode). Add one line on scope when it matters (snippet only, a referenced class not supplied).
- **Test Plan**: the compact table above.
- **The three issue sections** hold only production or testability problems that materially affect the generated tests:
  - **Urgent - Needs Attention**: a production defect that makes a correct test fail, or anything that would make the generated tests fail to deploy or give false confidence (unreliable tests).
  - **Warning - Should Change**: problems that weaken the tests or make part of the behavior hard to test reliably, but do not block the class.
  - **Suggested Changes**: first, the unsupplied files that would unlock skipped scenarios (called classes, Custom Metadata records, object metadata), ordered by how much each unlocks. Then, only if a dependency would still block deterministic testing after it is supplied, the smallest seam, factory, or other change, with why it is still needed.
  - If there are no production or testability issues at all, skip all three sections and go straight from the Test Plan to the Generated Test Class. If there are some, include all three headings and use the empty lines for the ones with nothing: `No urgent issues identified.`, `No warnings identified.`, `No additional changes suggested.` Do not create items just to fill a section.
- **Generated Test Class**: the complete, copy-paste-ready class in one Apex code block. If the user wants a file (or the work is in a project folder), also write it as `<TestClassName>.cls` with a matching `-meta.xml` using the project's API version when visible.
- **Pending Regression Test**: the regression test that will pass once the defect reported under Urgent is fixed, with a note that it should be added to the class after the fix. See Production defects.

Urgent and Warning items use:

```
**1. Short issue title**

**What's wrong:** the problem and how it affects the tests, stated directly.

**Fix:** exactly what should be changed.
```

Suggested Changes items use:

```
**1. Short improvement title**

**Change:** what could be improved.

**Fix:** the recommended change.
```

Keep it tight:

- **Each problem appears once.** Do not restate it in the Test Plan, the class comments, and an issue section. Any extra context belongs with the item.
- **Do not over-explain what is correct**, and do not review production code beyond the scope boundary above.
- **Order by consequence** within each section.
- **Keep the length proportional.** A clean 30-line service gets a two-sentence explanation, a three-row plan, and the class.

Example, clean code:

````
## What Needs To Be Tested

`CaseEscalationService` escalates a Case when its Priority changes to High and
queues an external synchronization.

## Test Plan

| Test | Proves |
| --- | --- |
| escalatesHighPriorityCase | Happy-path escalation |
| ignoresUnchangedPriority | Field-change guard |
| handlesBulkUpdate | Collection behavior |
| handlesApiFailure | Failure branch |

## Generated Test Class

```apex
...
```
````

Example, production defect found:

```
## Urgent - Needs Attention

**1. Static Boolean skips records after the first trigger chunk**

**What's wrong:** The handler sets `hasRun = true` after the first chunk of up
to 200 records. A DML operation containing more than 200 records can therefore
skip later records.

**Fix:** Replace the transaction-wide Boolean with an Id-based recursion guard.

The correct regression test is listed below as pending because it fails against
the current production implementation.
```

Then the regression test goes under `## Pending Regression Test`, never inside the class described as deployment-ready.

When the user asks for only the code, give the test class plus a brief list of any **Cannot Verify** items, plus the Pending Regression Test when there is one, and nothing else.

### Closing

When the user asked for a test class, generate it in the same response. Do not ask whether they want something they already requested. Then:

- If production code also needs to change, end with: "Would you like me to update the production class as well and then add the pending regression test?"
- If the user only asked for an assessment of an existing test class, end with: "Would you like me to update and recreate this test class with these changes?"
- Otherwise, do not ask a closing question. Summarize what was generated in one sentence, or say no further changes are required.

Call a class "deployable" or "deployment-ready", here or anywhere in the response, only when the metadata it depends on is known or the tests have actually run and passed. Otherwise describe it as a test class supported by the supplied code, or one that does not invent missing dependencies.

## Edge cases

- **Snippet only**: test what the snippet shows, and say the tests assume the surrounding class compiles as implied.
- **Production code looks buggy**: follow Production defects. Do not write a test that locks in a bug, and do not put a knowingly failing test in a deployment-ready class unasked.
- **Request for "just get coverage up"**: still write tests with real assertions; they cover the same lines. Say briefly why.
- **Managed package or unsupplied called classes**: test only the behavior of the supplied code, and mark the dependency's behavior **Cannot Verify**.
- **Request is really a code review**: this skill writes tests. If the user wants a review of production code, say that is a separate task for the Apex Code Reviewer skill, and keep comments on production code within the scope boundary above.