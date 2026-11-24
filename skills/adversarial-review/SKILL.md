---
name: adversarial-review
description: "Adversarial verification and feature-type test matrix after building a feature. Dispatches fresh breaker agents to attack functionality, browser UI, and real user journeys instead of relying on TDD unit tests alone. Use for /adversarial-review or before finishing a feature."
disable-model-invocation: true
---

# Adversarial review

Unit tests and TDD prove the happy path you already thought of. They do not prove the feature is complete, integrated, or resilient against a real user. Before declaring a feature done, classify what you built, run the test types it requires, and dispatch fresh adversarial subagents whose only job is to break it.

## 1. Classify the functionality and pick test types

A single test type never fits every change. Match the feature to every row below that applies.

| Functionality type | Required test types |
| --- | --- |
| **Backend, API, or domain logic** | Unit tests for invariants, integration tests against real storage and boundaries, contract and schema checks, and error-path, auth, and concurrency tests. |
| **Frontend or UI** | Component and state tests, **frontend-ui** skill (`impeccable` and `browser` Design Desk loop), and interactive DOM and responsive viewport checks. |
| **Full-stack (UI and backend)** | Backend integration tests, **frontend-ui** skill, and end-to-end flows in `browser` hitting the real backend with zero mocked APIs. |
| **CLI, scripts, hooks, or automation** | Subprocess tests in an isolated temp directory, exit-code checks, malformed args, env, or stdin tests, and signal, recovery, and idempotency checks. |
| **Data, migrations, or pipelines** | Forward and idempotency runs on realistic dirty data (nulls, duplicates, boundary values), plus row-count and invariant conservation checks. |
| **Skills, agents, or prompts** | Isolated dry-run or eval case, structural checks, and trigger, refusal, and boundary checks. |

## 2. Three adversarial lenses

Run `functionality` and `real-user` for every feature, and run `browser` whenever the feature has a web UI. Use fresh subagents that did not write the implementation.

1. **Functionality breaker (`vex-agent`)**
   - Give the agent the user's original goal, the acceptance criteria, and the changed file paths. Do not tell it the implementation works or ask it to confirm your tests.
   - Instruct it to try to break the feature across boundary, empty, null, unicode, and oversized inputs, invalid state transitions, partial failures, race conditions, permission bypasses, contract mismatches, and skipped requirements from the user's goal.
   - Require executable failing repros or exact reproduction commands for every defect found, with zero edits to production code.

2. **Browser breaker (`browser` subagent)**
   - Run directly on the live URL whenever the feature has a web UI, after or alongside **frontend-ui** skill's Design Desk loop.
   - Attack the live URL as an impatient user. Test rapid double-clicks, browser back and forward mid-flow, page refresh mid-action, invalid or oversized form inputs, empty, error, and overflow states, mobile and desktop viewports, and console or network 4xx and 5xx errors.

3. **Real-user simulator (`vex-agent` or `browser`)**
   - Act as a first-time user who knows only the public entry point (UI, CLI `--help`, API endpoint, or docs) and the user's goal.
   - Do not read internal source code to work around missing docs, unclear errors, or awkward UX.
   - Execute the complete end-to-end journey including setup, the primary task, and recovery from a mistake. Report anything broken, confusing, or missing relative to what a user needs.

## 3. Dispatch rules and fix loop

- **Fresh agents only.** Never ask the agent that wrote the feature to be its own adversary. If the current session cannot spawn subagents, run the adversarial and real-user checks in a separate pass without relying on the author's tests and state that limit in the reply.
- **Kickoff format.** Start every `vex-agent` prompt with `Read <path>/worker.md before anything else.`, where `<path>` is the installed plugin's `skills/vex-mode` folder. State the adversarial bar in the kickoff so the agent finds defects, missing requirements, or breakages and reports exact repros without editing production code.
- **Triage and close the loop.** For every confirmed defect or missing requirement, delegate the fix to a fresh `vex-agent`, never the breaker, then rerun the breaker's failing repro and the feature's test suite. Cap the loop at three rounds. If defects remain after three rounds, report them instead of declaring done.
- **Headless fallback.** If the environment has no `browser` subagent, run the project's UI or end-to-end suite and static checks, and state that live browser adversarial testing was skipped.

## Reply

Report:
- **Classification.** Which functionality types applied and which test types ran.
- **Adversarial lenses.** Which agents ran (`functionality`, `browser`, `real-user`) and what each attacked.
- **Findings and fixes.** Defects or gaps found and fixed with failing-then-passing repros, or verified clean with command or browser evidence.
