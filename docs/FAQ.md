# FreshCtx™ FAQ

## Does GitHub or CI/CD already prevent this problem?

No. GitHub branch protection and CI/CD determine whether a particular commit passed its configured checks. FreshCtx determines whether the specific files, Git state, APIs, database rows, or MCP resources supporting an agent's current action are still valid when that action is about to occur.

FreshCtx complements GitHub, pull requests, branch protection, and CI/CD. It closes the reasoning-to-action freshness gap.

## How is FreshCtx different from agent memory?

Memory tells an agent what it knew. FreshCtx tells it whether that knowledge is still current. FreshCtx records declared observations, connects dependent reasoning to them, and checks those dependencies again at a protected boundary.

## Does FreshCtx verify that an agent's reasoning is correct?

No. FreshCtx revalidates observations and invalidates reasoning that depends on stale observations. It does not prove that reasoning is logically correct or that reality is globally correct.

## Does every repository change invalidate everything?

No. The Git adapter supports path-scoped validation. An unrelated change does not invalidate an observation when the observed path is unchanged.

## What happens when FreshCtx cannot reach a source?

The result is `UNVERIFIABLE`, not `CURRENT`. FreshCtx then fails safely according to the configured `block`, `warn`, or `allow` policy. Blocking is the default.

## Does FreshCtx make a workflow compliant?

No. FreshCtx can support compliance controls by producing local, auditable evidence that declared sources were revalidated at decision time. Compliance depends on the complete workflow, policies, people, and systems around it.

## Is Postgres required?

No. Postgres is an optional adapter integration. The core package has no required third-party runtime dependencies.

## Does FreshCtx require an account, hosted service, model, or agent framework?

No. FreshCtx v0.1 is local-first, model-neutral, framework-neutral, requires no account, and sends no telemetry.

## Is FreshCtx a Hyperwise proprietary product or an open-core edition?

No. FreshCtx™ is an independent Apache-2.0 open-source project initially stewarded by Hyperwise. The complete usable v0.1 runtime and its five initial adapters are part of the open project.

Possible future Hyperwise services—such as centralized governance, managed deployment, enterprise integrations, implementation support, and SLAs—are separate from FreshCtx core and do not exist in v0.1.
