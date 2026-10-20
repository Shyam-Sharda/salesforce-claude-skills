# Metadata Permission Guide

How Salesforce security metadata is structured in source-format XML, and how to interpret it without inventing effective access. Element names below are the Metadata API names; check the actual supplied file if it differs.

## Contents

1. Reading absent entries (read first)
2. Permission Set (`.permissionset-meta.xml`)
3. Profile (`.profile-meta.xml`)
4. Permission Set Group (`.permissionsetgroup-meta.xml`)
5. Muting Permission Set (`.mutingpermissionset-meta.xml`)
6. Object sharing model and sharing rules
7. Apex class and trigger metadata
8. Flow metadata
9. Custom Permission and Record Type metadata
10. Assignment evidence

---

## 1. Reading absent entries

This is where most invented access comes from.

- **Explicit `true`** in a Permission Set or Profile: the source grants it.
- **Explicit `false`**: the source does not grant it. It is not a deny. Another assigned source can still grant it.
- **Absent entry**: the file says nothing. The meaning depends on how the file was produced:
  - Metadata API retrieves of Profiles (and often Permission Sets) only include permissions for components that were also in the retrieve manifest. A Profile retrieved without `WorkOrder` in the package will have no `WorkOrder` object or field entries even if the org grants them. Treat absence as **Cannot Verify** unless the file is known to be complete.
  - A complete Permission Set retrieved with all related objects normally omits ungranted permissions, so absence usually means "not granted by this set". Say "not granted in the supplied file" rather than "denied".
- **No source denies.** Salesforce has no deny permission except muting inside a Permission Set Group, plus license limits.
- **Field entries missing for required fields** are normal; universally required fields are not FLS-controlled.

When the file may be partial and it matters:

**Cannot Verify:** whether omitted field permissions are intentionally denied or simply absent from the supplied metadata.

## 2. Permission Set

```xml
<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>MillTrack Technician</label>
    <license>Salesforce</license>                 <!-- optional; ties set to a user license -->
    <hasActivationRequired>false</hasActivationRequired>
    <objectPermissions>
        <object>WorkOrder</object>
        <allowRead>true</allowRead>
        <allowCreate>false</allowCreate>
        <allowEdit>true</allowEdit>
        <allowDelete>false</allowDelete>
        <viewAllRecords>false</viewAllRecords>
        <modifyAllRecords>false</modifyAllRecords>
    </objectPermissions>
    <fieldPermissions>
        <field>WorkOrder.Technician_Notes__c</field>
        <readable>true</readable>
        <editable>false</editable>
    </fieldPermissions>
    <classAccesses>
        <apexClass>TechnicianWorkOrderController</apexClass>
        <enabled>true</enabled>
    </classAccesses>
    <flowAccesses>
        <flow>Close_Work_Order</flow>
        <enabled>true</enabled>
    </flowAccesses>
    <customPermissions>
        <name>Dispatch_Manager</name>
        <enabled>true</enabled>
    </customPermissions>
    <userPermissions>
        <name>RunFlow</name>
        <enabled>true</enabled>
    </userPermissions>
    <recordTypeVisibilities>
        <recordType>WorkOrder.Field_Service</recordType>
        <visible>true</visible>
    </recordTypeVisibilities>
    <tabSettings>
        <tab>standard-WorkOrder</tab>
        <visibility>Visible</visibility>          <!-- Visible | Available | None -->
    </tabSettings>
    <applicationVisibilities>
        <application>MillTrack</application>
        <visible>true</visible>
    </applicationVisibilities>
</PermissionSet>
```

Notes:

- Object CRUD flags map to: Read = `allowRead`, Create = `allowCreate`, Edit = `allowEdit`, Delete = `allowDelete`, View All = `viewAllRecords`, Modify All = `modifyAllRecords`.
- Field names are `Object.Field`. Fields on related objects are listed under their own object.
- Other permission blocks that can matter: `apexPage` access (`pageAccesses`), `customMetadataTypeAccesses`, `customSettingAccesses`, `externalDataSourceAccesses`. Treat them like class access: they gate entry, not data.
- A Permission Set has no assignment information.

## 3. Profile

Same blocks as a Permission Set, plus Profile-only settings:

- `<userLicense>` (the license the Profile is bound to).
- `recordTypeVisibilities` also carry `<default>true</default>` (and `personAccountDefault`).
- `applicationVisibilities` carry `<default>`.
- Tabs are `tabVisibilities` with `DefaultOn | DefaultOff | Hidden`.
- `layoutAssignments`, `loginHours`, `loginIpRanges`, `custom` (true for custom Profiles).

Profiles are the most common partial retrieve. See section 1 before treating any missing object or field as denied.

## 4. Permission Set Group

```xml
<PermissionSetGroup xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>MillTrack Technician</label>
    <permissionSets>MillTrack_WorkOrder_Access</permissionSets>
    <permissionSets>MillTrack_Base</permissionSets>
    <mutingPermissionSets>MillTrack_Technician_Muting</mutingPermissionSets>
    <status>Updated</status>
</PermissionSetGroup>
```

