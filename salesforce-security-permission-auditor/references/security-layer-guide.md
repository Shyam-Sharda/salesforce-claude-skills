# Security Layer Guide

What each Salesforce access layer controls, what it proves, and what it does not prove. Use this to decide which layer actually controls an access question. It complements SKILL.md; it does not repeat the workflow or output format.

## Contents

1. Assignment sources: Profile, Permission Set, Permission Set Group, Muting
2. User licenses and Permission Set Licenses
3. Object CRUD
4. Field-level security
5. Record-level sharing
6. Record Types
7. Apex class access and Apex execution mode
8. Flow access and Flow run context
9. Custom Permissions
10. App, tab, page and component visibility
11. Experience Cloud and guest users
12. Quick diagnosis: "why can't they…?"

---

## 1. Assignment sources

A user's permissions come from exactly one Profile plus any number of Permission Sets and Permission Set Groups. Grants are additive: if any assigned source grants a permission, the user has it, unless muting inside a group removes it from that group.

- **Permission Set contains a permission.** Evidence: the Permission Set file.
- **Permission Set Group contains a Permission Set.** Evidence: the group file's `permissionSets` list.
- **Muting Permission Set removes a permission from the group.** Evidence: the group's `mutingPermissionSets` reference plus the muting file. Muting applies only to permissions that come *through that group*. If the same permission is granted by the user's Profile or by a Permission Set assigned directly (or by another group without that muting), the user still has it.
- **User is assigned the source.** Evidence: a user record (Profile), or a `PermissionSetAssignment` export / Setup screenshot (Permission Sets and Groups). Nothing in a Permission Set file proves who is assigned to it.

Each of the four must be evidenced separately. Without the full set of sources assigned to a user, their complete effective access is Cannot Verify.

Permission Set Groups are recalculated after changes; a group in a failed or outdated recalculation status may not reflect its metadata. If the user reports behavior that contradicts correctly resolved group metadata, recalculation status is a reasonable Cannot Verify.

## 2. User licenses and Permission Set Licenses

The user license (Salesforce, Salesforce Platform, Customer Community, Customer Community Plus, Partner Community, guest, and so on) caps which objects and permissions can be granted at all. A Permission Set can be tied to a license (`<license>` in its metadata) and then can only be assigned to users with that license. Some features also need a Permission Set License.

- License eligibility does not prove a grant.
- A grant in a Permission Set does not prove the license allows it for a given user. If a persona's license was not supplied and the feature is license-sensitive (for example, sharing sets, roles for external users, certain standard objects in communities), Cannot Verify.

## 3. Object CRUD

Six independent flags per object: Read, Create, Edit, Delete, View All, Modify All.

- Platform dependencies: Create and Edit require Read; Delete requires Read and Edit; View All requires Read; Modify All requires Read, Edit, Delete and View All. A file that shows a dependent flag without its prerequisite is usually malformed or partial.
- **View All** lets the user read *all* records of the object regardless of sharing. **Modify All** lets them read, edit, delete (and transfer/approve) all records regardless of sharing. These are effectively record-level grants and should be compared against the record access the role is meant to have.
- System user permissions **View All Data** and **Modify All Data** do the same across every object, and **View All Fields** style permissions can widen field visibility. Treat them as powerful.
- Object Read says the user *may* read records of the object. It does not say which ones.
- Detail objects in a master-detail relationship take record-level access from the master. CRUD on the detail object is still separate.

## 4. Field-level security

Two flags per field: readable and editable. Editable requires readable.

- FLS is enforced in the standard UI, in Lightning Data Service / LWC base components, in the API, and in Apex/Flow only when they run in user mode or explicitly enforce it.
- Object Edit without field Edit means the field is read-only for that user.
- Field Edit without object Edit does not let the user edit the record.
- Universally required fields and some system fields do not appear in field permissions at all; their absence is not a denial.
- Page layout "read-only" is a UI setting, not FLS. A field editable via FLS can still be read-only on a layout, and the reverse.

## 5. Record-level sharing

Determines *which* records a user can see or change, once object CRUD allows the operation at all. Sources:

- **Organization-wide defaults (OWD)**: internal (`sharingModel`) and external (`externalSharingModel`) defaults per object: Private, Read, ReadWrite, ControlledByParent, and so on.
- **Ownership** and **role hierarchy** (with "Grant Access Using Hierarchies" for custom objects).
- **Sharing rules**: owner-based and criteria-based, including guest user sharing rules.
- **Teams** (Account, Opportunity, Case), **manual sharing**, **territories**.
- **Implicit sharing** (for example, parent account access from child records).
- **Sharing sets** and **share groups** for certain Experience Cloud licenses.
- **Apex managed sharing** (share records written by code).
- **Execution context**: a `without sharing` class bypasses record-sharing enforcement for operations that use that class sharing context. Explicit user-mode database operations enforce the running user's sharing, CRUD and FLS for that operation, even when broader Apex execution is elevated. Always consider both the class sharing declaration and the operation's explicit `USER_MODE` / `SYSTEM_MODE`; do not treat `without sharing` as proof that every operation inside the class ignores sharing.

A Permission Set alone almost never settles record-level access. Unless View All / Modify All / View All Data / Modify All Data is granted, or OWD plus supplied sharing evidence settles it, "which records" is Cannot Verify.

## 6. Record Types

Record Type visibility (per Profile or Permission Set) controls which record types a user can create records with and pick from. Profiles also set the default Record Type.

- Visibility does not grant object CRUD.
- A user without visibility to a Record Type can still view records of that type if CRUD and sharing allow; the restriction is on creating/assigning it.
- Use developer names (`WorkOrder.Field_Service`), never IDs.

## 7. Apex class access and Apex execution mode

