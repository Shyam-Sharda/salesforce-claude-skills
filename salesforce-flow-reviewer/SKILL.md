---
name: "salesforce-flow-reviewer"
description: "Performs a structured, Salesforce-specific review of Flow metadata (*.flow-meta.xml): purpose and execution path, bulkification and governor limits, record-triggered design (before/after-save, entry criteria, recursion), Get/Create/Update/Delete usage, decision logic, fault handling, Screen Flow behavior, run mode and security, maintainability, Flow-vs-Apex fit, and testing gaps. Make sure to use this skill whenever the user pastes, uploads, or points to Flow XML or a .flow-meta.xml file (record-triggered, before/after-save, autolaunched, screen, scheduled, subflow, or flows calling Apex, callouts, Prompt Builder or Agentforce actions) and asks for a review, audit, feedback, PR check, second opinion, \"is this bulk safe\", \"will this hit limits\", \"why does this flow fail\", or \"what's wrong with this flow\", even if they never say \"review\". Do not use for building a new Flow from scratch, reviewing Apex classes or triggers on their own, or general Flow Builder how-to questions with no Flow metadata attached."
---

# Salesforce Flow Reviewer

Flow metadata is XML that describes a graph: elements (Get Records, Decisions, Loops, Actions...) joined by connectors. Reviewing it well means first rebuilding that graph in your head, then asking Salesforce-specific questions of it: what runs per record, what runs per loop iteration, what happens when an element fails, and in whose security context it all runs.

A useful review is accurate, grounded in the supplied files, and proportional. Volume of findings is not the goal. "This Flow is sound; here is one thing to watch" is a good review when the Flow is sound.

## Core principles

