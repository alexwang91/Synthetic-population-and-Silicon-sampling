# ADR 0001: Aggregate weighted discrete choices, not score tables

## Status

Accepted

## Context

This repository simulates representative synthetic respondents for product-choice scenarios. Several stages produce diagnostics such as utilities, softmax probabilities, confidence labels, and reason codes. Those diagnostics are useful for development and quality review, but they are not respondent-level market-share observations.

The repository's product boundary is that each respondent produces exactly one discrete choice. Market summaries must aggregate those choices with `population_weight`.

## Decision

All market-share, segment-lift, interval, dashboard, and report surfaces must use weighted discrete choices as the primary outcome.

Diagnostic scores and probabilities may be emitted only under diagnostic fields. They must not replace `choice` as the aggregation source.

## Consequences

- Every choice result row must include `choice` and `population_weight`.
- Validators should fail rows that do not produce a discrete choice contract.
- Reports must identify uncalibrated rule-based or synthetic LLM outputs as hypotheses, not observed consumer behavior.
- Future calibrated models may change how choices are generated, but the aggregation contract remains weighted discrete choice aggregation.
