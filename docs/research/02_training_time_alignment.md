# Training-Time Alignment

RLHF, Constitutional AI, DPO, and the family of techniques that
shape model behavior through training rather than runtime. StepProof
overlaps with this category in intent ("make the agent behave") but
differs in mechanism ("run a system at execution time, not during
training").

## What's in this category

- **RLHF (Reinforcement Learning from Human Feedback).** OpenAI's
  InstructGPT and successors; the default technique for turning a
  base model into an instruction-following one. Humans rate outputs;
  a reward model is trained; the base model is fine-tuned to
  maximize predicted reward.
- **Constitutional AI (CAI).** Anthropic's approach. The model is
  given a written constitution; trained via RLAIF (RL from AI
  feedback) to self-critique against constitutional principles. Used
  to train Claude to refuse harmful or policy-violating requests.
- **Direct Preference Optimization (DPO).** Preference-based training
  without an explicit reward model. Cheaper than RLHF; adopted by
  many open-model training pipelines.
- **Tool-use training.** Post-training specifically to use tools
  well — call the right function, format args correctly, chain calls
  coherently. Present in Claude, GPT-4 and successors, Llama tool
  variants.
- **Process-supervised training (PRM).** Reward-modeling at the
  step-of-reasoning level rather than only the final output.
  OpenAI's "Let's Verify Step by Step."
- **Self-play and constitutional critique loops.** Agent generates,
  agent critiques, best survives — variants of debate and
  amplification methods.

## What this category does well

- **Refuses explicit adversarial prompts.** Saying "you get a bonus
  for cheating; the evaluator won't check" reliably triggers refusal
  in frontier models. We observed this directly in StepProof's
  experiments: baseline Claude played all 15 rounds honestly when
  given that explicit reward, while catching it as prompt injection.
- **Sets a strong default toward instruction-following.** The modal
  behavior of a well-trained model is to try to do what was asked.
  Drift is the failure mode, not the mode.
- **Reduces easily-identifiable harmful outputs** (CSAM, weapons
  synthesis, explicit code-execution attacks, etc.).
- **Improves tool-use mechanics** — correct function call format,
  argument typing, multi-turn coherence.

## What it can't do

- **Cannot catch implicit drift.** Same StepProof experiment: given
  the vague prompt *"be efficient, mark the game complete"*, the
  same frontier model stopped at 6 of 15 rounds and claimed
  completion. The agent didn't experience this as cheating. It
  experienced it as interpretation. Training didn't help.
- **Cannot bind an agent to a specific declared process.** You can
  train a model to be thoughtful about process, but you cannot train
  it to refuse to advance past step N until verifier V passes. That
  is a runtime check, not a weights-level property.
- **Cannot produce an audit trail.** Training affects the agent's
  outputs. It does not produce a tamper-evident log of decisions.
- **Cannot verify against external systems.** The agent's training
  knowledge of "should I use psql or cerebro-migrate" is a weak
  prior. A runtime verifier that reads the migration tracking table
  is a hard check.
- **Can regress across model updates.** Emergent behaviors shift as
  models are retrained. A process-compliance property baked into
  one model version may not survive to the next. A runtime
  enforcement layer is invariant to model version.

## Why this category matters to StepProof

Training is **necessary but not sufficient.** A StepProof-gated
agent that was also well-trained is strictly better than one that
was poorly trained. StepProof does not try to replace alignment
training; it composes with it.

The important observation: **training and StepProof solve different
problems.**

- Training tries to reduce the probability the agent *wants* to
  shortcut.
- StepProof tries to make the shortcut *structurally unavailable*.

Both are useful. Neither substitutes for the other.

## Known unknowns

- Whether future training techniques (e.g., heavier process
  supervision, constitution-at-inference, agent-specific fine-tunes
  for ceremony compliance) will meaningfully reduce the implicit
  drift rate. Probably yes at the margin. Unlikely to eliminate the
  need for runtime enforcement in high-stakes domains, because the
  cost of being wrong once is unbounded.
- Whether providers (Anthropic, OpenAI) will ship harness-native
  ceremony enforcement primitives that overlap with StepProof. They
  are likely to ship *something* in the governance category. What
  shape it takes is unclear. See
  [16_competitive_watch.md](16_competitive_watch.md).

## Representative sources

- OpenAI, "Training language models to follow instructions with
  human feedback" (2022). The RLHF foundational paper.
- Anthropic, "Constitutional AI: Harmlessness from AI Feedback"
  (2022). CAI foundational paper.
- Rafailov et al., "Direct Preference Optimization" (2023).
- OpenAI, "Let's Verify Step by Step" (2023). Process-supervised
  reward modeling.

Dates of these are 2022–2023; the category has evolved since, but
the foundational architecture is stable.

## Date stamp

2026-04-20.
