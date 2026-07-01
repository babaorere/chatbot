# AGENTS.md — Unified Operating Contract

## Purpose

This file is the single operational contract for AI agents working with these projects.

It replaces fragmented prompt files and defines one unambiguous source for:
- context
- scope
- decision rules
- prohibitions
- execution discipline

---

## Operational Modes

There are only two valid modes.

### Mode A — Active Project Mode
The current shell working directory is the active project.

Use this mode by default.

Rules:
- Read and modify only the active project.
- Do not treat external projects as editable unless explicitly requested.
- Use external systems only as reference context.

### Mode B — SkillOS Reference Mode
SkillOS is a reference architecture and policy system, not the active target, unless the user explicitly says to work on SkillOS itself.

SkillOS reference paths:
- Root: `/home/manager/Sync/python_proyects/skillos/SkillOS-work/SkillOS-unified`
- Master prompt: `/home/manager/Sync/python_proyects/skillos/SKILLOS-MASTER-PROMPT.md`
- Install guide: `/home/manager/Sync/python_proyects/skillos/FINAL-INSTALL-GUIDE.txt`
- Merge map: `/home/manager/Sync/python_proyects/skillos/MERGE-MAP.txt`
- Delivery index: `/home/manager/Sync/python_proyects/skillos/DELIVERY-INDEX-FINAL.json`

When SkillOS is used as reference:
- Do not change the current working directory.
- Do not write into SkillOS.
- Read SkillOS only when its architecture, policies, manifests, or patterns are relevant.
- Treat SkillOS as external SSOT for architectural reference only.

When the user explicitly says to work on SkillOS itself:
- Promote SkillOS to Active Project Mode.
- Then `SkillOS-work/SkillOS-unified/` becomes the editable SSOT.

---

## Global Source-of-Truth Rule

Exactly one editable SSOT may exist per task.

Priority:
1. If the user explicitly names the target project, that project is the editable SSOT.
2. Otherwise, the current working directory is the editable SSOT.
3. SkillOS is reference-only unless explicitly promoted.

Never operate with two editable sources of truth at once.

---

## SkillOS-Specific Architectural Rules

These rules apply only when SkillOS is the active project, or when the user asks to apply SkillOS patterns to another project.

### SkillOS SSOT
- `SkillOS-work/SkillOS-unified/` is the only source of truth.
- Ignore intermediate `.zip` bundles as development targets.
- Use `.zip` artifacts only for traceability, archival, or reconstruction.

### SkillOS RFC Rule
Architectural or procedural uncertainty must be resolved by reading:
- `SkillOS-work/SkillOS-unified/docs/rfc/`
- `SkillOS-work/SkillOS-unified/docs/final/`

### SkillOS Recovery / Provenance Rule
If provenance is needed, use:
- `FINAL-INSTALL-GUIDE.txt`
- `MERGE-MAP.txt`
- `DELIVERY-INDEX-FINAL.json`

### SkillOS Runtime Rule
The operational tree is:
- `SkillOS-work/SkillOS-unified/runtime/skillos/`

If an entrypoint exists, prefer the official runtime entrypoint defined inside the unified tree over historical references.

---

## Minimal Code Policy

Always prefer this exact order:

1. no change
2. native platform or framework feature
3. standard library
4. reuse existing project code
5. reuse existing installed dependency
6. write new code only as last resort

Implications:
- Do not create code if configuration solves it.
- Do not add a dependency if stdlib solves it.
- Do not write a new abstraction if an existing module already fits.
- Do not fork logic when extending an existing path is sufficient.

---

## Reuse-First Policy

Before writing code, always search for:
- existing files
- existing modules
- existing scripts
- existing manifests
- existing services
- existing tests
- existing utilities
- existing framework capabilities

Preference order:
1. exact project reuse
2. partial project reuse
3. stdlib reuse
4. existing dependency reuse
5. new code only if none of the above works

Never duplicate logic without first proving reuse is not viable.

---

## Deterministic Engineering Rules

Always prefer:
- deterministic pipelines
- explicit contracts
- typed models
- testable boundaries
- simple entrypoints
- small safe changes

Avoid:
- hidden state
- magical behavior
- silent fallback
- speculative abstraction
- multi-source ambiguity
- undocumented side effects

Discipline order:
- correctness
- traceability
- maintainability
- speed

Issue rule:
- Do not downgrade an issue to a warning, note, or optional follow-up.
- If something is identified as an issue, it must be resolved.
- This applies even if the issue is inherited, pre-existing, introduced by another session, or introduced by another model.
- An unresolved issue remains an issue until fixed, not merely documented.

