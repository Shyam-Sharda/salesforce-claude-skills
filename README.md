# Salesforce Claude Skills

A collection of reusable Claude Skills for Salesforce development, code review, testing, debugging, Flow analysis, and security auditing.

These skills are designed to give Claude structured Salesforce-specific reasoning rather than relying on a generic prompt each time. Each skill focuses on a specific development task, uses evidence from the files supplied, avoids inventing missing Salesforce configuration, and returns concise, actionable results.

## Skills

### 1. Salesforce Apex Code Reviewer

Reviews Apex classes, triggers, controllers, services, and asynchronous code for meaningful technical issues.

Focuses on:

- correctness and runtime risks
- governor-limit concerns
- bulkification
- security and execution context
- maintainability where it has a concrete impact
- Salesforce-specific Apex patterns
- evidence-based findings without inventing missing metadata

Example:

```text
/salesforce-apex-code-reviewer review this Apex class
```

Folder:

```text
salesforce-apex-code-reviewer/
```

---

### 2. Salesforce Apex Test Generator

Analyzes production Apex and generates behavior-focused test classes based on the actual code paths and dependencies supplied.

Focuses on:

- meaningful test scenarios rather than coverage alone
- positive and negative paths
- triggers and DML behavior
- Queueable, Batch, Schedulable and future Apex
- callout mocks
- REST and Aura-enabled entry points
- bulk behavior where relevant
- missing dependencies and `Cannot Verify` cases
- assertions that prove observable behavior

Example:

```text
/salesforce-apex-test-generator generate tests for this Apex class
```

Folder:

```text
salesforce-apex-test-generator/
```

---

### 3. Salesforce Debug Log Analyzer

Analyzes Salesforce debug logs and reconstructs the runtime path that caused a failure or performance issue.

Focuses on:

- exceptions and fatal errors
- root cause versus wrapper errors
- SOQL and DML repetition
- governor-limit failures
- Flow and Apex interactions
- callouts
- asynchronous execution
- recursion and repeated execution patterns
- CPU and heap usage
- successful transactions without manufacturing issues

Includes a deterministic Python helper for inventorying large debug logs before Claude performs the diagnosis.

Example:

```text
/salesforce-debug-log-analyzer analyze this debug log
```

Folder:

```text
salesforce-debug-log-analyzer/
```

---

### 4. Salesforce Flow Reviewer

Reviews Salesforce Flow metadata by reconstructing the Flow from its XML rather than relying on element order.

Focuses on:

- execution paths and connectors
- record-triggered Flow behavior
- before-save versus after-save logic
- DML and actions inside repeated paths
- recursion and re-entry risks
- fault handling
- subflows and Apex actions
- bulk behavior
- unreachable or dangling elements
- Flow-specific maintainability issues

Includes a deterministic Python helper that inventories Flow XML and reconstructs its execution graph.

Example:

```text
/salesforce-flow-reviewer review this Flow
```

Folder:

```text
salesforce-flow-reviewer/
```

---

### 5. Salesforce Security & Permission Auditor

Audits Salesforce access configuration across multiple security layers and identifies missing or excessive permissions.

Focuses on:

- object CRUD
- field-level security
- Permission Sets
- Permission Set Groups
- Muting Permission Sets
- Profiles
- Apex class access
- Flow access
- Custom Permissions
- Record Types
- record-level sharing when sufficient evidence is supplied
- Experience Cloud access
- least-privilege mismatches against supplied persona requirements

The skill keeps Salesforce security layers separate rather than assuming that one permission proves another.

Includes a deterministic Python helper for comparing Salesforce security metadata and resolving Permission Set Groups with muting.

Example:

```text
/salesforce-security-permission-auditor audit the supplied files
```

Folder:

```text
salesforce-security-permission-auditor/
```

## Repository Structure

```text
salesforce-claude-skills/
│
├── salesforce-apex-code-reviewer/
│   ├── SKILL.md
│   └── references/
│
├── salesforce-apex-test-generator/
│   ├── SKILL.md
│   └── references/
│
├── salesforce-debug-log-analyzer/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
│
├── salesforce-flow-reviewer/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
│
└── salesforce-security-permission-auditor/
    ├── SKILL.md
    ├── references/
    └── scripts/
```

Each skill is self-contained.

`SKILL.md` defines the skill's purpose, workflow, reasoning rules, scope, and output format.

`references/` contains focused Salesforce-specific guidance used by the skill when deeper context is required.

`scripts/` contains deterministic helpers for tasks that benefit from mechanical parsing, such as Flow XML, debug logs, and security metadata. The scripts extract facts; Claude performs the actual reasoning and recommendations.

## Design Principles

The skills follow a few common principles:

- **Evidence first** — do not invent Salesforce metadata, configuration, permissions, dependencies, or business requirements.
- **Cannot Verify** — clearly identify when missing information prevents a reliable conclusion.
- **Salesforce-specific reasoning** — distinguish concepts such as CRUD, FLS, sharing, Apex class access, execution mode, Flow context, and Custom Permissions.
- **Smallest fix** — recommend the minimum change necessary rather than redesigning an application by default.
- **Concise results** — focus on what is wrong, what should change, and what genuinely cannot be verified.
- **Clean results are valid** — do not manufacture findings when the supplied implementation is already correct.
- **Clear skill boundaries** — Apex review, testing, Flow analysis, runtime debugging, and security auditing remain separate responsibilities.

## Typical Output

Most review-oriented skills use a compact format such as:

```text
## What This Code / Flow / Configuration Does

## Urgent - Needs Attention

## Warning - Should Change

## Suggested Changes

## Cannot Verify
```

Sections are kept short and are omitted or marked as clear when there is nothing meaningful to report.

## Using the Skills

Add the desired skill folder to your Claude Skills environment and invoke the skill while supplying the relevant Salesforce files.

For example:

```text
/salesforce-apex-code-reviewer review this class
```

```text
/salesforce-flow-reviewer review the supplied Flow
```

```text
/salesforce-debug-log-analyzer analyze this log
```

```text
/salesforce-security-permission-auditor audit the supplied files
```

The skills are intentionally designed so that short prompts are usually enough. The detailed Salesforce-specific instructions live inside each skill rather than needing to be repeated in every request.

## Testing

Each skill is tested against deliberately different fixtures, including:

- broken or risky implementations
- clean implementations
- incomplete dependency scenarios
- missing configuration
- Salesforce-specific edge cases

The goal is not only to confirm that a skill can find problems, but also that it can recognize when there is **no meaningful problem to report**.

## Roadmap

The current repository contains five general-purpose Salesforce skills.

Planned additions include more application-specific Salesforce skills built around real service-management workflows, including:

- workflow generation
- service-case generation
- workflow auditing
- architecture-aware Salesforce automation

These will build on the same evidence-first and concise-output principles used by the current skills.

## About

This project is part of my work exploring how Claude Skills can be used to create repeatable, Salesforce-aware development workflows around Apex, Flow, testing, runtime debugging, and platform security.

The goal is to move common Salesforce engineering tasks from one-off AI prompts into reusable skills with consistent reasoning rules, clear boundaries, and predictable outputs.
