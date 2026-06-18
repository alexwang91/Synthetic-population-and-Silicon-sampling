# Methodology Map

Use this file when deciding which method belongs in which layer of the pipeline.

## Method Routing

| Pipeline problem | Prefer | Use when | Avoid when |
|---|---|---|---|
| Fit a panel to known census margins | IPF/raking | You have marginal constraints and seed microdata or a seed table | High-order interactions drive the business question and only first-order margins are fit |
| Preserve fine-grained interactions | Poststratification, MRP, or multilevel calibration | Segment estimates depend on combinations such as region x education x income x age | Cells are too sparse and no shrinkage/regularization is used |
| Generate plausible soft variables | Conditional probability models, Bayesian networks, calibrated imputation | You have survey or behavioral sources for media, channel, category, or income behavior | The only source is an LLM story |
| Generate rich persona narratives | Taxonomy-guided persona expansion | You need coherent stories or deep casebooks | The narrative would be used as statistical evidence |
| Estimate stated preference and price tradeoffs | CBC/DCE, HB-MNL, mixed logit, latent class MNL | Products can be represented as alternatives with attributes and price | The task is a single direct rating with no tradeoff structure |
| Convert LLM text into rating-like purchase intent | SSR-style text-first mapping | Human survey benchmarks or reference statements exist | You only have raw numeric LLM ratings |
| Find preference-based segments | Latent class MNL, HB-MNL summaries, clustering on partworths | You have repeated choice tasks or simulated choice histories | You only have a single product-vote per persona |
| Estimate causal HTE/CATE/uplift | Causal forests, meta-learners, uplift models | There is randomized, quasi-experimental, or well-adjusted observational outcome data | You only have synthetic choice simulation |
| Report uncertainty | Bootstrap, repeated seeds, model version sensitivity, prompt sensitivity | Any market share, WTP, elasticity, HTE, or segment lift is reported | A single deterministic run is all that exists |

## Evidence Ladder

Use the strongest supported label:

| Evidence | Allowed language |
|---|---|
| Synthetic panel only | "simulated preference heterogeneity", "segment lift", "hypothesis" |
| Synthetic panel plus external survey benchmark | "survey-calibrated simulated lift" |
| Synthetic panel plus sales/click/conversion benchmark | "behavior-calibrated lift" |
| Randomized price/promotion/product experiment | "estimated HTE/CATE/uplift" |
| Client experiment with pre-registered analysis | "client-calibrated causal HTE" |

## Literature Anchors

- Argyle et al., "Out of One, Many": use demographic conditioning and evaluate algorithmic fidelity before treating LLM responses as population evidence.
- Bisbee et al., "Synthetic Replacements for Human Survey Data?": add variance, prompt sensitivity, reproducibility, and regression-coefficient checks.
- Lovelace et al., "Evaluating the Performance of Iterative Proportional Fitting for Spatial Microsimulation": use IPF for reconstructing microdata from aggregated geography, but test fit carefully.
- Ben-Michael, Feller, and Hartman, "Multilevel Calibration Weighting for Survey Data": use multilevel calibration or DRP when high-order interactions matter.
- DeepPersona: use taxonomy-guided, conditional attribute expansion for deep personas instead of one-shot persona generation.
- Brand, Israeli, and Ngwe, "Using LLMs for Market Research": treat LLM market research as an addition to human studies, with category-specific prior data improving reliability.
- Maier et al., "LLMs Reproduce Human Purchase Intent via SSR": elicit text first and map to distributions; avoid direct numeric Likert ratings when possible.
- Wager and Athey, "Estimation and Inference of Heterogeneous Treatment Effects using Random Forests": use causal forests for valid HTE inference when causal assumptions are supported.
- Kunzel et al., "Meta-learners for Estimating Heterogeneous Treatment Effects": use S/T/X/R/DR learner families when estimating CATE with flexible base learners.

## Self-Check Before Reporting

Before finalizing a design or report, answer:

1. Which variables are official controls, survey-calibrated, behavior-calibrated, imputed, or narrative-only?
2. Which interactions are essential for the market decision?
3. Does the method fit those interactions or only first-order margins?
4. Is the HTE label descriptive, preference-based, or causal?
5. What uncertainty comes from sampling, model assumptions, LLM prompt wording, and model version drift?