- `permissionSets` lists member Permission Set API names. The members' own files are needed to know what the group grants.
- `mutingPermissionSets` names the group's Muting Permission Set (at most one per group).
- `status` reflects recalculation; anything other than Updated may mean the live group does not match its metadata.
- The group grants: union of member grants, minus muted permissions. Only within this group.

## 5. Muting Permission Set

Uses the same blocks and element names as a Permission Set, but **`true` means muted**:

```xml
<MutingPermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <label>MillTrack Technician Muting</label>
    <objectPermissions>
        <object>WorkOrder</object>
        <allowDelete>true</allowDelete>     <!-- Delete is MUTED in this group -->
        <allowRead>false</allowRead>
        ...
    </objectPermissions>
    <fieldPermissions>
        <field>WorkOrder.Cost__c</field>
        <editable>true</editable>           <!-- Edit on Cost__c is MUTED -->
        <readable>false</readable>
    </fieldPermissions>
</MutingPermissionSet>
```

- Muting removes a permission only from the group it belongs to.
- Muting a prerequisite (for example object Read) makes dependent permissions not effective through the group. The helper's `group` command applies the object and field prerequisites it models and marks those rows `MUTED (dependency: X)`; reason yourself about any other cross-permission dependency.
- A muting file not referenced by the group under review is irrelevant to that group.

## 6. Object sharing model and sharing rules

In `objects/<Object>/<Object>.object-meta.xml`:

```xml
<sharingModel>Private</sharingModel>          <!-- internal OWD -->
<externalSharingModel>Private</externalSharingModel>  <!-- external OWD -->
```

Values include `Private`, `Read`, `ReadWrite`, `ReadWriteTransfer`, `FullAccess`, `ControlledByParent`. Standard objects may keep OWD in org sharing settings rather than the object file.

Sharing rules (`sharingRules/<Object>.sharingRules-meta.xml`) contain `sharingCriteriaRules`, `sharingOwnerRules` and `sharingGuestRules`, each with an `accessLevel` (`Read`, `Edit`) and `sharedTo` (roles, groups, portal roles, guest user). A rule proves records matching it are shared to that audience; it does not prove a specific user is in that audience without role/group evidence.

Sharing sets and share groups are configured per Experience Cloud site and are often not in source; if not supplied, Cannot Verify.

## 7. Apex class and trigger metadata

`.cls-meta.xml` / `.trigger-meta.xml`:

```xml
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>67.0</apiVersion>
    <status>Active</status>
</ApexClass>
```

`apiVersion` here is the authoritative source for version-dependent security defaults. A debug log's API version header reflects the request, not the class.

In the `.cls` source, look only at: sharing keyword on the class, `@AuraEnabled` / `@RestResource` / `webservice` entry points, explicit mode (`WITH USER_MODE`, `WITH SYSTEM_MODE`, `AccessLevel.*`, `as user` / `as system`), `Security.stripInaccessible`, objects and fields queried or written, and `FeatureManagement.checkPermission` calls.

## 8. Flow metadata

Relevant elements in `.flow-meta.xml`:

- `processType` and `start` (`triggerType`, `object`) identify Screen, autolaunched, record-triggered or scheduled Flows.
- `runInMode`: `DefaultMode`, `SystemModeWithSharing`, `SystemModeWithoutSharing`. Absence means default behavior for the Flow type.
- Record elements (`recordLookups`, `recordCreates`, `recordUpdates`, `recordDeletes`) show objects and fields touched.
- `$Permission.<Name>` in decisions or formulas shows Custom Permission checks.
- Whether the Flow restricts access to enabled Profiles/Permission Sets is a Flow-level setting; when it is on, users need a `flowAccesses` grant. If the supplied Flow file does not show this setting and it matters, Cannot Verify.

## 9. Custom Permission and Record Type metadata

`customPermissions/<Name>.customPermission-meta.xml`: label, description, `isLicensed`, and `requiredPermission` entries naming other Custom Permissions that must also be granted.

`objects/<Object>/recordTypes/<Name>.recordType-meta.xml`: `active`, label, picklist value restrictions. Visibility per user comes from Profiles/Permission Sets, not this file.

## 10. Assignment evidence

Only these establish who has what:

- User record or export showing `ProfileId` / Profile name.
- `PermissionSetAssignment` export: `AssigneeId`, `PermissionSetId` / `PermissionSet.Name`, `PermissionSetGroupId`. Note that Profile-owned permission sets (`PermissionSet.IsOwnedByProfile = true`) also appear in such queries; exclude or label them.
- Setup screenshots of a user's assigned Permission Sets / Groups.
- The user's explicit statement that a persona is assigned a given set (treat as supplied requirement/evidence and say so).

Without one of these, phrase conclusions as "the `X` Permission Set grants…", not "the Technician user has…".
