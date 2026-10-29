# Euglena research notebook and operating model

Recorded: 2026-10-29. Status: planning; no physical experiments or daily runner active.

This is the persistent entry point for the research project. Read it at the start
of each research session, together with the latest daily report, experiment
records, and hypothesis register. Chat history alone is not the project memory.

## User's research direction

The user intends to provide a fully described, calibrated Euglena observation
setup with camera acquisition and controllable LEDs. Once the instrument is
validated and the user starts the research programme, the agent may choose
experiments, collect data, develop hypotheses, and test them within the agreed
operating envelope without requesting permission for each individual trial.

The purpose is open-ended exploration of light-dependent cell behaviour over
months. Novel findings are possible, not promised. Useful replication, negative
results, measurement improvements, and model failures are legitimate outcomes.

The user remains informed through daily reports that explain decisions,
assumptions, evidence, uncertainties, and competing interpretations. The user
retains control over working hours, budgets, scope, and stopping the programme.

## Conditions before physical operation

- Document the exact controller, camera, optics, LEDs/drivers, sample chamber,
  power arrangement, calibration procedures, and culture maintenance.
- Validate deterministic camera acquisition, tracking, timestamped light control,
  and data recording before autonomous experimentation.
- Establish permitted stimulus intensities, durations, cumulative exposure,
  session duration, and other limits appropriate to the actual hardware.
- Validate an independent controller timeout, manual stop, and a defined rest
  state. Specify visible stimulation, observation illumination, and culture
  maintenance separately. Loss of the agent must not leave a stimulus running.
- Set the daily budget and authorize session timing. These values are currently
  unset. This document does not start experiments or schedule recurring work.

The experimental agent cannot raise its own operating limits during a run.

## Daily session

1. Read this entry point, the previous checkpoint, unresolved hypotheses, and
   relevant earlier trials. Retrieve original records when a summary is unclear.
2. Check authorization, remaining budget, hardware status, storage, sample
   identity/history, and calibration validity. Reconcile any interrupted trial;
   never replay an actuator command blindly.
3. Acquire a baseline/control appropriate to the planned experiments. Record the
   question or exploratory rationale, predictions where available, and protocol
   before changing light conditions.
4. Execute bounded trials through the validated controller. Save observations and
   command events as they happen, so a report is not required to reconstruct them.
5. Assess data quality, compare plausible explanations, and select informative
   follow-up trials. Include controls and independent confirmation of findings
   selected during exploration; do not treat tracks from one sample as independent
   biological replicates.
6. Before the budget or time allowance is exhausted, stop starting trials. Finish
   or safely terminate the active trial, verify saved data, enter the defined rest
   state, and write the daily report and next-session checkpoint.
7. Stop model work. A later date alone does not authorize a restart. Initially the
   user starts sessions; automatic starts require an explicitly configured and
   authorized schedule. Local research dates use `Africa/Tunis`; event timestamps
   also retain UTC and monotonic timing where available.

## One linked research dataset

The notebook, machine-readable experiment ledger, and raw recordings form one
linked dataset. Reports are views of that evidence, not replacements for it.
Create the following records when implementation begins:

| Record | Purpose |
| --- | --- |
| `experiments.jsonl` | Append-only experiment/event index using stable IDs |
| `daily/YYYY-MM-DD.md` | Daily report and restart checkpoint |
| `hypotheses.md` | Current hypotheses with links to supporting and conflicting evidence |
| Data manifest | Raw/derived artifact locations, checksums, size, and backup status |

Large recordings live in designated data storage; Git holds code, protocols,
small manifests, and reports. Persistent storage and backup locations remain to
be chosen. Preserve raw observations and prior analyses. Append corrections and
link superseding interpretations instead of silently rewriting original records.

Each experiment record must contain:

- Experiment, session, sample, and culture/batch IDs; sample preparation and
  relevant light history; start/end times and completion/abort status.
- Hardware/setup and calibration identifiers, source commit, analysis parameters,
  camera settings, and environmental measurements when available. Mark unknown
  values explicitly.
- The question, protocol, decision rationale, assumptions, and predictions recorded
  before intervention; mark open exploration as such.
- Requested LED states, command/acknowledgement timestamps, and measured/applied
  states when available. A sent command is not proof of optical output.
- Raw recordings, derived tracks/metrics, file checksums, quality checks, errors,
  exclusions with reasons, and all unsuccessful trials.
- Observations separated from interpretation, alternative explanations, uncertainty,
  hypothesis updates, and the next useful test.

Start the hypothesis register only when there is a concrete question to track.
Keep novelty claims provisional until the result survives confirmation and a
targeted literature comparison.

## Token and spending budgets

The user's daily token allowance is a ceiling, not a target to spend. Its exact
value and accounting definition remain unset. Report input, cached input, output,
and reasoning usage separately where the runtime exposes them. Verify which
fields overlap before summing; do not double-count cached or reasoning subsets.
Include planning, analysis, visual inspection, retries, reporting, and any delegated
model calls in the agreed accounting scope. Track monetary cost separately when
models or rates differ; subscription allowances are not interchangeable with API
token prices.

An external runner must persist usage across restarts and concurrent calls,
reserve budget before dispatching work, prevent overlapping hardware sessions,
and stop launching work when the remaining allowance is insufficient. Reserve
capacity for reporting and closure. A failed call with unknown usage must not be
treated as free. Changing the date must not reset usage for an already active run.

Codex provides machine-readable usage events, but an exact arbitrary daily cutoff
has not been implemented or verified here. Usage may be finalized after a request;
use conservative admission limits and supported request caps where available.
Report any overshoot or accounting uncertainty. If a strict ceiling cannot be
guaranteed by the chosen runtime, stop early and disclose that limitation before
enabling unattended operation. Shutdown and basic checkpointing must work without
an additional model request.

References checked on 2026-10-29:

- [Codex scripted execution and usage events](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Codex app-server events](https://learn.chatgpt.com/docs/app-server)

Local inspection: `codex-cli 0.166.0`; `codex exec --help` exposes JSON event output
but no dedicated daily token-budget option. No model invocation or budget test
was performed to validate an enforcement mechanism.
