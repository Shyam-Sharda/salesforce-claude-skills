# Test data and dependencies

Tests run in the real org's schema and automation but, without `@SeeAllData=true`, see almost none of its data. This file says what a test can create, what it can only read, what it cannot touch, and how to handle each with or without **Cannot Verify**. Note that "cannot be created in a test" is not a reason for `@SeeAllData=true`: several of the read-only items below (Custom Metadata, record types, profiles) are already visible to tests.

## Contents

1. Minimum data principle
2. What a test can and cannot see or create
3. Required fields, validation rules, and other automation
4. Users, profiles, permission sets, and mixed DML
5. Record types, Custom Metadata, Custom Settings
6. Other common dependencies
7. Organizing data setup
8. Cannot Verify examples

---

## 1. Minimum data principle

Create the smallest data set that drives each path you traced: the fields the code reads or filters on, the parent records lookups require, and, for filtered queries, at least one record that should match and one that should not. Do not populate fields the code never touches, except fields you know are required (see section 3).

## 2. What a test can and cannot see or create

| Thing | Visible without SeeAllData? | Can the test create it? | Notes |
| --- | --- | --- | --- |
| Ordinary records (Account, custom objects) | No | Yes | Create everything the test needs |
| User, Profile, PermissionSet, Group/Queue | Yes (setup objects) | Users, permission sets, groups, queues: yes. Profiles: no | Watch mixed DML (section 4) |
| Record types | Yes (via describe) | No | Org metadata; reference by developer name |
| Custom Metadata records | Yes | No (no DML on CMDT) | Values come from whatever is deployed to the org |
| Custom Settings data | No | Yes | Insert the values the code needs |
| Standard Pricebook | Id only | No | `Test.getStandardPricebookId()` |
| Organization, ApexClass, CronTrigger, AsyncApexJob | Yes | No | Fine to query |
| Static resources | Yes | No | `Test.loadData` can load CSV data from one |

## 3. Required fields, validation rules, and other automation

Validation rules, duplicate rules, required fields, flows, other triggers, and managed package automation all run in tests. None of them are visible from Apex source.

- Populate required fields that are visible in the supplied code or metadata, plus the platform-required ones you know such as `Account.Name`, `Contact.LastName`, and `Opportunity.Name`, `StageName`, `CloseDate`. `User` has several; see section 4.
- For custom objects, fill only fields evidenced in the supplied files. If insert success depends on fields you cannot see, add **Cannot Verify** and a `// CANNOT VERIFY:` comment at the insert.
- Picklist values: use only values that appear in supplied code or metadata. A restricted picklist rejects unknown values.
- If an assertion could be changed by automation you cannot see (for example, a flow that also updates the field you assert), note **Cannot Verify** once rather than on every test.

## 4. Users, profiles, permission sets, and mixed DML

Create users only when the code's own contract depends on the running user (owner logic, queue assignment, an explicit CRUD/FLS or Custom Permission check, deliberate access-mode switching, sharing-sensitive behavior the method is responsible for), or when the user asks for security tests. A sharing declaration or the API 67.0+ user-mode default alone is not a reason; see "Do not generate security tests by default" in `test-patterns-by-apex-type.md`. Remember that a low-access user running API 67.0+ code needs object and field access for every operation in the scenario, not just the one being tested.

```apex
private static User createUser(String profileName) {
    Profile p = [SELECT Id FROM Profile WHERE Name = :profileName LIMIT 1];
    String unique = String.valueOf(Datetime.now().getTime()) + Crypto.getRandomInteger();
    return new User(
        ProfileId = p.Id,
        LastName = 'Tester',
        Alias = 'tstr',
        Email = 'tester@example.com',
        Username = 'tester' + unique + '@example.com.test',
        TimeZoneSidKey = 'America/Los_Angeles',
        LocaleSidKey = 'en_US',
        EmailEncodingKey = 'UTF-8',
        LanguageLocaleKey = 'en_US'
    );
}
```

- Usernames must be unique across all Salesforce orgs, hence the timestamp.
- Profile names can be renamed or localized. `Minimum Access - Salesforce` is the usual low-access starting point; `Standard User` is common but not guaranteed. If the code's behavior depends on a specific custom profile, that is **Cannot Verify** unless supplied.
- Prefer granting access through a permission set the test creates, so the test controls exactly what the user can do:

```apex
PermissionSet ps = new PermissionSet(Name = 'Test_WO_Access', Label = 'Test WO Access');
insert ps;
insert new ObjectPermissions(ParentId = ps.Id, SobjectType = 'Work_Order__c',
    PermissionsRead = true, PermissionsCreate = true);
insert new FieldPermissions(ParentId = ps.Id, SobjectType = 'Work_Order__c',
    Field = 'Work_Order__c.Priority__c', PermissionsRead = true, PermissionsEdit = false);
insert new PermissionSetAssignment(AssigneeId = u.Id, PermissionSetId = ps.Id);
```

  When the code depends on an existing permission set from the project, query it by `Name` instead, and mark it **Cannot Verify** if it was not supplied.
