# Reading Flow Metadata XML

Use this when reading a `*.flow-meta.xml` file directly, or to interpret the parser's output. Tag names below are from the Metadata API `Flow` type. Older API versions and some features use slightly different shapes; when something is unfamiliar, describe what the XML shows rather than guessing what it means.

## Contents
- Top-level settings
- The start element and trigger configuration
- Element types
- Connectors and how to trace them
- Finding loop bodies
- Fault-capable elements
- Variables, resources, and references
- Common traps when reading

---

## Top-level settings

| Tag | Meaning |
|---|---|
| `<processType>` | `Flow` = Screen Flow. `AutoLaunchedFlow` = autolaunched, record-triggered, scheduled, or platform-event-triggered (the `<start>` element tells you which). Others exist (`Orchestrator`, `Workflow` for Process Builder, etc.). |
| `<status>` | `Active`, `Draft`, `Obsolete`, `InvalidDraft`. |
| `<runInMode>` | Explicit Flow execution context when configured. Common values include default and system modes. Available values can vary by API version. Do not assume the effective security context from this value alone when the Flow's launch mechanism can affect it. If a newer/unfamiliar value appears, report the literal metadata value and consult the Flow API version rather than guessing its meaning. |
| `<apiVersion>` | Flow's API version. Some runtime behavior depends on it. |
| `<label>`, `<description>` | Human name and author's description. Useful evidence of intent. |
| `<interviewLabel>` | Name pattern for paused/failed interviews. Not a defect source. |
| `<environments>` | Can indicate where the Flow runs (for example `Default`, or Slack-related values). |

## The start element and trigger configuration

Newer Flows have a `<start>` element. Older Flows use `<startElementReference>` pointing at the first element.

Inside `<start>`:

| Tag | Meaning |
|---|---|
| `<triggerType>` | `RecordBeforeSave`, `RecordAfterSave`, `RecordBeforeDelete`, `Scheduled`, `PlatformEvent`. Absent for screen and plain autolaunched Flows. |
| `<recordTriggerType>` | `Create`, `Update`, `CreateAndUpdate`, `Delete`. |
| `<object>` | Triggering object (record-triggered) or the object a scheduled Flow runs over. |
| `<filters>`, `<filterLogic>` | Entry conditions (`and`, `or`, or custom logic like `1 AND (2 OR 3)`). |
| `<filterFormula>` | Formula entry condition (used instead of `<filters>`). |
| `<doesRequireRecordChangedToMeetCriteria>` | `true` = "Only when a record is updated to meet the condition requirements". Absent/false on update triggers = runs on every qualifying save, even if nothing relevant changed. |
| `<connector>` | First element of the immediate path. |
| `<scheduledPaths>` | Scheduled or async paths. `<pathType>AsyncAfterCommit</pathType>` = "Run Asynchronously" path; others use `<offsetNumber>`, `<offsetUnit>`, `<timeSource>`, `<recordField>`. Each has its own `<connector>`. |
| `<schedule>` | For scheduled-triggered Flows: `<frequency>`, `<startDate>`, `<startTime>`. |

Entry criteria filters use `<field>`, `<operator>` (`EqualTo`, `IsChanged`, `IsNull`, ...), and `<value>`.

## Element types

Each element has a `<name>` (API name, used in connectors), a `<label>`, optional `<description>`, and `<locationX>`/`<locationY>` (canvas position: ignore for review purposes).

