# Debug Event Guide

How to read the event families that matter for runtime diagnosis, and what each one does and does not establish. Exact field layouts vary slightly by API version and log level; read the fields that are actually present rather than assuming positions.

## Contents
1. Line anatomy and the header
2. Code units
3. Method and constructor events
4. SOQL / SOSL
5. DML
6. Exceptions and fatal errors
7. Flow events
8. Callouts
9. Governor usage blocks
10. Async and entry-point markers
11. USER_DEBUG
12. Truncation and missing detail

## 1. Line anatomy and the header

```
14:32:08.315 (315123456)|SOQL_EXECUTE_BEGIN|[42]|Aggregations:0|SELECT Id FROM Contact WHERE Id = :tmpVar1
```

- `14:32:08.315` wall-clock time; `(315123456)` nanoseconds since the transaction began. The nanosecond value is the reliable way to measure elapsed time between two events.
- Event type, then pipe-separated fields.
- `[42]` is the source line in the class or trigger currently executing. It is not a log line number. Combine it with the enclosing method or code unit to locate the code.
- Lines without a timestamp prefix are continuations of the previous event: multi-line debug messages, stack trace lines after `FATAL_ERROR`, and the body of limit blocks.

The first line is usually a header such as `60.0 APEX_CODE,FINEST;APEX_PROFILING,INFO;CALLOUT,INFO;DB,INFO;...`. It gives the API version of the log and the log levels per category. Treat that version as log/runtime context (log format, available event structure); it does not establish the compile/API version of each Apex class or trigger in the transaction, which comes from that component's `.cls-meta.xml` or `.trigger-meta.xml`. Low levels mean some events were never recorded, so absence of an event type is weak evidence that it did not happen.

## 2. Code units

`CODE_UNIT_STARTED` / `CODE_UNIT_FINISHED` bracket each entry point: a trigger event (`WorkOrderTrigger on WorkOrder trigger event BeforeUpdate`), a Flow, a validation pass, an `@AuraEnabled` method, a Queueable `execute`, anonymous Apex, and so on.

Establishes: what ran, in what order, and how units nest. A trigger code unit opening inside another trigger's DML is direct evidence of re-entry. The same trigger opening several times in sequence for one DML usually means the platform chunked records (typically 200 per chunk) rather than recursion; check whether each opening follows a separate DML from your own code or the same original operation.

Does not establish: why a unit ran. Combine with the preceding `DML_BEGIN` to see which operation caused it.

## 3. Method and constructor events

`METHOD_ENTRY` / `METHOD_EXIT`, `CONSTRUCTOR_ENTRY` / `CONSTRUCTOR_EXIT`, with `[line]` of the call site and the method signature.

Establishes: the call path, and how many times a method ran. A method entered repeatedly from the same call site, followed by the same query each time, is the strongest per-record-processing evidence a log can give; the exact loop structure is confirmed only by source.

Does not establish: arguments or return values. These events disappear at lower `APEX_CODE` levels, so a log without them may still contain loops you cannot see; rely on repeated SOQL/DML signatures and `[line]` markers instead, and say the call path is inferred.

## 4. SOQL / SOSL

`SOQL_EXECUTE_BEGIN|[line]|Aggregations:N|<query>` then `SOQL_EXECUTE_END|[line]|Rows:N`. SOSL uses `SOSL_EXECUTE_BEGIN/END`.

Establishes: each query execution, its source line, and rows returned. The query text shows bind variables (`:tmpVar1`), not values. The same query text at the same `[line]` repeating is a repeated query signature.

`SOQL_EXECUTE_END|Rows:0` immediately before a query-related exception can strongly support an empty-result diagnosis when the source line, stack trace, variable assignment, method context, or supplied source connects that query to the failing value.

Do not treat temporal proximity alone as proof that the empty query caused a later null dereference.

For `System.QueryException: List has no rows for assignment to SObject`, a corresponding zero-row single-record query is much stronger evidence because the exception directly describes that query behavior.

For a general `NullPointerException`, establish the connection before calling the empty query the root cause.

Does not establish: why the query returned what it did (sharing, data, filters). Record visibility and data contents are **Cannot Verify** unless logged.

## 5. DML

`DML_BEGIN|[line]|Op:Update|Type:Account|Rows:N` then `DML_END|[line]`.

Establishes: operation, object, row count, and source line. Automation fired by the DML (triggers, validation, Flows, duplicate rules, workflow, assignment rules) appears between `DML_BEGIN` and `DML_END`. A failure inside that window is the inner cause of any `DmlException` that follows.

Related: `VALIDATION_RULE`, `VALIDATION_FORMULA`, `VALIDATION_FAIL`, `VALIDATION_ERROR` show validation evaluation when the validation category is logged. `DUPLICATE_DETECTION_*` events show duplicate rules.

## 6. Exceptions and fatal errors

- `EXCEPTION_THROWN|[line]|<type>: <message>` is recorded when an exception is thrown, whether or not it is later caught. Several can appear for one failure as it propagates or is rethrown.
- `FATAL_ERROR|<type>: <message>` followed by stack trace lines (`Class.Service.method: line 15, column 1`, `Trigger.WorkOrderTrigger: line 3, column 1`) means it was unhandled and the transaction failed.

