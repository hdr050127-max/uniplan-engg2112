# Preference-learning simulation: ENGG2112 + AMME2301

172 distinct feasible profiles · 300 synthetic students per setting · population `commuter` (Dirichlet α = (0.5, 3.0, 1.0) over G, D, O) · weight-report noise σ = 1.0 · seed 2112.
Values are means ± 95% CI half-widths across students. Agreement is over 3,000 sampled profile pairs; regret is in x units (0 = picked the student's best).

## Decisiveness s = 5.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.725 ± 0.010 | 0.082 ± 0.007 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.841 ± 0.010 | 0.018 ± 0.005 | — | — |
| baseline · self-reported weights | 0.915 ± 0.010 | 0.016 ± 0.004 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.866 ± 0.012 | 0.018 ± 0.005 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.685 ± 0.018 | 0.108 ± 0.013 | 0.589 ± 0.031 | 0.37 |
| learned · standardised x, C=1, prior 0 | 0.720 ± 0.020 | 0.102 ± 0.013 | 0.606 ± 0.030 | 0.36 |
| learned · app default (standardised, equal-weight prior) | 0.761 ± 0.018 | 0.089 ± 0.012 | 0.615 ± 0.030 | 0.35 |
| learned · app default with random pairs | 0.788 ± 0.016 | 0.065 ± 0.010 | 0.641 ± 0.028 | 0.21 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 5% of students; the held-out pair verdict matches that truth for 84%.
- App-default learner truly beats the stronger baseline for 15% of students; the held-out pair verdict matches that truth for 77%.

## Decisiveness s = 10.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.725 ± 0.010 | 0.082 ± 0.007 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.841 ± 0.010 | 0.018 ± 0.005 | — | — |
| baseline · self-reported weights | 0.915 ± 0.010 | 0.016 ± 0.004 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.866 ± 0.012 | 0.018 ± 0.005 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.755 ± 0.014 | 0.059 ± 0.007 | 0.685 ± 0.029 | 0.45 |
| learned · standardised x, C=1, prior 0 | 0.825 ± 0.014 | 0.040 ± 0.008 | 0.723 ± 0.028 | 0.33 |
| learned · app default (standardised, equal-weight prior) | 0.864 ± 0.011 | 0.028 ± 0.006 | 0.741 ± 0.026 | 0.31 |
| learned · app default with random pairs | 0.869 ± 0.010 | 0.025 ± 0.006 | 0.755 ± 0.025 | 0.04 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 8% of students; the held-out pair verdict matches that truth for 79%.
- App-default learner truly beats the stronger baseline for 29% of students; the held-out pair verdict matches that truth for 69%.

## Decisiveness s = 20.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.725 ± 0.010 | 0.082 ± 0.007 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.841 ± 0.010 | 0.018 ± 0.005 | — | — |
| baseline · self-reported weights | 0.915 ± 0.010 | 0.016 ± 0.004 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.866 ± 0.012 | 0.018 ± 0.005 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.762 ± 0.012 | 0.054 ± 0.006 | 0.713 ± 0.029 | 0.45 |
| learned · standardised x, C=1, prior 0 | 0.867 ± 0.010 | 0.020 ± 0.004 | 0.850 ± 0.022 | 0.23 |
| learned · app default (standardised, equal-weight prior) | 0.905 ± 0.007 | 0.009 ± 0.003 | 0.868 ± 0.020 | 0.18 |
| learned · app default with random pairs | 0.909 ± 0.007 | 0.009 ± 0.003 | 0.853 ± 0.019 | 0.16 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 11% of students; the held-out pair verdict matches that truth for 83%.
- App-default learner truly beats the stronger baseline for 38% of students; the held-out pair verdict matches that truth for 67%.