**Class access** (`classAccesses`) controls whether a user may invoke a class through user-facing entry points: `@AuraEnabled` methods called from Aura/LWC (including from Experience Cloud and guest users), Apex REST and web services, and Visualforce controllers. Missing class access typically fails before any code runs.

Class access says nothing about what the code can do with data. That depends on execution mode:

| Mechanism | Controls |
| --- | --- |
| `with sharing` / `without sharing` / `inherited sharing` | Record-level sharing only |
| `WITH USER_MODE` / `WITH SYSTEM_MODE` (SOQL/SOSL) | CRUD, FLS and sharing for that query |
| `AccessLevel.USER_MODE` / `AccessLevel.SYSTEM_MODE` (`Database.*` methods) | CRUD, FLS and sharing for that operation |
| `insert as user` / `update as system` etc. | CRUD, FLS and sharing for that DML |
| `Security.stripInaccessible` | Removes fields the user cannot access |
| `WITH SECURITY_ENFORCED` | CRUD/FLS check on query (not supported at API 67.0+) |
| `FeatureManagement.checkPermission('X')` | Custom Permission (business authorization) |

**API version defaults.** At API 67.0 and later, database operations default to user mode (object permissions and FLS enforced) and classes without a sharing keyword run with sharing. At API 66.0 and earlier, database operations default to system mode, and an undeclared class's sharing depends on context (Aura/LWC entry points run with sharing; non-entry-point classes inherit the caller; otherwise without sharing). Triggers always run in system mode. Use the `apiVersion` in the class's own `-meta.xml`. Explicit mode clauses override defaults.

Implications for auditing:

- User-mode code fails when the user lacks CRUD/FLS for what it touches; system-mode code succeeds and may expose more than the user's own permissions would.
- A page that shows data via system-mode Apex does not prove the user has record or field access.
- System mode is often intentional. It is a finding only when a user-controlled entry point exposes data beyond the intended model, requirements say user permissions must apply, or there is an evidenced boundary problem.
- `System.runAs` tests do not prove production CRUD/FLS behavior.

## 8. Flow access and Flow run context

Three separate questions:

1. **Can the user start the Flow?** Depends on the user having permission to run Flows generally (for example the Run Flows user permission or the relevant license) and, when the Flow is set to restrict access to enabled Profiles/Permission Sets, on a `flowAccesses` grant for that Flow. Record-triggered and scheduled Flows are not started by users this way.
2. **What context does it run in?** From the Flow's `runInMode` (system context with or without sharing, or default/user context) and the Flow type. Record-triggered Flows run in system context. Screen and autolaunched Flows depend on settings and how they are launched (for example, from an Experience Cloud page or from Apex).
3. **Can the data operations succeed?** In user context, the user's CRUD/FLS/sharing apply. In system context they largely do not.

Flow access never proves data access. If the run context or launch context is missing and changes the answer, Cannot Verify.

## 9. Custom Permissions

Custom Permissions are on/off business authorization flags granted by Profiles and Permission Sets, checked by code (`FeatureManagement.checkPermission`), Flow (`$Permission.Name`), validation rules and formulas. They gate *logic*, not data. A Custom Permission can declare required Custom Permissions that must also be granted.

- Holding a Custom Permission does not grant CRUD/FLS for the data that logic touches.
- Custom Metadata is configuration shared by all users; it is not a substitute for per-user authorization.
- To show a persona really has it: grant source → group membership → muting → assignment, each evidenced.

## 10. App, tab, page and component visibility

App visibility, tab settings, Lightning page assignment, component visibility rules, Experience Builder page audiences and navigation menus control what UI is reachable. None of them grant data access, and hiding UI does not remove data access available through the API or other pages. Report UI visibility only when the question is about why something does not appear.

## 11. Experience Cloud and guest users

**Authenticated external users** (customer, partner):

- Must be members of the site through a member Profile or Permission Set.
- Have external-license limits on objects and permissions.
- Use the **external OWD**, which can be stricter than the internal one.
- Get record access through ownership, sharing sets (Customer Community / high-volume licenses), share groups, sharing rules to external roles or groups (role-based licenses), and Apex managed sharing.
- Still need CRUD, FLS and Apex class access like any user.

**Guest (unauthenticated) users**:

- Have a single guest user Profile per site, plus any Permission Sets assigned to the guest user.
- Get record access only through guest sharing rules (and code running without sharing). Salesforce restricts guest users from View All / Modify All and limits their object permissions; treat any broad guest grant as Urgent.
- Need Apex class access for every `@AuraEnabled` controller they call; a controller running without sharing or in system mode effectively hands guests whatever it queries.

Do not assume an external or guest user behaves like an internal user, and do not assume that a page displaying a record proves the user has record access.

## 12. Quick diagnosis: "why can't they…?"

| Symptom | Layers to check, in order |
| --- | --- |
| LWC / Aura error before any data loads | Apex class access → component/page visibility → then data layers |
| Record page opens, save fails on one field | Field editable → object Edit → validation/Flow logic (out of scope beyond noting) |
| Save fails on every field | Object Edit → record-level edit access (OWD/sharing/ownership) → Record Type visibility for new records |
| "Insufficient privileges" opening a record | Object Read → record-level read access → Record Type is *not* the cause |
| Can see the object, cannot see a specific record | Record-level sharing (OWD, ownership, rules, sharing sets) |
| Flow button missing or Flow won't start | Flow access / Run Flows → page/component exposure |
| Flow starts but fails on an update | Flow run context → CRUD/FLS/sharing if user context |
| Code path behaves as if permission absent | Custom Permission grant → group/muting → assignment |
| Works for admin, not for user | Compare every layer; admins usually hold View All Data / Modify All Data |
| Works internally, not in Experience Cloud | External OWD, external license limits, guest/member Profile class access, sharing sets |
