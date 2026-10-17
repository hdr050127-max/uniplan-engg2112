# Preference-learning simulation: ENGG2112 + AMME2262 + CIVL3206

59 distinct feasible profiles · 300 synthetic students per setting · population `mixed` (Dirichlet α = (1.0, 1.0, 1.0) over G, D, O) · weight-report noise σ = 0.5 · seed 2112.
Values are means ± 95% CI half-widths across students. Agreement is over 3,000 sampled profile pairs; regret is in x units (0 = picked the student's best).

## Decisiveness s = 5.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.900 ± 0.006 | 0.009 ± 0.003 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.631 ± 0.013 | 0.282 ± 0.023 | — | — |
| baseline · self-reported weights | 0.959 ± 0.005 | 0.006 ± 0.003 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.629 ± 0.013 | 0.282 ± 0.023 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.855 ± 0.019 | 0.052 ± 0.010 | 0.731 ± 0.027 | 0.37 |
| learned · standardised x, C=1, prior 0 | 0.855 ± 0.018 | 0.045 ± 0.010 | 0.723 ± 0.027 | 0.36 |
| learned · app default (standardised, equal-weight prior) | 0.896 ± 0.012 | 0.029 ± 0.007 | 0.739 ± 0.025 | 0.21 |
| learned · app default with random pairs | 0.885 ± 0.013 | 0.033 ± 0.008 | 0.698 ± 0.028 | 0.24 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 14% of students; the held-out pair verdict matches that truth for 82%.
- App-default learner truly beats the stronger baseline for 17% of students; the held-out pair verdict matches that truth for 79%.

## Decisiveness s = 10.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.900 ± 0.006 | 0.009 ± 0.003 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.631 ± 0.013 | 0.282 ± 0.023 | — | — |
| baseline · self-reported weights | 0.959 ± 0.005 | 0.006 ± 0.003 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.629 ± 0.013 | 0.282 ± 0.023 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.883 ± 0.016 | 0.033 ± 0.007 | 0.818 ± 0.023 | 0.43 |
| learned · standardised x, C=1, prior 0 | 0.903 ± 0.013 | 0.024 ± 0.005 | 0.821 ± 0.023 | 0.38 |
| learned · app default (standardised, equal-weight prior) | 0.931 ± 0.009 | 0.018 ± 0.004 | 0.839 ± 0.021 | 0.22 |
| learned · app default with random pairs | 0.929 ± 0.009 | 0.012 ± 0.003 | 0.816 ± 0.023 | 0.18 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 18% of students; the held-out pair verdict matches that truth for 79%.
- App-default learner truly beats the stronger baseline for 24% of students; the held-out pair verdict matches that truth for 74%.

## Decisiveness s = 20.0

| Method | True agreement | Top-1 regret | 4-pair test acc. | r(test, truth) |
| --- | --- | --- | --- | --- |
| baseline · equal weights | 0.900 ± 0.006 | 0.009 ± 0.003 | — | — |
| baseline · UI default (D 50% / O 50%) | 0.631 ± 0.013 | 0.282 ± 0.023 | — | — |
| baseline · self-reported weights | 0.959 ± 0.005 | 0.006 ± 0.003 | — | — |
| baseline · self-reported, G hidden (current UI) | 0.629 ± 0.013 | 0.282 ± 0.023 | — | — |
| learned · proposal (raw x, C=1, prior 0) | 0.895 ± 0.014 | 0.025 ± 0.005 | 0.872 ± 0.022 | 0.46 |
| learned · standardised x, C=1, prior 0 | 0.922 ± 0.011 | 0.017 ± 0.004 | 0.886 ± 0.019 | 0.33 |
| learned · app default (standardised, equal-weight prior) | 0.948 ± 0.007 | 0.011 ± 0.003 | 0.902 ± 0.017 | 0.29 |
| learned · app default with random pairs | 0.953 ± 0.005 | 0.009 ± 0.003 | 0.891 ± 0.020 | 0.24 |

Stronger baseline = better of equal weights and self-reported weights (with G), judged per student by true agreement.

- Proposal learner truly beats the stronger baseline for 19% of students; the held-out pair verdict matches that truth for 79%.
- App-default learner truly beats the stronger baseline for 31% of students; the held-out pair verdict matches that truth for 70%.

