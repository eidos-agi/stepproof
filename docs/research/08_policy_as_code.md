# Policy-as-Code

OPA (Open Policy Agent), Styra, Rego, and the general pattern of
"declare policy as code, evaluate at decision points." Not directly
an AI tool, but the architectural ancestor of what StepProof's
runbook + classifier layer is doing.

## What's in this category

- **OPA (Open Policy Agent).** CNCF-graduated policy engine. Rego
  language. Decisions as: "given this input, what's the policy
  verdict?" Used for Kubernetes admission control, API
  authorization, service-mesh policy.
- **Rego.** OPA's query language. Declarative, pure-functional,
  designed for policy.
- **Styra.** Commercial OPA-based platform. Policy authoring,
  distribution, audit. The company that built OPA.
- **Cedar (AWS).** Policy language AWS built for Verified Permissions
  and IAM. Alternative to Rego.
- **Casbin.** Access-control library with multiple policy models
  (ACL, RBAC, ABAC).
- **Cel (Common Expression Language).** Google's expression language,
  used in Kubernetes admission and many validating webhooks.

## What this category does well

- **Policy decisions as data, not code.** Policies are declarative,
  auditable, reviewable as diffs.
- **Centralized policy, distributed enforcement.** Declare once;
  every enforcement point evaluates the same rules.
- **Composable rules.** Policies can call each other, inherit,
  combine.
- **Decision logging.** Every policy evaluation can be logged with
  its input and verdict. Audit trail comes free.
- **Well-understood by security teams.** OPA has been production at
  scale for years; the operational story is mature.

## Why StepProof looks a lot like this

Both:
- Evaluate rules at decision points.
- Produce structured decisions (allow / deny / transform / approve).
- Log every decision.
- Aim for declarative rule authoring.

The StepProof PreToolUse hook is essentially a policy evaluation
point, and the classifier YAML is a primitive policy language.

## Where they differ

- **Policy-as-code engines evaluate stateless queries.** Given input,
  return verdict. They don't carry "this is the current step of a
  multi-step process" state across queries.
- **StepProof needs stateful evaluation.** The policy for a given
  tool call depends on which step the run is currently on, which
  requires cross-query state.
- **Policy-as-code engines don't verify against external state.**
  They evaluate rules against the input. They don't query a
  migration tracker to confirm the claimed input is real.
- **Policy engines don't model ceremonies.** A ceremony is a
  first-class artifact in StepProof; it's a user-space concept on
  top of a policy engine.

## Could StepProof be built on OPA?

Yes, partially. The classifier YAML could be translated to Rego,
with a StepProof-specific data model for ceremony state. The hook
could call OPA for evaluation.

Tradeoffs:

- **Pro**: standard tooling, security-team familiarity, Rego expertise
  in the market, better policy composition.
- **Con**: adds a Rego runtime dependency; rule authors need Rego
  skills in addition to understanding ceremonies; extra integration
  layer with no concrete feature gain for most users.

Probably not v1. Plausibly v2+ if enterprise customers demand it for
compliance with existing Rego-based governance stacks.

## What StepProof could learn from OPA

- **Bundle distribution pattern.** OPA bundles policies distributed
  via signed artifacts. Regulated StepProof deployments might want
  signed runbook bundles.
- **Decision log format.** OPA's decision logs (input, query, result,
  timestamp) are a good model for StepProof's audit log.
- **Test harness for policies.** OPA has first-class testing of
  policy rules. StepProof should have first-class testing of
  runbooks — declare the runbook, declare test scenarios, assert
  expected verdict at each step.

## Known unknowns

- Whether there's value in translating the classifier YAML to Rego
  for existing-OPA customers. Plausible enterprise ask.
- Whether ceremony-as-data-plus-policy-as-code generalizes as an
  abstraction beyond the current StepProof implementation.

## Representative sources

- Open Policy Agent: `openpolicyagent.org`.
- Styra: Styra DAS platform.
- Cedar: AWS Cedar docs.
- CEL: `github.com/google/cel-spec`.

## Date stamp

2026-04-20.