1. **Understand before criticizing.** State what the Flow is for before judging how it does it. Many apparent flaws are reasonable given the purpose.
2. **Evidence only.** Report only what the supplied files show. Never invent objects, fields, profiles, permission sets, flow access settings, sharing rules, OWDs, validation rules, triggers, other Flows, Process Builder, Workflow Rules, Custom Metadata, Apex behavior, external-system behavior, Agentforce or Prompt Builder behavior, record volumes, or org configuration. When an important conclusion depends on something not supplied, label it **Cannot Verify** (exact wording).
3. **A clean review is valid.** Do not manufacture findings to fill sections. A section with nothing to report gets one line saying so.
4. **Calibrate severity.** A finding is Critical only when the metadata shows a realistic path to failure, incorrect behavior, data exposure, or significant limit risk. Say briefly why you chose the level, so the author can disagree intelligently.
5. **Respect the existing design.** Suggest the smallest fix that works within the current Flow. Don't redesign the Flow, convert it to Apex, or add Subflows unless there is a concrete correctness, performance, maintainability, or reuse benefit, and name that benefit.
6. **Separate defects from decisions.** Technical defects are findings. Product, UX, and business-policy choices (which fields a screen asks for, what a record's default status should be) are not defects; if worth mentioning, present them as questions for the owner. Builder canvas layout, element positioning, and naming taste are not defects unless they cause a real maintainability problem.
7. **No invented numbers.** Don't invent application thresholds (maximum records per screen, ideal element counts, etc.) unless they come from a Salesforce platform limit or a supplied business requirement.

## Workflow

1. **Inventory.** If you can run Python, run the bundled parser on each Flow file:

   ```bash
   python <skill-dir>/scripts/flow_inventory.py path/to/MyFlow.flow-meta.xml
   ```

   It prints the Flow type, start/trigger configuration, run mode, every element with its key settings, the connector graph, loop bodies (with database and action elements inside them flagged), fault-capable elements with no fault connector, unreachable elements, and possible hardcoded IDs. Treat its output as a reliable map of the XML, but verify anything you report as a finding against the XML itself. The script detects structure; it does not judge severity. If you cannot run it, read the XML directly using `references/flow-xml-guide.md`.

   Also list what was supplied (Flow files, Apex classes, subflows, permission sets, other automation) and what is referenced but not supplied (an invoked Apex class, a called subflow, a Prompt template).

2. **Establish purpose.** In 2 to 4 sentences: what the Flow does, what starts it (object and trigger, schedule, screen launch, invocation by another Flow or Apex), and what data it reads and writes. If you are inferring intent from labels and descriptions, say so. Proceed on that assumption rather than stopping to ask, unless the Flow is too ambiguous to review meaningfully.

3. **Reconstruct the execution path.** Build the execution path from the connector graph, even when you will not print it. This is also how you find the real problems, because most Flow defects live in the shape of the graph: what sits inside a loop, which branch has no fault path, which outcome is unreachable.

4. **Review against the checklists.** Read `references/review-checklists.md` and apply the sections that fit this Flow type. Apply the general sections to everything.

5. **Classify and prune.** For each candidate finding ask two questions. Is it evidenced in the supplied metadata? If not, convert it to **Cannot Verify** or drop it. Is there a concrete Salesforce consequence? If not, drop it, or keep it as a minor Improvement only if it meaningfully affects maintainability. Merge duplicates. Use `references/severity-and-cannot-verify.md` to calibrate.

6. **Write the review** in the structure below.

## Severity levels

- **Critical**: likely bugs, data integrity issues, security exposure, governor-limit failures, broken automation, infinite or repeated execution, or anything else that makes the Flow unsafe to deploy.
- **Warning**: implementation choices that may cause failures or maintenance problems depending on context. The author should make a conscious decision.
- **Improvement**: meaningful maintainability, clarity, performance, or design improvements that are not immediate defects.

These map to the response headings:

- Critical → **Urgent - Needs Attention**
- Warning → **Warning - Should Change**
- Improvement → **Suggested Changes**

The simpler format changes only how findings are presented. The severity rules above and in `references/severity-and-cannot-verify.md` are unchanged, so do not downgrade a genuine Critical issue because the output is shorter.

## Cannot Verify

Use **Cannot Verify** whenever a conclusion that matters depends on something not in the supplied files: what an Apex action or subflow does inside, whether other automation exists on the object, who can run the Flow, the running user's permissions, record volumes. State what is unknown and why it matters. Don't guess in either direction.

Placement:

- When the unknown affects a finding, put it directly under that finding:

  **Cannot Verify:** Case organization-wide default and sharing configuration. Without that metadata, this behavior cannot be confirmed.

- When an unknown is important but is not itself a defect, list it in a short `## Cannot Verify` section after the three main sections, one line per item.
- Do not number Cannot Verify items or count them as defects. Keep each one short.

## Review reasoning that shapes findings

- **Fault handling:** judge whether failure handling matters for this Flow and this element. Do not demand a fault connector on every element.
- **Security:** reason about the separate layers: run mode / execution context, record-level access, object permissions, field-level security, and business-level authorization (should this user be allowed to do this action, not merely can they run the Flow).
- **Bulk behavior:** ask what runs per record and per loop iteration, and whether record-triggered execution holds up when many records arrive in one transaction.

Findings from all of these go under the severity heading they earn, not in separate review sections.

## Response format

The purpose of the response is to tell the developer what needs attention and how to fix it. Use this structure by default:

```
## What This Flow Does
## Urgent - Needs Attention
## Warning - Should Change
## Suggested Changes
## Cannot Verify            (only when needed)
```

- **What This Flow Does**: 2 to 4 sentences on what the Flow does, its type and start configuration (object, trigger, entry criteria, schedule, run mode, status), and the data it reads and writes. Add one line on scope when it matters (partial XML, a referenced subflow or Apex action not supplied, an inferred purpose). Include a compact execution path when it materially helps understand the findings (see below).
- **Urgent - Needs Attention**: only issues that can cause broken behavior, failed deployment, incorrect data, security exposure, governor-limit failures, unreliable tests, or serious production failures. If none: `No urgent issues identified.`
- **Warning - Should Change**: important issues that are not immediate blockers but should reasonably be corrected. If none: `No warnings identified.`
- **Suggested Changes**: optional improvements to maintainability, clarity, testing quality, performance, architecture, or developer experience. Do not create suggestions just to fill this section. If none: `No additional changes suggested.`

Execution path, when included: a code block using `↓` for sequence and `├──` / `└──` for branches, with element labels (or API names when labels are unclear). Mark loops, fault paths, and scheduled or async paths. Collapse large Flows into major branches. Example:

```
Start (Case, after save, Status changed to Escalated)
  ↓
Get Account
  ↓
Check Support Tier
  ├── Premium → Create Escalation Task
  └── Default → (end)
  ↓
Notify Owner (Apex: CaseNotifier)   [fault → Log Error]
```

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

- Name the element API name(s) inside **What's wrong**, plus the path when it matters (for example, `Loop_Over_Line_Items` → `Get_Product`). Never cite XML line numbers unless the file was supplied with visible line numbers.
- When the severity is not obvious, say in one clause why it sits at that level, so the author can disagree intelligently.
- Describe the **Fix** in Flow Builder terms. Show an XML snippet only when it genuinely clarifies, and keep it to the affected element.
- Number items from 1 within each section.

Keep it tight:

- **Each problem appears once**, under its severity. Do not add Overall Assessment, Bulkification / Performance Review, Error Handling Review, Security Review, Maintainability Review, Testing Gaps, or Recommended Next Steps sections by default. Any extra context belongs with the finding.
- **Do not over-explain what is correct.** Acknowledge a sound area in one line inside What This Flow Does, and only when useful (for example, "Bulk handling looks correct: there are no database elements inside the loop.").
- **Order by consequence.** Within each section, put the issue with the greatest consequence first. Never put cosmetic cleanup ahead of correctness, security, governor limits, data integrity, or deployment problems.
- **Keep the length proportional to the findings.** A tidy six-element before-save Flow should not become a multi-page report. It may produce only the three headings, two "No ... identified." lines, and one short suggestion.

Example finding:

```
## Urgent - Needs Attention

**1. Update Records is inside the loop**

**What's wrong:** `Update_Contact` executes once for each Contact in
`Loop_Contacts`, creating one DML operation per iteration.

**Fix:** Modify the current Contact using Assignment, add it to a collection,
and perform one Update Records after the loop.
```

### Closing question

End a normal review with:

> Would you like me to update and recreate this Flow metadata with these changes?

Do not regenerate the XML until the user asks. Do not ask the question when the user already explicitly asked for modified metadata, when it was already provided in this response, or when no changes are recommended; in those cases, state in one sentence that no further changes are required or what was changed.

### Detailed audit (only on explicit request)

If the user explicitly asks for a detailed or full audit, you may add sections after the three severity sections: Flow Execution Summary (full), Bulkification / Performance Review, Error Handling Review, Security Review, Maintainability Review, Testing Gaps, and Recommended Next Steps. Full findings still appear only once, under their severity; the extra sections refer to them by section and number (for example, "Urgent 1") and say what looks sound.

## Fix guidance

- Preserve the existing elements, API names, and structure where reasonable.
- Describe fixes as Flow Builder changes; include a minimal XML snippet of the affected element only when helpful.
- Do not rewrite or regenerate the whole Flow XML unless the user explicitly asks for modified metadata. If they do, keep the architecture, change only what the findings require, and list each change.
- If a fix needs a structural change (splitting into a before-save Flow, moving work to an async path, extracting an invocable Apex action), explain why the smaller fix is not enough.

## Edge cases

- **Several Flow files**: review them as a set. Note cross-file issues, such as a parent Flow calling a supplied subflow from inside a loop where the subflow does a Get Records. Give each Flow its own short What This Flow Does; the three severity sections can be shared, naming the Flow in each finding.
- **Flow tests or Apex tests supplied**: review what they demonstrate and put each weakness under its severity. If no tests were supplied, that is not a finding and needs no section; a specific untested risk (for example, nothing exercises the bulk path) can be one Suggested Change.
- **Apex supplied alongside the Flow**: you may look inside it to settle questions the Flow raises (does the invocable method query per record? is it bulkified over its input list?). For a full Apex review, mention that the Apex reviewer skill covers that.
- **Snippet or partial XML**: review what is there and say the review is limited to it.
- **Process Builder or Workflow metadata, or a non-Flow file**: say this skill covers Flows, and review only Flow metadata that is present.
- **Narrow question** ("just check bulk safety"): answer that scope, and say in one line that the rest was not reviewed.
- **Inactive or obsolete version**: note the status; still review it if asked.
