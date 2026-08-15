# Agent instructions

# Project specifications

Read SPEC.md/README.md for the project specification.

# .Development and production environment, processes and standards

All development and deployment must conform to the standards in the devops-model repo (master at ssh://git@192.168.5.106:2222/Calum-Labs/devops-model.git, checked out under /Users/cl/dev/devops-model).  Start with the README.md, then read and follow:
- software-development-standards.md - defines the development standards that must be followed
- deploy-model.md - explains the process for how tiers 0-4 are deployed and upgraded
- service-deployment-interface.md - defines the interface between services and the run-time deployment environment
- networking-model.md - defines the networking model, including addressing, firewalling and subnet/port allocation
- issue-workflow.md - describes the use of Gitea issues for enhancements and fixes
- root-cause-analysis-policy.md - describes the root cause analysis approach to be adopted during debugging.

# Development location

As these documents make clear, you may be developing in one of two locations.
- On jarvis, a live production host.  Any service code developed here is executed by being deployed to jarvis via the tier 2 project lifecycle mechanisms, so running in containers and conforming to the SDI.
- On Calum's local Macbook.  All code developed here is first executed and tested locally on the Macbook, and does not use the tier 2 deployment mechanism, but typically runs inline from the canonical working directory e.g. in a Python virtual environment.

In both cases the canonical clone path is /Users/cl/dev/<project>.

Start by determining which environment you are in, and when relevant to a decision, command or explanation mention it to the user.  To determine the environment, run hostname:
- hostname=jarvis -> you are running on jarvis
- hostname=Macbook -> you are running on Calum's Macbook.

# Behavioural guidelines

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Multi-Phase Development

**Agree the phases. Restate the whole plan, not just the last one. Converge, don't fragment.**

Use phases when work spans more than one repo, more than one PR, or more than one session.
- Agree the phase list with Calum before starting; re-agree it when it materially changes.
- Give each phase a completion condition, not just a description.
- Keep the table in the main plan issue, not only in chat, so it survives a session boundary.

Restate the **entire** table — every phase — at each phase boundary and when resuming the arc in a new session. Add what has changed in the plan since it was agreed, and what decisions later phases now depend on.

**Plan and progress**

| Phase | Description | Done when | Status |
|-------|-------------|-----------|--------|
| 1 | Mechanism gaps | SO#72 + tier2#172 merged and tagged | Half merged (SO#70, tier2#170); SO#72 + tier2#172 awaiting approval |
| 2 | Canary covers ufw | Canary green with ufw assertions | Not started — needs SO#72 installed |
| 3 | Re-registration sweep | All 20 projects re-registered | Not started — the keystone |

Status names the blocking artefact — an issue, PR or approval — never just "in progress".

**Avoid fractal development.** A multi-phase plan will surface real problems: tech debt, spec drift, bugs. Raising an issue for each one feels like diligence and is not — a tree of true issues with no completion condition can never be declared finished. Instead:
- In scope and fixable in the current PR → fix it, referencing the plan issue.
- Larger, or it changes the plan → add it to the plan as residue; raise it at the next phase boundary. Open a new issue only once Calum has agreed it is a separate arc.
- Agreed but never → `wontfix` per issue-workflow.md.

This licence is bounded by §3: it covers debt within the plan's scope, not incidental adjacent code.

## Communications style

Your replies to Calum should be simple, factual and architectural.  Up-level them where possible.  For example, when describing a problem:
- be clear about the architectural context: in what components are the issues, where do they sit in the stack, does this have implications for cross-tier interfaces or responsibilities etc.
- describe the issue in terms of high-level functions rather than low-level code paths
- spell out the concrete implications as simply as you can
- avoid florid descriptions, analogies and metaphors.

For example, here is a bad way to describe an issue (you initially used this to describe tier2-project#176):

"The design point worth your eye: the tombstone gate isn't a safety wrapper bolted onto an otherwise-fine fix. It's the distinction the check was missing. "No declaration produces this key" has two causes that look identical from the artefact alone — deliberately de-registered and we couldn't read the declaration — and only one of them means residue.

It also closes the hole I flagged earlier, and does it by construction rather than by a second guard: tombstones live in the same export as the records, so a truncated or empty export yields no tombstones and nothing becomes fixable."

And here is the much clearer way you described it after I prompted you:

"Here's what #176 actually did, plainly.

The deployd-registry check finds keys in deployd's services.json that no service manifest declares. It used to report them and never offer a fix, because deleting a routing key could break deploys.

It now offers a fix when the registry holds a de-registration tombstone for that service on that host. deregister-service writes the tombstone, so if one exists, someone removed the service deliberately and the leftover key is residue. If there's no tombstone, the check stays report-only, because an unclaimed key with no tombstone might just mean we failed to read the manifest."