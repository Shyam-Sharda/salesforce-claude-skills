---
name: "salesforce-security-permission-auditor"
description: "Audits Salesforce security and permission configuration from supplied metadata: who can access an object, field, Apex class, Flow, Record Type or Custom Permission, whether required access is missing or too broad, which security layer controls it, and the smallest fix. Make sure to use this skill whenever the user supplies or points to Permission Sets, Permission Set Groups, Muting Permission Sets, Profiles, sharing settings, Custom Permissions, Experience Cloud or guest-user configuration, user assignment exports, or a persona access matrix, and asks to audit permissions, compare Permission Sets or personas, check least privilege, find excessive or missing access, or explain why a user cannot read, edit, save, see a page or run an Apex controller or Flow, even if they never say audit. Do not use for a general Apex code review or a general Flow review with no access or configuration question, or merely because a Permission Set file appears in unrelated project context."
---

# Salesforce Security & Permission Auditor

Salesforce access is the product of many independent layers. Most real access bugs come from reasoning about one layer and assuming the others: "they have object Edit, so they can edit the field", "the class is `with sharing`, so FLS is enforced", "the Permission Set Group contains the set, so the user has it". This skill exists to keep those layers apart, trace the actual permission path from the evidence supplied, and report only what is wrong, what should change, and what cannot be verified.

It is a configuration and access auditor. It is not a generic security checklist, not an Apex code review (`salesforce-apex-code-reviewer`), and not a Flow design review (`salesforce-flow-reviewer`).

## Core principles

1. **Evidence only.** Never invent Profile or Permission Set grants, assignments, Permission Set Group membership, muting, CRUD, FLS, OWD, sharing rules, role hierarchy, sharing sets, user licenses, Custom Permission grants, Apex class access, Flow access, Record Type visibility, Experience Cloud configuration, Apex API versions, or any other org configuration. If a conclusion needs something that was not supplied, say so with the exact label **Cannot Verify**.
2. **Layers stay separate.** Identify which layer actually controls the issue. One layer never proves another (see the table below).
3. **Requirements come from the user.** Judge "too broad" or "missing" against the requirements or access matrix the user supplied. Without requirements, flag only objectively powerful access, and label it as potentially excessive or as a business decision needing confirmation, not as a defect.
4. **Smallest fix.** Recommend the single configuration change that resolves the issue inside the existing architecture. Do not redesign the permission model unless asked.
5. **Clean audits are valid.** If the configuration matches the requirements, say so briefly. Do not manufacture least-privilege findings.
6. **Answer the question asked.** A narrow question ("Can the Technician set edit `WorkOrder.Technician_Notes__c`?") needs only the files that answer it and a short reply.

## Security layers

Keep these distinct. The right-hand column is what people most often wrongly infer.

| Layer | Proves | Does not prove |
| --- | --- | --- |
| User exists / authenticated | A login identity | Any permission |
| User license / Permission Set License | Which permissions can be granted | That they are granted |
| Profile / Permission Set assignment | The user receives that source's grants | What other sources grant |
| Permission Set Group composition | The group bundles those sets | That a user is assigned the group, or that muting left the grant intact |
| Muting Permission Set | A permission is removed *within that group* | Removal of the same permission granted by another source |
| Object CRUD (Read/Create/Edit/Delete/View All/Modify All) | Object-level capability | FLS, or which records |
| Field-level security (readable/editable) | Field capability | Object CRUD |
| Record-level sharing (OWD, ownership, roles, rules, teams, sharing sets, manual/Apex sharing) | Which records | Object CRUD or FLS |
| Record Type visibility | Which record types can be used | Object CRUD |
| Apex class access | The user can invoke the class entry point | CRUD, FLS, sharing, or Custom Permissions inside it |
| Flow access | The user can run the Flow | Access to the data the Flow touches |
| Custom Permission | Business authorization checked by code/Flow | CRUD or FLS |
| App / tab / page / component visibility | The UI is reachable | Any data access |
| Experience Cloud membership / guest user | Site reachability and the external/guest security model | Internal-user behavior |

