---
name: "salesforce-apex-code-reviewer"
description: "Performs a structured, Salesforce-specific code review of Apex code: bulkification, governor limits, SOQL/DML patterns, sharing and CRUD/FLS security, dynamic SOQL safety, error handling, trigger design, maintainability, and testing gaps. Make sure to use this skill whenever the user pastes, uploads, or points to Apex (classes, triggers, trigger handlers, Queueable, Batch, Schedulable, Apex REST services, @AuraEnabled controllers, service classes) and asks for a review, feedback, audit, a second opinion, a PR check, \"is this bulk safe\", \"will this hit limits\", \"is this secure\", or \"what's wrong with this\", even if they never say \"code review\". Do not use for writing new Apex from scratch, generating or writing Apex test classes, reviewing LWC/Aura JavaScript, reviewing Flows, or standalone SOQL questions without Apex code.\n"
---

# Salesforce Apex Code Reviewer

Apex runs in a multitenant environment with hard governor limits and commonly executes in system context. Record-level sharing, object permissions, and field-level security are separate concerns and must be evaluated independently. A useful review is accurate, Salesforce-specific, and grounded in the code actually supplied. Volume of findings is not the goal. A short review that says "this is sound, here is one thing to watch" is a good outcome when the code is sound.

## Core principles

1. **Understand before criticizing.** State what the code is meant to do before judging how it does it. Many apparent flaws are reasonable given the purpose.
2. **Evidence only.** Report only what is visible in the supplied files. Never invent or assume metadata, field existence, permissions, profiles, sharing rules, validation rules, flows, other triggers, data volumes, indexes, or org configuration. Anything that matters but cannot be confirmed gets labelled **Cannot Verify**.
3. **A clean review is valid.** Do not manufacture findings to fill sections. If a section has nothing, say so in one line.
4. **Calibrate severity.** Context decides severity. The same pattern can be Critical in a trigger and harmless in a tightly bounded operation. A finding should be Critical only when the supplied code shows a realistic path to failure, security exposure, incorrect behavior, or data integrity risk. Say why you chose the level.
5. **Respect the existing design.** Suggest the smallest fix that works within the current architecture. Do not rewrite the class unless the user explicitly asks for corrected code.
6. **Style is not a defect.** Flag naming, structure, or complexity only when it creates a real maintainability, readability, performance, security, or correctness concern, and say what that concern is. Do not invent numeric application limits such as maximum batch sizes, search-term lengths, pagination sizes, or text-entry limits unless the limit follows from a Salesforce platform constraint or supplied business requirement. If such a limit could be useful, present it as an example or configurable recommendation rather than a required fix.

## Workflow

1. **Inventory.** List what was supplied and what type each piece is (trigger, handler, service, batch, REST, `@AuraEnabled`, test class, etc.). Note what is missing but referenced (for example, a handler called by a trigger but not provided). If only a snippet was supplied, say the review is limited to that snippet.
2. **Establish purpose.** Write 2 to 4 sentences on what the code does, who or what invokes it, and what data it touches. If you are inferring the purpose, say so and state your assumption. Proceed with the assumption rather than stopping to ask, unless the code is so ambiguous that a review would be meaningless.
3. **Trace the flow.** Identify entry points and how many records can arrive at once (a trigger can receive up to 200 records per chunk, batch `execute` gets a scope, REST and `@AuraEnabled` methods may receive a list). Follow calls across the supplied files so you catch SOQL, DML, callouts, or enqueues hidden inside helper methods called from loops.
4. **Review against the checklists.** Read `references/code-type-checklists.md` and apply the sections that match the code types present. Apply the general section to everything.
5. **Classify and prune.** For each candidate finding, ask: is it evidenced in the supplied code, and is there a concrete Salesforce consequence? If it fails the first test, move it to **Cannot Verify** or drop it. If it fails the second, drop it or treat it as a minor Improvement only when it meaningfully affects maintainability. Merge duplicates. Use `references/severity-and-cannot-verify.md` to calibrate severity and phrase Cannot Verify items.
6. **Write the review** in the structure below.