- Custom Permissions cannot be created in a test. If the code checks `FeatureManagement.checkPermission('X')`, the custom permission must exist in the org; assign it through a permission set by inserting a `SetupEntityAccess` row (`ParentId` = permission set, `SetupEntityId` = the `CustomPermission` Id queried by `DeveloperName`). Mark **Cannot Verify** if the custom permission's metadata was not supplied.
- **Mixed DML:** inserting setup objects (User, PermissionSet, PermissionSetAssignment, Group, GroupMember, QueueSobject) and ordinary records in the same transaction throws `MIXED_DML_OPERATION`. Wrap the setup-object DML in its own `System.runAs` block:

```apex
User u = createUser('Minimum Access - Salesforce');
System.runAs(new User(Id = UserInfo.getUserId())) {
    insert u;
    // permission set and assignment inserts here
}
```

## 5. Record types, Custom Metadata, Custom Settings

**Record types** cannot be created in tests. Reference them by developer name through describe, never by hardcoded Id:

```apex
Id rtId = Schema.SObjectType.Case.getRecordTypeInfosByDeveloperName()
    .get('Field_Service').getRecordTypeId();
```

If the developer name appears in supplied code or metadata, use it. Otherwise **Cannot Verify**.

**Custom Metadata** cannot be inserted. Tests read whatever records are deployed to the org, so a test that depends on a CMDT value is coupled to org configuration.
- If the CMDT records are supplied (`customMetadata/*.md-meta.xml`), the test may rely on them; say so.
- If the production code exposes an override (for example, a `@TestVisible` static list or an injectable settings provider), set it in the test with in-memory records.
- Otherwise mark **Cannot Verify** and propose a small injectable seam under Suggested Changes. Do not add one to production code yourself, and do not reach for `@SeeAllData=true`: deployed CMDT records are visible without it.

**Custom Settings** are data. Insert exactly the values the code reads (hierarchy: org default via `SetupOwnerId = UserInfo.getOrganizationId()`; list settings by `Name`). Do not insert settings the code never reads.

## 6. Other common dependencies

- **Queues:** a test can create a `Group` with `Type = 'Queue'` plus a `QueueSobject` for the object (setup DML, so use the runAs block). If the code looks up an existing queue by developer name, create one with that name in the test when the name is visible in the code.
- **Products and pricebooks:** use `Test.getStandardPricebookId()` for the standard `PricebookEntry` before creating custom pricebook entries.
- **Dates and times:** compute dates relative to `Date.today()`. If the code's behavior depends on `Datetime.now()` with no seam, note that boundary conditions cannot be tested deterministically.
- **Org-dependent settings** (multi-currency, person accounts, territory management, state/country picklists): only rely on them when supplied evidence shows they are enabled. Otherwise **Cannot Verify**.
- **Unsupplied Apex classes the code calls:** test the supplied code's behavior around them. Do not guess what they return; if the outcome depends on their result, **Cannot Verify**.

## 7. Organizing data setup

| Situation | Approach |
| --- | --- |
| A few tests, little shared data | Build data inside each test or a private static helper |
| Several tests genuinely share meaningful base data, and centralizing it keeps each scenario readable | `@TestSetup`, then query the records in each test |
| Records specific to one scenario | Create them in that test, even when other tests use `@TestSetup` |
| Project already has a factory (`TestDataFactory`, `TestUtils`, ...) | Use it, and its conventions, if supplied. If it is referenced but not supplied, do not guess its method signatures: **Cannot Verify**, or build data locally |
| Many objects with deep parent chains reused across several test classes | Propose a factory under Suggested Changes; do not create one unasked |

`@TestSetup` data is rolled back and re-created per test method, so tests do not leak into each other. Static variables set in `@TestSetup` do not carry into test methods; query instead.

## 8. Cannot Verify examples

Phrase each one as unknown, impact, and what would settle it:

- **Cannot Verify**: required fields and validation rules on `Invoice__c`. The `@TestSetup` insert populates only fields referenced in `InvoiceService`, so it may fail in your org. The object's field metadata or a test run would settle it.
- **Cannot Verify**: the active `Dispatch_Settings__mdt` record values. `DispatchService.isEnabled()` reads them, so the happy-path test assumes the feature is enabled. Supplying the CMDT record files, or a test override in the class, would settle it.
- **Cannot Verify**: the response format of the ERP API. The parsing happens in `ErpClient`, which was not supplied, so the callout mocks cannot be shaped correctly. `ErpClient.cls` would settle it; the success and failure callout tests are skipped until then.
- **Cannot Verify**: the API version of `WorkOrderService`. Its queries have no explicit access mode, so they run in user mode at API 67.0+ and system mode at 66.0 and earlier. The low-access-user test the user asked for expects a denial only under user mode. `WorkOrderService.cls-meta.xml` would settle it.
- **Cannot Verify**: the org-wide default for `Work_Order__c`. The sharing test only proves anything if the default is Private or Read Only. Supply the object's sharing model, or confirm it.