`references/security-layer-guide.md` explains each layer in more depth, including Experience Cloud, guest users, Apex execution mode and Flow run context. Read it when the question involves a layer you need to reason about carefully.

`references/metadata-permission-guide.md` explains the XML structures (Permission Set, Profile, Permission Set Group, Muting Permission Set, object sharing model, sharing rules, Apex and Flow metadata) and, critically, how to interpret absent entries. Read it before drawing conclusions from metadata files, especially Profiles and partial retrieves.

## Workflow

Do these steps before writing findings. Keep the work proportional to the question.

### 1. Inventory the supplied evidence

Note which of these were supplied: Profiles, Permission Sets, Permission Set Groups, Muting Permission Sets, Custom Permissions, object/field metadata, Apex classes and their `-meta.xml`, Flows, Record Types, sharing settings and rules, Experience Cloud metadata, user/assignment exports, role information, licenses, stated personas or an access matrix. Note only the missing dependencies that matter to the question.

When three or more permission files are supplied, or a Permission Set Group must be resolved, run the inventory helper (below) instead of reading each XML by hand. Manual comparison of several long permission files is where omissions happen.

### 2. Establish the question or requirement

Use explicit requirements if given. If the user asked a narrow question, answer that question. Do not invent a full security architecture nobody asked for.

### 3. Trace the permission path

Follow the evidence from user/persona to the capability:

```text
Technician user
  ↓ assigned (evidence: assignment export)
MillTrack_Technician Permission Set Group
  ↓ contains
MillTrack_WorkOrder_Access
  ↓ grants
WorkOrder: Read/Edit (no Create, no Delete)
WorkOrder.Technician_Notes__c: Read/Edit
TechnicianWorkOrderController: class access
```

Account for muting. Each link must be evidenced separately; if a link has no evidence, that is a Cannot Verify, not an assumption.

Permissions are additive across Profile, Permission Sets and Permission Set Groups. Absence from one Permission Set is not a denial if another assigned source grants it. The main subtractive mechanism is muting, which only affects permissions inside its own group. When you do not have every permission source assigned to a user, do not claim to know their complete effective access.

### 4. Check required access

Compare each required capability with the actual grants, layer by layer.

### 5. Check excessive access

Look for concrete access broader than the stated role: Modify All / View All, Delete or Create where the requirement says Read or Read/Edit, edit access to sensitive or internal fields, internal Apex controllers exposed to portal or guest personas, powerful user permissions (for example Modify All Data, View All Data, Author Apex, Manage Users, Customize Application), powerful Custom Permissions, broad Flow access, guest-user grants. Do not flag ordinary Edit or Delete when the role requires it, and do not flag harmless differences just because two Permission Sets are not identical.

### 6. Check dependent layers

A feature usually needs several layers at once. For example, an LWC backed by an `@AuraEnabled` controller may need page/component exposure, Apex class access, object CRUD, field FLS and record-level access. Do not stop at the first layer that looks wrong; check the others the evidence covers, then report the one that actually blocks or over-grants.

### 7. Identify unknowns

Add a Cannot Verify only when the missing information would change a conclusion the user cares about. Skip irrelevant gaps, and skip layers the user explicitly placed out of scope (see Respect explicit scope below).

### 8. Recommend the smallest correction

Examples: grant Edit on one field; remove Delete from one object entry; add class access for one controller; add Flow access; assign an existing Permission Set; add a Custom Permission to the right Permission Set; remove an over-broad grant from one set; move one granular permission into a more appropriate existing set.

## Specific reasoning rules

**Object CRUD.** Report the exact flags (Read, Create, Edit, Delete, View All, Modify All), never just "has access". View All and Modify All bypass record-level sharing for that object, so flag them when they conflict with the role or give portal/guest/external personas broad record reach.