An `EXCEPTION_THROWN` with no `FATAL_ERROR` and the transaction continuing means the code caught it. That can still matter (swallowed failures, partial work), but it is not the terminal error.

For `DmlException`, read the whole message: `first error: <STATUS_CODE>, <message>: [fields]`. The status code (`FIELD_CUSTOM_VALIDATION_EXCEPTION`, `CANNOT_EXECUTE_FLOW_TRIGGER`, `UNABLE_TO_LOCK_ROW`, `DUPLICATE_VALUE`, `REQUIRED_FIELD_MISSING`, `INVALID_OR_NULL_FOR_RESTRICTED_PICKLIST`, `INSUFFICIENT_ACCESS_*`, `MIXED_DML_OPERATION`) names the inner failure category.

## 7. Flow events

Typical sequence: `FLOW_CREATE_INTERVIEW_BEGIN/END` (names the Flow), `FLOW_START_INTERVIEWS_BEGIN`, `FLOW_START_INTERVIEW_BEGIN`, then per element `FLOW_ELEMENT_BEGIN|<interview>|<element type>|<element API name>` and `FLOW_ELEMENT_END`, with detail events such as `FLOW_ASSIGNMENT_DETAIL`, `FLOW_VALUE_ASSIGNMENT`, `FLOW_RULE_DETAIL`, `FLOW_ACTIONCALL_DETAIL`, `FLOW_BULK_ELEMENT_*`. Failures show as `FLOW_ELEMENT_ERROR` and `FLOW_ELEMENT_FAULT`, and interviews end with `FLOW_START_INTERVIEW_END` / `FLOW_INTERVIEW_FINISHED`.

Establishes: which Flow ran, which element ran last, which element failed and its error message, and sometimes logged input/output values. Apex invoked from a Flow element appears as nested Apex events or a code unit inside that element; follow it to find the deepest exception.

Bulkified Flow elements (`FLOW_BULK_ELEMENT_*`) may execute once for many interviews; count element executions before calling something a per-record query.

Does not establish: the Flow's full design, fault connectors that were not taken, or entry criteria. Without Flow metadata, these are **Cannot Verify**.

## 8. Callouts

`CALLOUT_REQUEST|[line]|System.HttpRequest[Endpoint=..., Method=POST]` and `CALLOUT_RESPONSE|[line]|System.HttpResponse[Status=..., StatusCode=500]`. Named credentials and external services may also log `NAMED_CREDENTIAL_*` events.

Establishes: endpoint, method, status, and timing between request and response (use the nanosecond values). An exception immediately after a non-2xx response often means the code parsed an error body as success.

`System.CalloutException: You have uncommitted work pending` is direct evidence of DML before a callout in the same transaction; find the earlier `DML_BEGIN`.

Headers or bodies may contain secrets. Redact them when quoting.

## 9. Governor usage blocks

`LIMIT_USAGE_FOR_NS|(default)|` (or a namespace) followed by lines like:

```
  Number of SOQL queries: 101 out of 100 ******* CLOSE TO LIMIT
  Number of query rows: 1840 out of 50000
  Maximum CPU time: 2310 out of 10000
```

Usually inside `CUMULATIVE_LIMIT_USAGE` ... `CUMULATIVE_LIMIT_USAGE_END`. Managed-package namespaces get their own blocks and their own limits; report usage per namespace rather than summing.

Establishes: actual usage against the maximum that applied to this transaction. Prefer these figures to remembered limits. The platform's `CLOSE TO LIMIT` marker is a useful signal but not a finding by itself. `LIMIT_USAGE` (without `_FOR_NS`) lines report usage at a point in time.

## 10. Async and entry-point markers

`EXECUTION_STARTED` / `EXECUTION_FINISHED` bracket the whole transaction. The first code unit names the entry point: a trigger event, `[EXTERNAL]|VF: /apex/...`, an `@AuraEnabled` controller, `ApexRestService`, a Queueable class's execute, a Batch `start`/`execute`/`finish`, `FutureHandler`, a Schedulable, anonymous Apex (`execute_anonymous_apex`), a Platform Event subscriber.

`System.enqueueJob`, `Database.executeBatch` and `@future` calls in one log start a separate transaction with a separate log. A job Id returned or logged in the parent and visible in the child is the evidence that connects them.

## 11. USER_DEBUG

`USER_DEBUG|[line]|DEBUG|<message>` is whatever the developer chose to print. Useful for logged values and for understanding intent. It is not a platform fact: a message claiming success does not prove success. Check it against SOQL rows, DML events and exceptions around it.

## 12. Truncation and missing detail

Indicators: `*** Skipped N bytes of detailed log`, `MAXIMUM DEBUG LOG SIZE REACHED`, the log starting after the entry point or ending before `EXECUTION_FINISHED`, code units with no matching finish. Analyze what is present and state what the gap prevents you from confirming.

Missing event families (no METHOD events, no Flow detail, no validation events) usually mean the log levels in the header were too low. Recommend raising the specific category only if it would settle an open question.
