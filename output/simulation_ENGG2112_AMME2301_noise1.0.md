# Preference-learning simulation: ENGG2112 + AMME2301

172 distinct feasible profiles · 300 synthetic students per setting · population `mixed` (Dirichlet α = (1.0, 1.0, 1.0) over G, D, O) · weight-report noise σ = 1.0 · seed 2112.
Values are means ± 95% CI half-widths across students. Agreement is over 3,000 sampled profile pairs; regret is in x units (0 = picked the student's best).

## Decisiveness s = 5.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.847 ± 0.010 | 0.018 ± 0.004 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.690 ± 0.017 | 0.163 ± 0.018 | — | — |
| baseline · self-reported weights | 0.883 ± 0.010 | 0.028 ± 0.007 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.683 ± 0.018 | 0.163 ± 0.018 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.778 ± 0.018 | 0.082 ± 0.012 | 0.657 ± 0.027 | 0.34 |
| learned · standardised x, C=1, prior 0 | 0.779 ± 0.019 | 0.076 ± 0.014 | 0.667 ± 0.026 | 0.33 |
| learned · app default (standardised, equal-weight prior) | 0.815 ± 0.016 | 0.062 ± 0.012 | 0.687 ± 0.027 | 0.30 |
| learned · app default with random pairs | 0.811 ± 0.015 | 0.065 ± 0.011 | 0.660 ± 0.028 | 0.28 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 16% of students; the held-out pair verdict matches that truth for 72%.
- App-default learner truly beats the stronger baseline for 22% of students; the held-out pair verdict matches that truth for 70%.

## Decisiveness s = 10.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.847 ± 0.010 | 0.018 ± 0.004 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.690 ± 0.017 | 0.163 ± 0.018 | — | — |
| baseline · self-reported weights | 0.883 ± 0.010 | 0.028 ± 0.007 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.683 ± 0.018 | 0.163 ± 0.018 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.829 ± 0.013 | 0.052 ± 0.008 | 0.743 ± 0.026 | 0.30 |
| learned · standardised x, C=1, prior 0 | 0.862 ± 0.012 | 0.037 ± 0.008 | 0.775 ± 0.023 | 0.25 |
| learned · app default (standardised, equal-weight prior) | 0.886 ± 0.009 | 0.026 ± 0.005 | 0.792 ± 0.022 | 0.12 |
| learned · app default with random pairs | 0.883 ± 0.009 | 0.025 ± 0.004 | 0.791 ± 0.025 | 0.19 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 25% of students; the held-out pair verdict matches that truth for 69%.
- App-default learner truly beats the stronger baseline for 35% of students; the held-out pair verdict matches that truth for 62%.

## Decisiveness s = 20.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.847 ± 0.010 | 0.018 ± 0.004 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.690 ± 0.017 | 0.163 ± 0.018 | — | — |
| baseline · self-reported weights | 0.883 ± 0.010 | 0.028 ± 0.007 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.683 ± 0.018 | 0.163 ± 0.018 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.852 ± 0.011 | 0.040 ± 0.006 | 0.806 ± 0.023 | 0.40 |
| learned · standardised x, C=1, prior 0 | 0.899 ± 0.008 | 0.017 ± 0.003 | 0.852 ± 0.021 | 0.27 |
| learned · app default (standardised, equal-weight prior) | 0.923 ± 0.006 | 0.013 ± 0.003 | 0.877 ± 0.019 | 0.16 |
| learned · app default with random pairs | 0.915 ± 0.007 | 0.016 ± 0.003 | 0.856 ± 0.019 | 0.19 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 28% of students; the held-out pair verdict matches that truth for 69%.
- App-default learner truly beats the stronger baseline for 53% of students; the held-out pair verdict matches that truth for 55%.