**FLS.** Readable and editable are separate. When object Edit exists but field Edit does not, the field is read-only for that user under user-mode enforcement. Do not treat a missing field entry as a grant, and do not treat it as a deliberate denial when the file may be a partial retrieve (see the metadata guide).

**Profiles vs Permission Sets.** Analyze the architecture that exists. A Profile granting something is not a defect. Recommend moving access into Permission Sets or Permission Set Groups only when it materially simplifies or fixes the supplied model, or when the user asks for a modernization plan.

**Permission Set Groups.** Inventory member sets, find the relevant grants, apply the group's Muting Permission Set, and only then state the group's grants. Never claim a user has the group without assignment evidence. Judge the group by its result after muting: if a member set grants something (for example WorkOrder Delete) that the group's muting set removes, and the resulting group access matches the requirement, that is not a finding. Do not recommend removing the grant from the member set, since it may be intentionally reused elsewhere; recommend that only when the broader design or requirements show the member grant itself is wrong.

**Apex class access.** Authenticated and guest users calling `@AuraEnabled` methods need class access through their Profile or a Permission Set. Class access and data access are independent: a user can run the class and still fail its DML, or have the data access and still be blocked from the class. When Apex source is supplied, read only what is needed: sharing declaration, explicit `USER_MODE` / `SYSTEM_MODE` (`WITH USER_MODE`, `AccessLevel.USER_MODE`, `insert as user`, and so on), objects and fields touched, Custom Permission checks, and the exposed entry points.

**Apex API version.** Default security behavior depends on the class's API version. At API 67.0 and later, database operations run in user mode by default (object permissions and FLS enforced) and classes without a sharing keyword run `with sharing`; at 66.0 and earlier the defaults are system mode and, for undeclared classes, context-dependent sharing. Triggers always run in system mode. Use the version in the supplied `.cls-meta.xml` or `.trigger-meta.xml`; a debug-log header is not proof of a class's API version. Explicit mode clauses override the defaults. If the version is unknown and it changes the conclusion: **Cannot Verify:** the Apex metadata API version.

**System mode is not automatically a defect.** Explain it neutrally unless a user-controlled entry point exposes data beyond the intended model, the stated requirements say user permissions must be honored, or the elevated behavior creates an evidenced boundary problem. `with sharing` alone never enforces CRUD/FLS, and `System.runAs` in tests does not prove production CRUD/FLS behavior.

**Flow access.** Separate permission to run the Flow from permission over the data it touches, and from the Flow's run context. Use the run context only when the Flow metadata states it. If launch or run context is missing and matters, Cannot Verify.

**Custom Permissions.** Treat as business authorization. Trace: which Custom Permission is checked → which Permission Sets/Profiles grant it → which groups contain those sets → muting → assignment. Do not suggest replacing a Custom Permission with Custom Metadata; Custom Metadata is configuration, not user authorization.

**Record Types.** Report Record Type visibility (and the default, if supplied) separately from object CRUD. Refer to Record Types by developer name, never by ID.

**Record-level sharing.** Object Read means the user can potentially read records of that object, not which records. Do not say "this user can see every Work Order" unless View All, Modify All, View All Data / Modify All Data, or a Public Read OWD plus supplied evidence establishes it. If OWD, ownership, sharing rules or assignments are missing and the question depends on them, Cannot Verify.

**Experience Cloud and guest users.** Keep site membership, Profile/Permission Sets, CRUD, FLS, Apex class access, Flow access, external sharing (external OWD, sharing sets, sharing rules, ownership), guest restrictions and component visibility separate. Do not assume external users behave like internal users, and do not assume that a page displaying a record proves direct record access, since the data may come through system-mode Apex.

## Response discipline

### Respect explicit scope

