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
