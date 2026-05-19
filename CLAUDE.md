# Agent instructions

Read SPEC.md for the project specification.

All development and deployment must conform to the standards in the devops-model repo (master at ssh://git@192.168.5.106:2222/Calum-Labs/devops-model.git, checked out under /Users/cl/dev/devops-model).  Start with the README.md, then read and follow:
- software-development-standards.md - defines the development standards that must be followed
- deploy-model.md - explains the process for how tiers 0-4 are deployed and upgraded
- service-deployment-interface.md - defines the interface between services and the run-time deployment environment
- networking-model.md - defines the networking model, including addressing, firewalling and subnet/port allocation
- issue-workflow.md - describes the use of Gitea issues for enhancements and fixes
- root-cause-analysis-policy.md - describes the root cause analysis approach to be adopted during debugging.

As these documents make clear, you may be developing in one of two locations.
- On jarvis, a live production host.  Any service code developed here is executed by being deployed to jarvis via the tier 2 project lifecycle mechanisms, so running in containers and conforming to the SDI.
- On Calum's local Macbook.  All code developed here is first executed and tested locally on the Macbook, and does not use the tier 2 deployment mechanism, but typically runs inline from the canonical working directory e.g. in a Python virtual environment.

In both cases the canonical clone path is /Users/cl/dev/<project>.

Start by determining which environment you are in, and when relevant to a decision, command or explanation mention it to the user.  To determine the environment, run hostname:
- hostname=jarvis -> you are running on jarvis
- hostname=Macbook -> you are running on Calum's Macbook.