When supplied requirements explicitly place a security layer outside the scope of the audit, do not create a `Cannot Verify` finding for that layer unless the missing information prevents answering the requested security question. If the requirements say "Audit CRUD/FLS only. Record-level sharing is outside scope." and the CRUD/FLS evidence is sufficient, do not add "Cannot Verify: which records the user can access." `Cannot Verify` is for meaningful unknowns within the requested audit, not for every layer that was not supplied.

The distinction for record-level access:

- The requirement includes record-level access (for example, "Customers see only their own account's Work Orders") and sharing evidence is missing → **Cannot Verify**, and claim neither "all records" nor "only their own records". For example: **Cannot Verify:** whether Customers see only their own account's Work Orders. The supplied Permission Set establishes object Read but not record-level access. The relevant OWD/external OWD and Experience Cloud sharing configuration would settle it.
- Record-level access is explicitly excluded from scope → do not mention it.

### Tie permission-source claims to the evidence

Do not write statements that claim knowledge of the whole org, such as "Nothing else grants the Technician access", unless the evidence establishes it. Prefer "For this audit, `MillTrack_Technician` is the only supplied permission source for the Technician persona", or "According to the supplied requirements, the Technician persona is assigned `MillTrack_Technician`, and no other permission source is assumed." Likewise, "This Permission Set does not grant Delete" is not "The user cannot Delete"; the second needs complete effective-access evidence. When complete assignment evidence is supplied, stronger conclusions are fine.

### Keep conclusions at the layer the evidence establishes

Do not say an operation "works" because one layer is satisfied; record-level sharing or other runtime conditions may still affect it. Say "The supplied object and field permissions satisfy the CRUD/FLS requirements for this operation", not "The query works". "Apex class access is present" does not mean "the controller will run successfully".

### Group closely related findings

Combine grants into one finding when they violate the same role requirement, have the same security impact, and can be fixed together. For example, WorkOrder Edit, WorkOrder Delete and Edit on `WorkOrder.Technician_Notes__c` for a read-only Customer become one finding, "Customer access is not read-only", with one combined fix (set those to false; keep Read). Keep findings separate when they have different causes, severity or fixes, or when grouping would make the answer harder to understand.

### Keep correct configuration compact

Correct configuration is supporting context, not the focus. Mention it in a line, for example: "WorkOrder Read/Edit and controller access match the Technician requirements. `Technician_Notes__c` is readable but not editable." Do not explain each correct flag.

## Inventory helper

`scripts/security_metadata_inventory.py` (Python 3 standard library only) parses Permission Set, Profile, Permission Set Group and Muting Permission Set XML and prints facts. It does not assign severity, decide what anyone should have, infer sharing, assume assignments, recommend changes or modify files. You do the reasoning.

```bash
# Per-file inventory of grants and explicit denials (filter optional)
python3 scripts/security_metadata_inventory.py inventory FILE... [--filter WorkOrder]

# Side-by-side comparison of two or more permission sources
python3 scripts/security_metadata_inventory.py compare FILE FILE... [--filter WorkOrder] [--only-diff]

# Resolve a Permission Set Group: member sets, muting, resulting grants
python3 scripts/security_metadata_inventory.py group GROUP_FILE --search-dir DIR [--filter ...]
```

Add `--json` for machine-readable output. Use `--filter` to keep output focused on the objects, fields, classes or permissions in question.

`group` reports the resulting grants from that Permission Set Group after the supplied muting and the permission dependencies it models (object Read → Create/Edit/Delete/View All/Modify All; Edit → Delete/Modify All; Delete → Modify All; View All → Modify All; field Read → Edit). Each row is `granted`, `MUTED` (explicitly muted) or `MUTED (dependency: X)` (not effective because prerequisite X is muted). That is the group's result, not a user's effective access: the user may also hold the same permissions through their Profile, directly assigned Permission Sets, other groups or licenses, and Salesforce has cross-permission dependencies beyond those the helper models. If any member or muting set is missing or ambiguous, `group` marks the result INCOMPLETE and it must not be reported as the group's resolved result.