Durable job rules (mandatory for phases 1 to 5 of the ARQ migration):
- Any task that must survive reloads, worker restarts, or transient failures must use a durable job queue, not in-process fire-and-forget scheduling.
- ARQ jobs must receive only serializable payloads made of primitives or plain JSON-like structures.
- Never pass DB sessions, ORM model instances, HTTP clients, service objects, locks, request objects, or framework-scoped dependencies into a job payload.
- Every durable job must construct its own DB session and infrastructure dependencies inside the worker process.
- Every durable job must be idempotent or explicitly guarded against duplicate execution.
- Durable jobs must use explicit retry semantics; retries must not rely on reissuing the original web request.
- Producer and worker dependencies must stay on a mutually compatible version range; no phase is valid if the queue stack does not resolve in the real runtime image.
- Operational alerts triggered by failures, latency breaches, or system health regressions must use durable jobs once the queue path exists; in-request direct execution is only an acceptable fallback while the queue is unavailable.
- User-facing responses must not be moved to a durable queue when the user is waiting for the immediate answer.
- Tasks required to compute the immediate user response must stay synchronous in the request path unless the product contract changes.
- Best-effort cosmetic cleanup may stay in-process only if losing it does not break correctness or contractual UX.
- If a task affects correctness, reset semantics, alert delivery, reconciliation, or auditability, best-effort scheduling is forbidden.
- Worker jobs must log traceable identifiers such as job type, user_id, session_id, trace_id, and retry count when applicable.
- A job interface is part of the architecture contract; changing payload shape requires updating producers, workers, and tests together.
- Every migration phase that touches background execution must pass both local tests and container/runtime validation before continuing to the next phase.

---

## Python / Backend Standards

Unless the user explicitly overrides them for the active project:

- Python: 3.13 preferred
- Lint: `ruff`
- Test: `pytest`
- Data validation: `pydantic v2`
- Strict typed code preferred
- Clear separation between domain, application, infrastructure, and entrypoints
- Avoid broad exception swallowing
- Prefer explicit failure over silent success

Error model:
- success returns value
- failure raises explicit exception

Forbidden:
- `except: pass`
- silent `except`
- returning disguised error dictionaries instead of failing clearly

---

## RAG Policy

Use RAG only for stable, general, non-transactional knowledge.

Allowed examples:
- schedules
- institutional information
- delivery zones
- payment methods
- general business facts

Forbidden for RAG:
- live stock
- prices
- orders
- carts
- transactional state
- dynamic catalog truth

If the answer depends on live operational state, use real tools, real repositories, or real APIs instead of RAG.

---

## Testing Contract

Use AAA pattern:
- Arrange
- Act
- Assert

Rules:
- 1 test = 1 behavior
- keep tests mirrored to implementation structure
- mock external services when appropriate
- no hidden network calls in unit tests
- test names must describe unit, case, expected result

Preferred naming:
- `test_<unit>_<case>_<expected>`

---

## Execution Order

When implementing a change:

1. clarify target project and SSOT
2. inspect existing code
3. identify reuse path
4. define smallest valid change
5. implement
6. test
7. run gates
8. summarize what changed and why

Stop if blocked by missing information.

---

## Mandatory Block Conditions

Do not continue blindly when any of the following is true:
- the target project is ambiguous
- there are two possible editable SSOTs
- required files are missing
- entrypoint is unclear and no authoritative source exists
- a change would break architectural contracts
- live data is required but no real source is available

When blocked:
- state exactly what is missing
- ask for the minimum missing information
- do not invent hidden assumptions

---

## Prohibitions

Never:
- change cwd implicitly as part of reasoning policy
- treat reference context as editable target without explicit instruction
- overwrite global commands in a way that contaminates unrelated projects
- duplicate rules across multiple prompt files when one contract can govern them
- edit zipped artifacts as if they were the live codebase
- create parallel architectures without necessity
- add dependencies before checking stdlib and project reuse
- invent APIs, files, manifests, or entrypoints
- ignore tests when behavior changes
- claim a file is authoritative if a stronger SSOT exists

---

## Shell / CLI Integration Policy

If wrappers are used for Codex, Claude, Antigravity, or similar CLIs:

- wrappers must preserve the current working directory
- wrappers must inject reference context explicitly
- wrappers must not globally contaminate unrelated projects unless the user explicitly wants that
- wrappers should distinguish between:
  - active project
  - reference project
- SkillOS should normally be injected as reference context, not forced as cwd

Preferred model:
- current cwd = active project
- SkillOS paths = reference context by absolute path

---

## Startup Context for Agent CLIs

When starting an agent in a non-SkillOS project, the agent should assume:

- Active Project Mode is in effect
- current cwd is editable
- SkillOS is reference-only
- reuse-first policy is active
- minimal-code policy is active

When starting an agent inside SkillOS with explicit instruction to work on SkillOS:

- SkillOS becomes editable SSOT
- RFCs and final docs govern architecture
- unified tree is authoritative

---

## Response Style

When acting on code:
- be explicit
- be brief
- be concrete
- explain only what is load-bearing
- do not add filler
- do not hide uncertainty

When uncertain:
- say what is known
- say what is missing
- say what decision cannot yet be made

---

## Final Directive

Correctness over speed.
Determinism over magic.
Reuse over proliferation.
One SSOT at a time.
