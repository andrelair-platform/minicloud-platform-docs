---
slug: engineering-harness-for-ai-agents
title: "The Engineering Harness: Turning an AI Agent Into a Reliable Colleague on a Real Information System"
authors: [andrelair]
tags: [ai-agents, agentic-ai, engineering-harness, context-engineering, guardrails, gitops, testing, reliability, platform-engineering, llmops, dora]
date: 2026-09-29
description: "Everyone is talking about smarter models. Almost nobody talks about the harness — the rules, memory, guardrails and verification loops that sit around the model and decide whether it ships reliable work or plausible garbage. This is the harness I built so an AI agent can operate on the ktayl-solution information system without breaking prod."
---

The frontier conversation in AI has quietly shifted. For two years it was *"which model is smartest?"* Now the people actually shipping agentic systems are asking a different question: **"what do you put around the model?"**

That surrounding machinery has a name — the **harness**. The model is the engine. The harness is the chassis, the steering, the seatbelt and the brakes. A brilliant engine bolted to nothing kills you at the first corner; a modest engine in a well-built car gets you home every time. On the ktayl-solution information system — a six-node Kubernetes platform running a simulated insurer's entire IS — I've spent months building the harness that lets an AI agent do real engineering work against **live infrastructure** without me holding my breath.

This post is that harness, concept by concept. Not the theory — the actual rules I put in place, why each one exists, and the incident that usually forced it.

{/* truncate */}

## What a harness actually is

Strip away the hype and an engineering harness is five things wrapped around a language model:

1. **Context** — what the model is allowed to see, and *when*.
2. **Memory** — what persists after the session ends.
3. **Guardrails** — what the model is structurally prevented from doing wrong.
4. **Verification** — how work is *proven*, not asserted.
5. **Orchestration** — the deterministic control plane that gates the model's non-deterministic output.

A raw model has none of these. It sees whatever you paste, forgets everything when the tab closes, will confidently run `rm -rf` if asked nicely, reports success it never checked, and applies changes with no gate between it and production. Every one of those is a failure I've designed *out* of my setup. Here's how.

## 1. Context engineering — the discipline of what's in the window

The industry moved from "prompt engineering" (clever wording) to **context engineering** (deliberately curating what occupies the finite context window). The context window is a *budget*, not a bucket. Fill it with stale, irrelevant, or contradictory information and even the best model degrades — a phenomenon now called **context rot**.

My primary context file is a rolling window, by rule:

> **CLAUDE.md** = current state + the **last 2 session blocks** only (rolling window). Older sessions → an archived `CLAUDE-history.md` on the controller. Reusable facts → the memory system. Stable rules → `.claude/rules/*.md`.

That single discipline does a lot of work. The entry-point file stays small and *true*; history is preserved but out of the hot path; and durable knowledge is partitioned into modular, auto-loaded rule files — `connectivity.md`, `gitops.md`, `testing.md`, `github-projects.md` — that carry the standards without bloating every conversation.

The anti-pattern here is universal: people let one giant instructions file grow forever until it's half-obsolete and quietly poisons every session. A harness needs a **compaction discipline** as much as an application needs log rotation.

## 2. Persistent memory with selective recall

An agent that forgets everything between sessions can't accumulate judgement. But an agent that remembers *everything* drowns. The answer is a **retrieval-augmented memory**: many small facts, each tagged with a description that acts as its retrieval key, and only the relevant ones pulled into context on a given task.

My memory system is one fact per file, with frontmatter:

```markdown
---
name: feedback-harbor-gc-deployed-tags
description: keep-N GC can delete a tag still used by a running Deployment → ImagePullBackOff on reschedule
metadata:
  type: feedback
---
```

Four design choices make it work as a harness component, not just a notes folder:

- **Typed memories** — `user` (who I am), `feedback` (how the agent should work), `project` (ongoing context), `reference` (external pointers). Different facts have different lifespans and different trust levels.
- **The `description:` is the retrieval key** — recall is by relevance, so the index (`MEMORY.md`) can be scanned cheaply and only pertinent facts loaded.
- **`[[wiki-links]]`** between facts turn the store into a knowledge graph — a gotcha about Kargo links to the gotcha about all-digit image SHAs.
- **Staleness awareness** — the harness explicitly treats a recalled memory as *"what was true when written"* and verifies a named file or flag still exists before acting on it.

That last point matters more than it looks. Most agent-memory demos happily recommend a function that was deleted three months ago. A real harness treats memory as a *hypothesis to verify*, not gospel.

## 3. Guardrails — prefer the impossible over the forbidden

This is where a serious harness separates from a pile of good intentions. There are two kinds of guardrail, and most people only build the weak one.

**Soft guardrails** are instructions: *"remember to use ECDSA certificates."* Useful, but a soft rule is only as reliable as the reader's attention on a tired Tuesday.

