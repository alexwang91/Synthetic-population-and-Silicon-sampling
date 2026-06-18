# Architecture

## Principle

Do not build this as one large prompt. Build a pipeline where deterministic data work controls population structure, digital respondents answer bounded product scenarios, and aggregation counts discrete choices.

## Nine Modules

1. Country Data Ingestion
2. Statistical Cell Builder
3. Population Synthesizer
4. Persona Attribute Expander
5. Narrative Persona Generator
6. Consistency Validator
7. Isolated Respondent Interview Runner
8. Pricing Sensitivity Runner
9. Calibration and Audit Reporter

## Responsibility Split

| Work | Owner |
|---|---|
| Statistical tables, source metadata | Programmatic data pipeline |
| Stratification, sampling, weights | Programmatic data pipeline |
| IPF/raking | Programmatic data pipeline |
| High-dimensional soft traits | Program plus conditional assumptions |
| Life stories | LLM, bounded by fixed fields |
| Coherence checks | Program plus LLM judge |
| Product choice answer | Digital respondent or LLM, identity-first and structured |
| Respondent isolation, seed, temperature, schema, prompt variant | Interview orchestration layer |
| Test-retest, prompt sensitivity, consistency judge | Quality-control layer |
| Choice aggregation | Programmatic count of weighted discrete choices |
| Scores or utilities | Optional diagnostics only |
| Final report | Program metrics plus LLM explanation |

## End-to-End Flow

1. Load country data pack.
2. Build marginal constraints.
3. Estimate joint distribution with IPF/raking or a documented alternative.
4. Sample person skeletons and assign population weights.
5. Expand soft variables with conditional models.
6. Generate story templates for archetypes or a narrative subset.
7. Validate consistency and repair only non-statistical fields.
8. Run isolated choice interview tasks against product alternatives. Each persona answers with a natural response and one parsed choice.
9. Validate interview contract, isolation controls, contamination red flags, and consistency-judge outputs.
10. Aggregate weighted discrete choices and segments.
11. Write audit report.

For natural-language product scenarios, read `product-scenario-workflow.md` first. It defines how to normalize inputs such as country, category, focal product, competitor, price, and features into the pipeline contract.

## Scale Design

Avoid 10,000 full LLM calls by default. Use 10,000 independent LLM micro-calls only when explicitly requested and budgeted.

Recommended tiers:

| Tier | Size | Use |
|---|---:|---|
| Core Panel | 10,000 | Structured fields for statistics |
| Shallow Interview Panel | 10,000 | Isolated micro-interviews or calibrated respondent engine for statistics |
| Medium Narrative Panel | 1,000 | Independent short LLM interviews for reason distribution |
| Deep Casebook | 100 to 300 | One isolated LLM conversation per case |

Generate structured records and shallow interview answers at full scale, narrative stories for representative archetypes, and deep stories only for a curated subset.

For the 100 / 1,000 / 10,000 depth strategy, read `sample-depth-tiers.md`. Use the largest shallow tier for denominators and intervals, not the deep casebook.

## MVP

For a four-week MVP, use one country, one category, 1,000 core records, 100 narratives, two product alternatives, weighted choice share, segment HTE, and an audit report.

Do not include full multi-country coverage, 10,000 long stories, long-term memory, social contagion, or claims of sales prediction.

## Full Product Decomposition

If the task is too broad for one skill execution, split it into five sub-systems:

1. Country Pack Builder
2. Weighted Persona Generator
3. Deep Persona Narrator
4. Choice Simulation Engine
5. Audit and Calibration Engine