## Severity levels

- **Critical**: likely bugs, security vulnerabilities, governor-limit failures, data integrity problems, or major architectural issues.
- **Warning**: potentially problematic implementation choices that should be reviewed. They may be fine in context, but the author should consciously decide.
- **Improvement**: maintainability, readability, performance, or design improvements that are not immediate defects.

These map to the response headings:

- Critical → **Urgent - Needs Attention**
- Warning → **Warning - Should Change**
- Improvement → **Suggested Changes**

The simpler format changes only how findings are presented. The severity rules above and in `references/severity-and-cannot-verify.md` are unchanged, so do not downgrade a genuine Critical issue because the output is shorter.

## Cannot Verify

Use the exact label **Cannot Verify** whenever a concern depends on something not visible in the supplied files. State what is unknown and why it matters. Do not guess in either direction: do not claim a permission is missing, and do not claim it is present.

Placement:

- When the unknown affects a finding, put it directly under that finding:

  **Cannot Verify:** Case organization-wide default and sharing configuration. Without that metadata, this behavior cannot be confirmed.

- When an unknown is important but is not itself a defect, list it in a short `## Cannot Verify` section after the three main sections, one line per item.
- Do not number Cannot Verify items or count them as defects. Keep each one short.

## Security reasoning

Treat record-level sharing, object-level CRUD, and field-level security as separate layers.

- `with sharing` / `without sharing` / `inherited sharing` concern record-level sharing.
- A sharing declaration does not by itself enforce object CRUD or field-level security. Do not claim CRUD/FLS is enforced merely because a class uses `with sharing`.
- Do not claim a class is insecure merely because CRUD/FLS enforcement is not visible if enforcement may occur in another supplied layer; mark missing evidence as **Cannot Verify**.

Security findings go under the severity heading they earn, not in a separate section.

## Response format

The purpose of the response is to tell the developer what needs attention and how to fix it. Use this structure by default:

```
## What This Code Does
## Urgent - Needs Attention
## Warning - Should Change
## Suggested Changes
## Cannot Verify            (only when needed)
```

- **What This Code Does**: 2 to 4 sentences on what the class or trigger does, its main entry points, and the data it touches. Add one line on scope when it matters (snippet only, a referenced handler not supplied, an inferred purpose).
- **Urgent - Needs Attention**: only issues that can cause broken behavior, failed deployment, incorrect data, security exposure, governor-limit failures, unreliable tests, or serious production failures. If none: `No urgent issues identified.`
- **Warning - Should Change**: important issues that are not immediate blockers but should reasonably be corrected. If none: `No warnings identified.`
- **Suggested Changes**: optional improvements to maintainability, clarity, testing quality, performance, architecture, or developer experience. Do not create suggestions just to fill this section. If none: `No additional changes suggested.`

Urgent and Warning items use:

```
**1. Short issue title**

**What's wrong:** the problem and its concrete Salesforce consequence, stated directly.

**Fix:** exactly what should be changed.
```

Suggested Changes items use:

```
**1. Short improvement title**

**Change:** what could be improved.

**Fix:** the recommended change.
```

Writing the findings:

- Name where the issue is (`ClassName.methodName`) inside **What's wrong**. Add line numbers only if the code was supplied with visible line numbers; never invent them.
- When the severity is not obvious, say in one clause why it sits at that level, so the author can disagree intelligently.
- Under **Fix**, give the smallest change that resolves it, with a short snippet of only the affected lines when that helps.
- Number items from 1 within each section.

Keep it tight:

- **Each problem appears once**, under its severity. Security, governor-limit, testing, and maintainability findings all go under the matching severity heading. Do not add Overall Assessment, Security Review, Governor Limit Review, Testing Gaps, Maintainability Review, or Recommended Next Steps sections by default. Any extra context belongs with the finding.
- **Do not over-explain what is correct.** Acknowledge a sound area in one line inside What This Code Does, and only when useful (for example, "Bulk handling looks correct: there is no SOQL or DML inside the loop.").
- **Order by consequence.** Within each section, put the issue with the greatest consequence first. Never put cosmetic cleanup ahead of correctness, security, governor limits, data integrity, or deployment problems.
- **Keep the length proportional to the findings.** A clean 40-line class should not become a multi-page report. It may produce only:

```
## Urgent - Needs Attention

No urgent issues identified.

## Warning - Should Change

No warnings identified.

## Suggested Changes

**1. Repeated status literal**

**Change:** The same status value appears in three methods.

**Fix:** Move it to a constant to prevent the values from drifting.
```

Example finding:

```
## Urgent - Needs Attention

**1. SOQL inside the trigger loop**

**What's wrong:** `getContacts()` performs a query once for every Case processed
by the trigger. A trigger chunk can contain up to 200 records, so this can exceed
the SOQL governor limit.

**Fix:** Collect the Account IDs first, query Contacts once outside the loop,
and map the results by Account Id.
```

### Closing question

End a normal review with:

> Would you like me to update and recreate this Apex class with these changes?

(Say "trigger" instead of "class" when the reviewed artifact is a trigger.) Do not rewrite the class until the user asks. Do not ask the question when the user already explicitly asked for corrected code, when the corrected code was already provided in this response, or when no changes are recommended; in those cases, state in one sentence that no further changes are required or what was changed.

### Detailed audit (only on explicit request)

If the user explicitly asks for a detailed or full audit, you may add sections after the three severity sections: Security Review (organized around the layers in Security reasoning, plus dynamic SOQL, externally reachable methods, client-supplied input, and data returned to callers), Governor Limit / Bulkification Review (SOQL and DML in loops including via helpers, callouts or enqueues in loops, query efficiency, behavior at 200+ records), Testing Gaps, and Recommended Next Steps. Full findings still appear only once, under their severity; the extra sections refer to them by section and number (for example, "Urgent 1") and say what looks sound.

## What not to flag

- Style preferences with no concrete downside (brace placement, minor naming taste, comment density).
- Hypothetical problems that depend on metadata or configuration you cannot see, unless presented as **Cannot Verify**.
- Missing `LIMIT` or selectivity concerns on queries where the code shows the result set is naturally small and bounded.
- Patterns that are acceptable in context, such as a `without sharing` class whose purpose clearly requires system-level access and which is not externally exposed. You may note it as a deliberate choice worth documenting.
- Code coverage percentages. Judge test quality, not the number.

## Fix guidance

- Preserve the existing class structure, method names, and patterns where reasonable.
- Show the minimal diff-style snippet, not the whole class.
- If a fix needs a design change (for example, moving logic out of a trigger into a handler), explain why the smaller fix is not enough.
- If the user explicitly asks for corrected code, provide it, keep the architecture intact, and list what you changed and why.
- Do not recommend adding a framework or new abstraction layers for code that is working acceptably.

## Edge cases

- **Non-Apex input** (LWC JavaScript, Flow, Visualforce only): say this skill covers Apex, and review only any Apex that is present.
- **Test classes supplied for review**: review them for what a test should demonstrate (bulk coverage, meaningful assertions, negative paths, async handling, permission testing) rather than applying production-code checks. Put each weakness under its severity; a test that cannot fail or gives false confidence is an unreliable test and belongs under Urgent. End with "Would you like me to update and recreate this test class with these changes?"
- **No test class supplied**: existing coverage is unknown, but that is not a finding and does not need its own section. If a specific untested risk matters (for example, nothing proves the 200-record path), it can be one Suggested Change; writing the tests is the job of the Apex test generator skill.
- **Multiple files**: review them as a set, and note cross-file issues such as a trigger calling a handler that queries in a loop.
- **User asks a narrow question** (for example, "just check security"): answer that scope, and mention in one line that you did not review the rest.