| Tag | Builder name | Notes for review |
|---|---|---|
| `<recordLookups>` | Get Records | `<object>`, `<filters>`, `<getFirstRecordOnly>`, `<storeOutputAutomatically>` or `<outputReference>`/`<outputAssignments>`, `<queriedFields>`, `<sortField>`/`<sortOrder>`, `<assignNullValuesIfNoRecordsFound>`, `<faultConnector>`. SOQL query. |
| `<recordCreates>` | Create Records | `<inputReference>` (a record or collection variable) or `<object>` + `<inputAssignments>`. DML. |
| `<recordUpdates>` | Update Records | `<inputReference>` (variable, often `$Record`) or `<object>` + `<filters>` + `<inputAssignments>`. Performs DML in Flow types that support the element. In a before-save record-triggered Flow, changes to the triggering record are normally made directly to `$Record` with Assignment and are saved automatically; do not treat that as an Update Records DML operation. |
| `<recordDeletes>` | Delete Records | `<inputReference>` or `<object>` + `<filters>`. DML. |
| `<recordRollbacks>` | Roll Back Records | Rolls back pending changes in the current transaction. |
| `<assignments>` | Assignment | `<assignmentItems>` with `<assignToReference>`, `<operator>` (`Assign`, `Add`, ...), `<value>`. No database cost. |
| `<decisions>` | Decision | `<rules>` (each an outcome with `<conditions>`, `<conditionLogic>`, `<connector>`), plus `<defaultConnector>` and `<defaultConnectorLabel>`. Rules are evaluated in order; the first match wins. |
| `<loops>` | Loop | `<collectionReference>`, `<iterationOrder>`, `<nextValueConnector>` (into the body), `<noMoreValuesConnector>` (after the loop). |
| `<collectionProcessors>` | Collection Sort / Filter | In-memory; no database cost. |
| `<transforms>` | Transform | In-memory mapping. |
| `<actionCalls>` | Action | `<actionType>` (`apex`, `emailSimple`, `emailAlert`, `submit`, `chatterPost`, `quickAction`, `externalService`, `generatePromptResponse`, `flow`, and others) and `<actionName>` (for `apex`, the class name). What it does internally is not visible unless its implementation is supplied. |
| `<apexPluginCalls>` | Legacy Apex plug-in | Treat like an Apex action. |
| `<subflows>` | Subflow | `<flowName>`, `<inputAssignments>`, `<outputAssignments>`. Contents are a separate Flow file. |
| `<screens>` | Screen | `<fields>` (with `<fieldType>`, `<isRequired>`, `<validationRule>`), `<allowBack>`, `<allowFinish>`, `<allowPause>`, `<showFooter>`. |
| `<waits>` | Pause / Wait | Pauses the interview; resumes in a new transaction. |
| `<customErrors>` | Custom Error | Record-triggered Flows: shows an error on the record/field and blocks the save. |
| `<formulas>`, `<variables>`, `<constants>`, `<textTemplates>`, `<choices>`, `<dynamicChoiceSets>` | Resources | Not executed as steps, but referenced by steps. |
| `<orchestratedStages>`, `<steps>` | Orchestrator | Review structure only at a high level unless asked. |

## Connectors and how to trace them

Every connector is `<targetReference>ElementName</targetReference>` inside one of:

- `<connector>`: normal next step (most elements; also each decision rule).
- `<defaultConnector>`: decision default outcome, wait default.
- `<faultConnector>`: path taken when the element errors.
- `<nextValueConnector>` / `<noMoreValuesConnector>`: loop body entry and loop exit.
- `<start><connector>` and `<start><scheduledPaths><connector>`: entry points.

An element with no outgoing connector ends that path. A decision outcome with no connector also ends the path. Newer API versions can mark a connector with `<isGoTo>true</isGoTo>` (a "Go To" jump back to an earlier element): this can create cycles outside a Loop element, so check whether such a cycle has a condition that eventually ends it.

## Finding loop bodies

The body of a loop is every element reachable from its `<nextValueConnector>` that eventually connects back to the loop element. The loop element itself is not in the body. Nested loops are inside the outer body. Anything in the body runs once per item in `<collectionReference>`.

Elements reachable from the body that end the Flow without returning (for example, a fault path that logs and stops) run at most once per interview but can still run per item until the first failure.

## Fault-capable elements

These accept a `<faultConnector>`: `recordLookups`, `recordCreates`, `recordUpdates`, `recordDeletes`, `actionCalls`, `apexPluginCalls`, `subflows`. When no fault connector exists and the element fails, the interview fails: in a record-triggered Flow the triggering save fails with an error to the user or integration; in a Screen Flow the user sees a generic error; in an autolaunched Flow the caller receives the failure. Whether that is acceptable depends on the Flow (see the checklists).

`{!$Flow.FaultMessage}` holds the error text in a fault path. A fault path that doesn't record or surface it usually loses the useful context.

## Variables, resources, and references

- `{!varName}`, `{!varName.Field__c}`, `{!$Record.Field}`, `{!$Record__Prior.Field}` (prior values in update-triggered Flows).
- `<isInput>true</isInput>` / `<isOutput>true</isOutput>` on variables: values that callers can pass in or read. For Screen Flows launched from a record page, `recordId` is commonly an input.
- `<isCollection>true</isCollection>` and `<dataType>SObject</dataType>` with `<objectType>` for record collections.
- `$Label`, `$Setup`, `$Permission`, `$User`, `$Profile`, `$UserRole` global variables in formulas and conditions.

## Common traps when reading

- `locationX`/`locationY` and element order in the file say nothing about execution order. Only connectors do.
- Elements in the file are grouped by type, not by execution order.
- A Get Records with `<getFirstRecordOnly>true</getFirstRecordOnly>` stores one record (or null). Without it, a collection (possibly empty).
- `storeOutputAutomatically` affects how the result is stored; don't claim it retrieves every field on the object. Which fields the runtime queries has varied across releases, so treat over-fetching as a concern only when `<queriedFields>` visibly lists fields that are never used.
- A Decision rule's `<conditionLogic>` can be `and`, `or`, or a custom expression; check that custom logic references the right condition numbers.
- Record-triggered Flows: `$Record` is the triggering record. In before-save, Assignments to `$Record` fields are saved without extra DML.
