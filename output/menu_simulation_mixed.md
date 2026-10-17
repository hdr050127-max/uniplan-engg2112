# Menu-choice pilot simulation

Menu library: 86 shortlists from 4 course combinations under random constraints. Menu size: median 4, range 2–9; 0 of 86 have a single plan (no choice needed) and are excluded below.
Population `mixed` (Dirichlet α = (1.0, 1.0, 1.0)), decisiveness s = 10.0, 40 simulated pilots per row, seed 2112.
Estimand: the pooled model's signed influence share on campus days D (rule scales). Reference from a 4,000-student fit: 0.28 (population mean weight 0.33; the pooled fit also reflects how decisively each group chooses).

Pooled logit = conditional logit shrunk toward equal weights (λ = 1). Accuracy = leave-one-participant-out top-1 accuracy predicting the plan chosen from a menu.

| Participants × menus each | Pooled logit | Equal weights | Fewest days | Random | D weight 95% CI (median half-width) | CI covers reference |
| --- | --- | --- | --- | --- | --- | --- |
| 16 × 1 | 0.40 | 0.43 | 0.23 | 0.29 | ± 0.38 | 90% |
| 16 × 3 | 0.45 | 0.44 | 0.27 | 0.30 | ± 0.37 | 92% |
| 40 × 3 | 0.45 | 0.45 | 0.27 | 0.30 | ± 0.38 | 95% |
| 100 × 3 | 0.44 | 0.45 | 0.26 | 0.30 | ± 0.25 | 92% |