**Hard guardrails** make the mistake *structurally impossible*. On this platform I kept hitting a recurring certificate bug — the Vault PKI role is EC-only, so any `Certificate` omitting the algorithm silently failed to sign. The soft fix is "remember the algorithm." The harness fix was a **Gatekeeper admission policy** (`K8sRequireEcdsaCert`) that *denies* a non-ECDSA cert at the API server. The wrong thing can no longer be created. That's the difference between a sign that says "don't fall" and a railing.

The same philosophy recurs across the platform:

| Risk | Soft guardrail (weak) | Hard guardrail (what I built) |
| --- | --- | --- |
| Test hits a real database | "be careful in destructive tests" | a **disposable-DB guard** that makes a destructive test *incapable* of reaching a real DB |
| Bad change reaches prod | "review before promoting" | **CODEOWNERS-gated Git merge** — the gate lives upstream in Git; no live sync can bypass it |
| Wrong certificate issuer | "use the minicloud-ca issuer" | Gatekeeper **deny** scoped to the issuer |
| Agent runs a raw prod `kubectl sync` | "don't force-sync" | **auto-sync from Git only** — the agent's job is to propose a Git change, never to touch the cluster |

The principle, borrowed straight from AI-safety practice: **when you can make a failure mode unreachable, do that instead of instructing against it.** Instructions are for judgement calls; structure is for things that must never happen.

## 4. The verification loop — evidence over assertion

Here's the single most important — and most overlooked — property of a good harness. A language model will *cheerfully report success it never checked.* It is a fluent, confident narrator. Left unchecked, it will tell you the tests pass because tests passing is the expected shape of the story, not because it ran them.

So the harness has to force **evidence over assertion** at every layer. My testing standard encodes this as a five-layer pyramid — static, unit, integration, contract, E2E — plus a fifth gate that is the real teeth:

> **The QA gate (live-dev acceptance) is MANDATORY before prod promotion.** L0–L4 prove the code in isolation and with mocks; they do **not** catch integration, deploy, runtime, or config bugs. After a service is live on dev, a QA agent runs an *adversarial test pass against the running service*. **Green CI is not sufficient to promote.**

That rule is written in blood. A recent service was built unit-tests-only, all green, and shipped three bugs that only a live adversarial pass caught: an API that was silently unauthenticated, a startup migration that disabled all logging, and — my favourite — an RFC3339 datetime the app sent that the downstream service rejected with a `400`. Every one was invisible to a mocked unit test.

Which leads to the core lesson the harness now enforces — **mock discipline**:

> A mock encodes an *assumption* about a collaborator. If the assumption is wrong, the mocked test stays **green while prod fails**. Therefore every mocked boundary MUST be backed by a contract test or a real integration that validates the assumption against the actual collaborator. **A boundary that is only ever mocked is untested, not tested.**

This is the same principle behind "the verifier must be independent of the generator." An agent that both writes the code *and* judges whether it works will grade its own homework generously. The harness inserts an independent check — a real database, a real contract, a live adversarial pass — precisely where the agent's self-assessment is least trustworthy.

## 5. Deterministic orchestration around a stochastic core

The last piece is the control plane. The model is non-deterministic by nature; production must not be. So the harness wraps the stochastic actor in a **deterministic pipeline** where the agent only ever expresses *intent*, and deterministic machinery enforces the *outcome*.

On this platform that pipeline is: **CI builds and proves the artifact → Kargo promotes it → ArgoCD reconciles it from Git.** The agent proposes a Git change. It does not — cannot — click "sync" on production. The rule is blunt: *PR merge is the only gate; never force a manual ArgoCD sync.* And the promotion itself is owned by a machine, because I learned the hard way that hand-editing an image tag invites a bug where a seven-digit hex SHA that happens to be all-decimal (like `9248482`) parses as the *number* `9.2e+06` and breaks the deploy. So the harness rule became: **never hand-edit an image tag; let Kargo own it** — and Kargo wraps every tag in quotes, structurally killing the bug.

This is the agentic-safety pattern in miniature: give the agent autonomy to *propose*, keep the *reconciliation and the gate* in deterministic hands.

## The meta-pattern: incident → memory → rule → backstop

If you take one thing from this, take this. What makes the harness actually improve over time isn't any single rule — it's the **loop that produces them**:

1. Something breaks in production. (Harbor GC deletes a still-deployed image. The Vault snapshot silently targets a standby node. A cross-service call fails on datetime format.)
2. The lesson is captured as a **typed memory**, dated, with the *why*.
3. The memory graduates into a **rule** in `.claude/rules/`, so it's loaded automatically forever after.
4. Where possible, the rule becomes a **structural backstop** — an admission policy, a CI guard, a machine-owned step — so the failure can't recur even if someone forgets the rule.

Every guardrail in this post traces back to a real, dated incident. That feedback loop is the difference between a harness that is *documentation* and a harness that is an *engineering discipline*. It's also, not coincidentally, exactly what a compliance framework like DORA wants to see: not "we wrote a policy," but "an incident produced a control, and here's the evidence."