## Output format

Keep it short and action-oriented. Do not produce a long report unless asked. Use this structure:

```markdown
## What Access Model Was Found

A few sentences on the relevant personas, permission path and configuration.
Include a compact path diagram when it helps. Mention correct configuration in
one line at most (for example, "Customer access to `Internal_Notes__c` is
correctly absent.").

## Urgent - Needs Attention

**1. Short issue title**

**What's wrong:** One concise explanation tied to the supplied evidence (name the file and the flag).

**Fix:** The smallest configuration change.

(or: No urgent issues identified.)

## Warning - Should Change

**1. Short issue title**

**What's wrong:** ...

**Fix:** ...

(or: No warnings identified.)

## Suggested Changes

**1. Short improvement title**

**Change:** What could improve.

**Fix:** Recommended change.

(or: No additional changes suggested.)

## Cannot Verify

**Cannot Verify:** what is unknown. Why it affects the conclusion. What would settle it.
```

Include the Cannot Verify section only when meaningful unknowns remain. When an unknown qualifies a specific finding, put the Cannot Verify line directly under that finding instead.

**Urgent** is only for: unauthorized data exposure; unauthorized modification or deletion; powerful access outside the intended role; required users completely blocked from a critical feature; security-control bypass; guest/customer exposure to internal data; material privilege escalation.

**Warning** covers important but non-critical issues: required field, Apex class or Flow access missing; potentially excessive permissions; ambiguous or fragile persona configuration; a permission in an awkward layer that will cause maintenance problems.

**Suggested Changes** are optional improvements that materially simplify or strengthen the model. Leave the section as "No additional changes suggested." rather than filling it.

Do not add separate CRUD / FLS / Sharing / Apex / Flow / Experience Cloud / Profile / Least Privilege review sections, "Recommended Next Steps", or any numerical score. A finding appears once. A simple missing field permission gets a few lines, not a page.

### Short example

```markdown
## What Access Model Was Found

`MillTrack_Technician` grants WorkOrder Read/Edit and class access to
`TechnicianWorkOrderController`, but `Technician_Notes__c` is readable only.

## Urgent - Needs Attention

No urgent issues identified.

## Warning - Should Change

**1. Technician cannot edit Technician Notes**

**What's wrong:** The persona has WorkOrder Edit, but `WorkOrder.Technician_Notes__c`
has `editable=false` in `MillTrack_Technician.permissionset-meta.xml`, so the required
note update fails under user-mode enforcement.

**Fix:** Set `editable` to `true` for `WorkOrder.Technician_Notes__c` in `MillTrack_Technician`.

## Suggested Changes

No additional changes suggested.
```

### Clean audit

When the configuration matches the stated requirements, state the resulting access model briefly, then write the three sections with their "none" lines and one sentence saying the supplied configuration matches the requested access model as far as the evidence shows. Add Cannot Verify items only if they genuinely remain within the requested scope; when everything the scoped audit needs was supplied, omit the Cannot Verify section entirely. Unless the user asks for deeper analysis, do not explain each correct permission, recommend reorganizing Permission Sets or moving permissions between Profiles and Permission Sets, manufacture least-privilege improvements, or add a score.

## Example requests

1. "Audit these Customer, Technician and Service Manager Permission Sets against this access matrix. Tell me only what is missing or too broad." Compare actual grants against the matrix; report mismatches only; do not explain each correct permission.
2. "My Experience Cloud Customer can open the Work Order page but gets an error when saving `Maintenance_List__c`. Here are the Customer Permission Set, WorkOrder metadata and Apex controller. Find the missing permission." Separate object Edit, field Edit, record-level access and Apex class access, and identify only the evidenced missing layer; Cannot Verify the rest.
3. "Compare these two Permission Set Groups and tell me whether either one gives Delete, Modify All, or access to internal Apex classes that the other doesn't." Resolve both groups with the helper (including muting), report those specific differences, stay short.
