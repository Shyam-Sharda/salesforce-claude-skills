# Test patterns by Apex type

Read only the sections that match the code types in your inventory. Each section says what to test, what not to force, and the platform behavior that trips people up. Snippets are shapes to adapt, not templates to paste; replace every object, field, and class name with what the supplied code actually uses.

## Contents

1. Any class (applies to everything)
2. Triggers and trigger handlers
3. Service and domain classes
4. @AuraEnabled controllers
5. Apex REST resources
6. Queueable
7. @future
8. Batch Apex
9. Schedulable
10. Invocable methods
11. Callouts
12. Security-sensitive code
13. Platform events and SOSL

---

## 1. Any class

- Test each public entry point at least once on its main success path, then add one test per meaningful branch or guard.
- Bulk-test only when the entry point accepts a collection or runs in a bulk context (trigger, batch, invocable, a method taking a `List`). Do not wrap a single-record API in a loop just to call it "bulk".
- Expected exceptions:

```apex
try {
    WorkOrderService.dispatch(null, techId);
    Assert.fail('Expected WorkOrderService.DispatchException for null work order');
} catch (WorkOrderService.DispatchException e) {
    Assert.isTrue(e.getMessage().contains('Work order'), 'Unexpected message: ' + e.getMessage());
}
```

- When production code catches an exception and recovers (logs, returns a default, adds an error), test the recovery: the logged record, the returned value, the `addError` message. Only do this when the failure can be triggered reliably from the test (bad input, a mock error response, a record deliberately missing a value). If it can only be triggered by a platform failure the test cannot cause, note it as a gap rather than faking it.
- Do not assert `Limits.getQueries()` counts by default. It couples the test to implementation. Use it only when the user asks for limit regression tests or the code's purpose is limit-sensitive.

## 2. Triggers and trigger handlers

- Read the trigger's declared contexts (`before insert`, `after update`, ...) and test only those. Do not write an undelete test for a trigger with no `after undelete`.
- Fire the trigger through DML, not by calling handler methods with hand-built `Trigger.new` lists. The trigger is the contract; the handler is an implementation detail. Exception: when the handler is a separate public service also called from elsewhere, test that service directly as well.
- For `update` logic with field-change conditions, insert records, change only the triggering field, update, then assert. Add one test where a non-triggering field changes and assert nothing happened, when the code has that condition.
- Bulk: insert or update 200 records in one DML to prove the logic handles a full chunk. Go above 200 (for example 201 or 250) only when the code holds static state across the transaction, such as a recursion flag or static cache. A DML of more than 200 records runs the trigger in multiple chunks of 200, and a static `hasRun` flag will silently skip records after the first chunk. That is a real bug class worth a test when the code has the flag.
- Recursion guards: when the code has one, test the scenario it protects (for example, the after-update handler updates the same records) and assert the outcome happened once, not twice.
- `addError`: use partial-success DML and assert on the error.

```apex
Database.SaveResult[] results = Database.insert(records, false);
Assert.isFalse(results[0].isSuccess(), 'Expected the record to be rejected');
Assert.isTrue(results[0].getErrors()[0].getMessage().contains('Close Date'),
    'Unexpected error: ' + results[0].getErrors()[0].getMessage());
```

- Do not assume other automation (flows, other triggers, validation rules) exists or does not exist. If an assertion could be affected by it, add **Cannot Verify**.

## 3. Service and domain classes

- Test the public methods directly with realistic inputs; assert database state and return values.
- If the method accepts IDs and queries records, test the "record not found" path only when the code handles it (empty-list check, `QueryException` catch). Otherwise do not invent it.
- If the class depends on an interface or injected collaborator, use a small stub (`implements` the interface inside the test class, or `System.StubProvider` when the project already uses it). Do not introduce a mocking framework the project does not have.

## 4. @AuraEnabled controllers

- Call the static method directly. There is no LWC in an Apex test; test only the Apex contract (parameters in, value or exception out).
- `AuraHandledException` messages: `getMessage()` returns `Script-thrown exception` unless the production code calls `setMessage(...)` on the exception. Assert on the message only when the code sets it; otherwise assert the exception type.

```apex
try {
    CaseController.closeCase(null);
    Assert.fail('Expected AuraHandledException');
} catch (AuraHandledException e) {
    // Only valid if production code calls ex.setMessage(...)
    Assert.areEqual('Case Id is required', e.getMessage(), 'Unexpected message');
}
```

- Assert DTO contents field by field for the values the UI depends on, not just non-null.
- `cacheable=true` methods cannot perform DML; do not write DML expectations for them.
- Security tests only when security is part of the method's own contract (`stripInaccessible`, explicit CRUD/FLS checks, a custom permission check, deliberate access-mode switching) or the user asks for them. `with sharing` or the API 67.0+ user-mode default alone is not a reason. See section 12.