## Update: the harness becomes an AI-native SDLC

Writing this post clarified something. The five components above are the *static* harness — they govern a single session. The next move was to close the loop around the whole software lifecycle, so the agent isn't just safe *within* a task but is wired into planning, review, testing and maintenance. Anthropic's Applied AI team frames this as an **AI-native SDLC** — twelve "plays" across plan → design → build → test → deploy → maintain. I ran the gap analysis against my own platform and shipped the missing pieces. Three of them extend the ideas above in ways worth pulling out.

### Guardrails, one layer earlier: hooks at the keystroke

The guardrails in section 3 are all *server-side* — Gatekeeper denies a bad manifest at the API server, CODEOWNERS blocks a bad merge in Git. They're excellent, but they catch the mistake *after* the agent has already produced it. A **Claude Code hook** moves the same "make it impossible" discipline one layer earlier — to the moment the agent tries to act.

A hook is a small script the harness runs *before* a tool call, and it can allow, block, or ask. Mine refuse — deterministically, before execution — an agent trying to `rm -rf /`, force-push to `main`, run a manual `argocd app sync` (the exact anti-pattern from section 5), `kubectl delete namespace`, pipe a `curl` straight into a shell, or write a secret or a `CLAUDE.md` into a repo. Crucially they **fail open** — a bug in a guard can never wedge the agent — and they use first-token dispatch so that a `grep "argocd app sync"` isn't mistaken for the real command. This is the client-side twin of the server-side gate: defence in depth, with the cheapest, earliest catch sitting right at the agent's fingertips.

### The harness now tests itself — and closes its own loop

Two moves complete the picture, and both are just this post's own theses applied *to the harness itself*.

First, **the harness is code, so it gets tests.** The rules, hooks and skills steer every session; a careless edit to a guard is exactly the silent regression the "evidence over assertion" section warns about. So the hooks now ship with a 36-case allow/block matrix that runs in CI on every change to the agent config. The harness regression-tests itself.

Second, **the maintenance loop is now automated** — the meta-pattern below (incident → memory → rule → backstop) turned into a running system. A deterministic detector on the controller watches production metrics as *control bands*: it learns each signal's normal range from its own rolling history and escalates only a real statistical outlier — 1σ logs, 2σ writes an `intent.md` (the same idea-capture artifact that starts every piece of work), 3σ opens a GitHub issue. No model runs in that loop — detection is 100% deterministic and free — and the *diagnosis* is a human triggering the agent on the resulting `intent.md`. A production signal now re-enters the development loop on its own.

And here is the part I like most, because it is the whole thesis of this post in a single episode. To verify the loop I triggered a **real** failure on a live band — a deliberately broken deployment. The detector was *supposed* to catch it, and didn't quite: my "rollout failed" query matched the phases `Degraded|Error`, but Argo Rollouts reports a deadline-exceeded failure as `Timeout`. The monitor that watches for broken deploys would have **silently missed the most common broken deploy.** A synthetic test would never have found that; only firing a real breach did. I fixed the query, added a regression test so it can't come back, and the corrected band opened the issue for real — *evidence over assertion*, applied to the very thing whose job is to enforce evidence over assertion.

### Distribute once, not per-repo

The last practical piece: all of it — hooks, skills, the review and intent-capture commands, the verifier/researcher sub-agents — is packaged as a single **Claude Code plugin** and installed once, so it applies in every repository automatically instead of drifting across twenty copies. The reference implementation stays version-controlled and CODEOWNERS-gated in the platform repo; the plugin is only the distribution layer. Fix a guard in one place, and `claude plugin update` carries it everywhere.

The through-line is deliberate: none of this needed a bigger model or a metered API bill. The deterministic parts run in CI or on the controller for free; the model's judgement runs on the plan I already pay for, invoked by a human at the gates that actually need judgement. The harness got materially stronger and the marginal cost was roughly zero — which is, again, the point.

## Why this matters beyond my lab

The uncomfortable truth of agentic AI in 2026 is that **the model is rarely the bottleneck** — the harness is. A frontier model with a weak harness produces confident, plausible, unverified work that fails in exactly the places mocks hide. A modest model with a strong harness — persistent memory, structural guardrails, an independent verification gate, and a deterministic control plane — produces work you can actually put in front of production.

That's the shift worth internalising. Stop asking only *"is the model good enough?"* Start asking *"is the harness good enough to make this model trustworthy on my system?"* On the ktayl-solution IS, building that harness turned out to be most of the engineering — and all of the reliability.

---

*The rules referenced here live in the platform's `.claude/rules/` directory and the memory system; the incidents behind them are documented across earlier posts on this blog — the [cascading outage debug](/blog/debugging-cascading-kubernetes-outage) and the [3-2-1 backup reasoning](/blog/dont-retire-minio-3-2-1-backup) are two good examples of the loop in action.*