## 5. Apex REST resources

Set up the request with only what the implementation reads:

```apex
RestRequest req = new RestRequest();
req.requestURI = '/services/apexrest/workorders/' + wo.Id;   // match the urlMapping
req.httpMethod = 'GET';
req.addHeader('Content-Type', 'application/json');            // only if the code reads it
req.requestBody = Blob.valueOf(JSON.serialize(payload));      // only for body-based methods
RestContext.request = req;
RestContext.response = new RestResponse();

Test.startTest();
WorkOrderResource.Result result = WorkOrderResource.doGet();
Test.stopTest();
```

- If the method returns a value, assert on the returned value directly. The platform's serialization into `RestContext.response.responseBody` does not happen in a unit test.
- If the method is `void` and writes `RestContext.response.statusCode` / `responseBody` itself, assert on those.
- Test each HTTP method the class declares. Test malformed or missing input only where the code handles it (a try/catch around `JSON.deserialize`, a null check, an explicit 400).
- Test idempotency or duplicate handling only when the code implements it (external ID upsert, a lookup before insert).

## 6. Queueable

- Enqueue between `Test.startTest()` and `Test.stopTest()`; the job runs synchronously at `stopTest()`. Assert the business outcome after `stopTest()`, not just that an `AsyncApexJob` exists.
- Any delay passed to `System.enqueueJob` is ignored in tests.
- **Chaining:** Queueable chaining is supported and is not inherently a defect. Current Salesforce releases support testing chained Queueables using appropriate stack depths (set through `AsyncOptions.MaximumQueueableStackDepth` on `System.enqueueJob(job, options)`), subject to the applicable async and Queueable limits.
  - When the code chains, determine whether the chain is deliberately finite, controlled by a terminating condition (for example, `AsyncInfo.hasMaxStackDepth()` / `getCurrentQueueableStackDepth()`, or running out of records), configured with an appropriate maximum depth, or potentially runaway.
  - Test the observable behavior of the chain (records processed across links, the terminating condition stopping it) when the supplied code and API version allow it.
  - Do not recommend adding `Test.isRunningTest()` to disable legitimate chaining for tests. Test-specific branches in production code hide real behavior.
  - An unbounded or incorrectly terminated chain is a production-code concern that affects the tests; report it once under the severity it earns (Urgent when it can run away in production). A normal parent-to-child chain is not a finding.
  - If the production code already contains a `Test.isRunningTest()` guard around the chain, the chained job will not run in the test; test the child Queueable by enqueuing it directly, and note the guard as a limitation.
- If the Queueable makes callouts (`Database.AllowsCallouts`), set the mock before `Test.stopTest()`, and follow "Async callouts" in section 11.
- Test the `Finalizer` only when the class attaches one; assert the finalizer's observable effect (a log record, a retry enqueue).

## 7. @future

- Call the method between `Test.startTest()` / `Test.stopTest()` and assert after `stopTest()`.
- `@future(callout=true)` needs a mock set before `stopTest()`.
- If the future method is called from a trigger, test it through the trigger DML, still inside start/stop.

## 8. Batch Apex

- **A normal test exercises a batch through one real `Database.executeBatch()` execution scope.** A test context allows a single batch execution, so keep the records returned by `start` at or below the scope size passed to `Database.executeBatch` (default 200). Test data that would produce multiple executions causes an error rather than exercising multiple scopes.
- End-to-end test: create records that match the `start` query (and some that should not, when the query filters), run `Database.executeBatch(new MyBatch(), 200)` inside start/stop, and assert the outcome on both sets.
- Do not claim that calling `execute()` manually several times reproduces real multi-scope behavior. Real scopes run in separate transactions, and `Database.Stateful` controls whether instance state persists between them; calling methods on one object in one test transaction does neither.
- When useful, direct calls to `execute()` on the same instance can unit-test the class's accumulation logic, provided `execute()` does not depend on `BatchableContext`. Label it in the test name and comment as a simulation of the calculation logic, not proof of `Database.Stateful` persistence.

```apex
// Simulates the accumulation logic across two scopes. Does NOT prove that
// Database.Stateful persists processedCount between real batch transactions.
MyBatch job = new MyBatch();
job.execute(null, firstScope);
job.execute(null, secondScope);
Assert.areEqual(firstScope.size() + secondScope.size(), job.processedCount, 'Accumulated count');
```

  If `execute` or `finish` reads `bc.getJobId()`, passing `null` will fail; test that path through a real `executeBatch` run instead.
- If correctness fundamentally depends on true multi-scope transaction behavior that the test context cannot reproduce, state that limitation in one line under the Test Plan.
- Partial-failure handling: when `execute` uses `Database.update(records, false)` and records failures, include a record that will fail for a reason the test controls (for example, a required lookup set to a deleted record, or an `addError` rule visible in supplied code) and assert the failure is recorded. If the only way to fail is org metadata you cannot see, mark **Cannot Verify**.
- `finish` that enqueues another job: assert the job was submitted (`AsyncApexJob` filtered by `ApexClass.Name`); a batch started from `finish` will not itself run in the test. `finish` that sends email or writes a log: assert the observable record when there is one, and otherwise note the email as untested rather than inventing a check.

## 9. Schedulable

- Use `System.schedule('Job name', cron, new MySchedulable())` inside start/stop when the scheduling entry point matters; the scheduled `execute` runs at `stopTest()`. Use a cron with a future year (for example `'0 0 0 1 1 ? 2099'`) so the date never becomes invalid.
- If `execute` only starts a batch or queueable, assert the job was submitted (`AsyncApexJob` filtered by `ApexClass.Name`) and test the batch's business behavior in the batch's own test. Async work started from inside the scheduled job will not run in the same test.
- If `execute` contains real logic and does not use the `SchedulableContext`, calling `new MySchedulable().execute(null)` directly is a simpler way to test that logic.
- Do not test cron expression trivia unless the class builds or parses cron strings.

## 10. Invocable methods

- Call the static `@InvocableMethod` directly with a `List` of request objects. Flow bulkifies interviews into one call, so include a test with several requests in one list when the method is meant to be called from record-triggered or scheduled flows.
- Assert the results list has one result per request, in the same order, with correct values.
- Test the `@InvocableVariable` required/optional handling only where the Apex code checks it; Flow enforces `required=true` itself.

## 11. Callouts

- Always set a mock. Real endpoints are never reachable from tests.

```apex
private class SuccessMock implements HttpCalloutMock {
    public HttpResponse respond(HttpRequest req) {
        Assert.areEqual('POST', req.getMethod(), 'Expected POST');   // only assert what the code sets
        HttpResponse res = new HttpResponse();
        res.setStatusCode(200);
        res.setHeader('Content-Type', 'application/json');
        res.setBody('{"id":"EXT-1","status":"accepted"}');            // shape taken from the parsing code
        return res;
    }
}
...
Test.setMock(HttpCalloutMock.class, new SuccessMock());
```

- Build the response body from what the production parsing code reads (the wrapper class, the JSON keys it accesses). If the parsing lives in an unsupplied class, the contract is **Cannot Verify**.
- Write one mock per response the code distinguishes (200, a handled 4xx/5xx, a body the code treats as invalid). If the code treats all non-200 the same, one failure mock is enough.
- When one transaction makes several different callouts, use a single mock that routes on `req.getEndpoint()`, or `MultiStaticResourceCalloutMock` if the project already uses static resources.
- SOAP (`WebServiceCallout`) uses `WebServiceMock` and `Test.setMock(WebServiceMock.class, ...)`.
- Create test data in `@TestSetup`. A callout after uncommitted DML in the same transaction throws `CalloutException`; if the production code itself does DML and then a callout, the test will surface that as a real defect. Report it rather than restructuring the test to hide it.
- Named Credentials referenced as `callout:Name` do not need to resolve under a mock, but the mock cannot prove the Named Credential exists. Mention it only if relevant.

### Async callouts (Queueable, @future, Batch)

- For async callout tests, prefer asserting the durable business outcome after `Test.stopTest()`.
- Validate request method, endpoint, headers, and payload inside `HttpCalloutMock.respond()` when practical.
- Avoid relying on mutable static test-class variables to carry observations across asynchronous transaction boundaries.
- When a chained job's request contains state such as an attempt number, prefer making the mock response conditional on that request state rather than on a mutable call counter.

## 12. Security-sensitive code

### Do not generate security tests by default

Do not add security tests merely because a class uses:

- `with sharing`
- `inherited sharing`
- user-mode database operations
- API-version security defaults

Generate a security test when security behavior is itself part of the supplied code's meaningful contract, such as:

- explicit `Security.stripInaccessible(...)`
- explicit CRUD/FLS describe checks
- explicit Custom Permission or authorization checks
- deliberate `USER_MODE` / `SYSTEM_MODE` switching
- sharing-sensitive behavior that the method is specifically responsible for
- an explicit security branch whose result the caller can observe
- the user specifically asks for security tests

For an otherwise simple CRUD/service class, do not automatically create any of the following just to prove that Salesforce platform security works:

- test Users
- Profile queries
- Permission Sets
- `ObjectPermissions`
- `FieldPermissions`
- `PermissionSetAssignment`
- `System.runAs`
- mixed-DML setup

If the class has no security-specific branch or contract, test the business behavior and stop.

Example:

```apex
public with sharing class AccountNameService {
    public static Account renameAccount(Id accountId, String newName) {
        if (accountId == null) {
            throw new AccountNameServiceException('Account Id is required.');
        }

        if (String.isBlank(newName)) {
            throw new AccountNameServiceException('A new account name is required.');
        }

        Account acct = [
            SELECT Id, Name
            FROM Account
            WHERE Id = :accountId
        ];

        acct.Name = newName.trim();
        update acct;
        return acct;
    }
}
```

The right plan is three tests: the success path (the trimmed name is returned and stored), the null-Id guard, and the blank-name guard. No security test is generated. `with sharing` and the API 67.0+ user-mode default are platform behavior here, not a branch or contract this method implements, so there are no Users, permission sets, `System.runAs` or mixed-DML setup. The access mode is not reported as an issue either. When the user does ask for security tests, the rest of this section says what each test can prove.

The rest of this section applies only when a security test is warranted under the rule above.

### API-version-aware security testing

Security defaults are versioned, so read the production class's API version (from its `-meta.xml`) before deciding what a security test can prove.

- **API 67.0 and later:**
  - database operations default to user mode;
  - object permissions, FLS, and record sharing are therefore enforced by default unless the code explicitly requests system mode;
  - classes without an explicit sharing declaration default to enforcing record sharing.
- **API 66.0 and earlier:**
  - database operations default to system mode;
  - do not assume CRUD/FLS enforcement unless the code explicitly implements it.
- Explicit `USER_MODE` or `SYSTEM_MODE` on a query or DML overrides the default; test what the code actually specifies.
- A plain `[SELECT Id, Name FROM Account]` in an API 67.0+ class already runs in user mode. Do not conclude "no security mechanism" just because `WITH USER_MODE` is absent.
- If the API version is not supplied and security behavior affects the test strategy, mark the effective access mode **Cannot Verify** rather than guessing. Note the effect on the test plan (for example, "the low-access user test expects a denial only if the class is API 67.0+").
- The API version of the class doing the database operation is what matters, not the test class's version.

### Security layers

Treat these as separate layers, each with its own test approach:

| Layer | Mechanism in code | How to test | What `System.runAs` alone proves |
| --- | --- | --- | --- |
| Record sharing | `with sharing`, `inherited sharing`; no declaration at API 67.0+; user-mode operations | `runAs` a user who does not own and has no share on the record; assert it is not returned or not updatable | Sharing, but only if the org-wide default is Private/Read Only, which is org metadata: **Cannot Verify** unless supplied |
| Object CRUD | Default user mode at API 67.0+, `WITH USER_MODE`, `AccessLevel.USER_MODE`, `isAccessible()/isCreateable()` describe checks | `runAs` a low-access user (with or without a test-created permission set) and assert the denial path | Nothing, if the operation runs in system mode (API 66.0 and earlier default, or explicit `SYSTEM_MODE`) without an explicit check |
| Field-level security | Default user mode at API 67.0+, `Security.stripInaccessible`, `WITH USER_MODE`, field describe checks | `runAs` a user without field access; assert the field is removed (`getRemovedFields()`) or the denial is raised | Nothing, if the operation runs in system mode with no explicit FLS mechanism |
| Business authorization | Custom Permission check, role/profile check in code | Assign or withhold the permission via a permission set and assert both outcomes | Only what the code checks |
| Apex class access | Profile/permission set class access | Not testable in a meaningful way from Apex; mention only if the user asks |

- `System.runAs` changes the running user and enforces record sharing for sharing-enforcing code, but it does not make system-mode operations respect CRUD/FLS. Only claim a CRUD/FLS test proves enforcement when the operation runs in user mode, by explicit mechanism or by the API 67.0+ default.
- User-mode queries on objects or fields the running user cannot access throw `QueryException`. For user-mode DML failures, confirm the exception type in the org before asserting a specific type; if unsure, catch `Exception` and assert on `e.getTypeName()` and message, and add a `// CANNOT VERIFY` note.
- Code whose only security behavior comes from its sharing declaration or the API-version default gets no security test (see "Do not generate security tests by default"). If such code is externally exposed and runs in system mode, that is a review finding, not a test to write; mention it in one line.
- At API 67.0+, the default user mode also affects ordinary tests: the running user in a test is the user who runs it (usually an admin), so happy-path tests normally pass, but tests that `runAs` a low-access user for other reasons (owner logic, queue assignment) may now hit access denials. Give such users the access the scenario needs through a test-created permission set.
- User and permission set setup patterns are in `test-data-and-dependencies.md`.

## 13. Platform events and SOSL

- Platform events published in a test are delivered when `Test.stopTest()` runs, or on `Test.getEventBus().deliver()`. Assert the subscriber's effect after delivery.
- SOSL returns nothing in tests unless you call `Test.setFixedSearchResults(new List<Id>{...})` before the search. Use it when the code under test runs SOSL.
