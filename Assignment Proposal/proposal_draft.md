# UniPlan: Project Proposal

**Team:** TUT04-06

## Table of Contents

- [1. Title and Abstract](#1-title-and-abstract)
- [2. Objectives and Motivation](#2-objectives-and-motivation)
- [3. Proposed Method and Work Plan](#3-proposed-method-and-work-plan)
- [4. Stakeholders, Impact and Ethics](#4-stakeholders-impact-and-ethics)
- [5. Team Organisation](#5-team-organisation)
- [References](#references)
- [Appendix A. Generative AI Use Record](#appendix-a-generative-ai-use-record)

## 1. Title and Abstract

**Title:** *UniPlan: Learning Student Preferences for Feasible Timetable Recommendations*

**Abstract:** UniPlan will help engineering students plan around commuting, employment and care. It will query public University of Sydney timetables by unit code, enforce scheduling constraints, and learn preferences from students' comparisons of feasible schedules. An interpretable model will recommend up to three explained alternatives. A four-week prototype will test prediction accuracy, feasibility and planning time against non-learning baselines.

## 2. Objectives and Motivation

A commuter may prioritise fewer campus visits; a working student may require particular afternoons free. Timetabling research distinguishes constraints from preferences [3] and considers individual schedules and gaps [4,5]. UniPlan will apply these principles to existing class options, leaving official allocation unchanged [1].

The AI for Good objective is less effort without prescribing universal preferences. Our hypothesis is that choosing between examples will express trade-offs better than setting numeric weights. Learning will estimate a particular student's probability of preferring schedule A over B, not enrolment success. Testing will cover three or four units per request.

## 3. Proposed Method and Work Plan

**Data and scope.** A scraper will query the public timetable [2] by requested unit code and semester, caching a timestamped snapshot. Unavailable codes will be flagged; manual collection will cover failed automated access. No private accounts will be accessed.

| Dataset / source | Fields / record unit | Purpose |
| --- | --- | --- |
| `meetings`: public timetable | One dated meeting: `unit_code`, `group_id`, `option_id`, `date`, `start_min`, `end_min`, `building`, `status` | Construct schedules; retain every meeting sharing an option. |
| `requirements`: checked published requirements | One required group: `unit_code`, `group_id`, `source_url`, `snapshot_time` | Verify group coverage and snapshot provenance. |
| `profiles`: student form | One student: `profile_id`, `unit_codes`, `unavailable_windows`, `preferred_hours`, `transition_min`, `weights` | Hard constraints, personalised features and baseline priorities. |
| `features`: generated schedules | One candidate/profile: `candidate_id`, `profile_id`, `option_ids`, `gap_min`, `campus_days`, `outside_min` | Model inputs and explanations. |
| `choices`: consented comparisons | One pair: `profile_id`, `candidate_A`, `candidate_B`, `choice`, `split` | Supervised labels: A=1, B=0; ties recorded separately. |

**1. Prepare and constrain.** Python/pandas will expand recurrence dates, convert Sydney-local times to minutes, deduplicate rows and validate identifiers/time order. Another reviewer will verify retained records against sources. Unresolved times/dates, links or requirements will exclude units pending verification. Unknown buildings/status will trigger warnings.

Backtracking will choose one option per required group, retaining linked meetings [5]. Same-date overlaps, unavailable windows, explicitly full classes and insufficient user-specified buffers between known different buildings will reject branches. Dates will distinguish alternating-week classes. Empty results will explain constraints without relaxing them. Learning will rank feasible schedules only; coefficients cannot override constraints.

**2. Engineer features and benchmarks.** Per candidate, G will sum between-class gaps, D attendance days, and O minutes outside preferred hours. Weekly means will use identical teaching weeks, including empty weeks. Following preference/gap objectives [4], inputs will be x=(G/300,D/5,O/120). These scales are design choices, not validated thresholds. A ±25% sensitivity check will measure top-three membership changes.

Baselines will rank by ascending equal-weight sum and student-weighted sum w·x. Weights will be nonnegative and sum to one; blank priorities will default to equal weights.

**3. Learn and recommend.** Four-week recruitment capacity motivates a 16-student consented pilot, not a powered population study; individual accuracy estimates from four tests will be unstable. Farthest-point sampling will select ten feasible schedules with distinct normalised feature vectors. A seeded split will reserve six for training and four for testing before pairing. Twelve unique training pairs will prioritise opposing feature trade-offs; four test pairs will be sampled uniformly. Display order will be randomised. Ties will be reported and excluded from binary accuracy.

A separate L2-regularised logistic model per student will use feature differences:

P(A preferred)=sigmoid(β·(x_A−x_B)).

Three interpretable coefficients and fixed regularisation C=1 will avoid tuning on tiny test sets. No intercept will preserve order symmetry; mirrored training pairs will provide both label orientations. Candidates will rank by descending utility β·x. Up to three results will display feature values, coefficient contributions and snapshot warnings. Insufficient distinct schedules or responses will trigger baseline recommendations and incomplete-validation reporting.

**4. Evaluate and deliver.** Twenty hand-solved cases covering date exceptions, linked meetings, missing data and impossible requests will require exact feasible-set matches. Held-out pair accuracy will be averaged across students and compared with both baselines and 50% chance; ties in predictions will receive half-credit. We will report participant-level outcomes, participant-bootstrap confidence intervals and recruitment shortfalls.

Six to ten participants will compare raw tables, weighted ranking and learned ranking on equivalent tasks with counterbalanced order. First-use timing will span course/preference entry to timetable acceptance, including weights or 12 training comparisons, computation and review; research tests/questionnaires will be timed separately. Learning must outperform the stronger baseline in mean test accuracy; usability targets will be 20% lower median completion time than raw tables, zero hard violations and 80% correct explanation interpretation. Top-three acceptance will be reported. These are prospective targets. Failure will trigger baseline use: poor training/test accuracy will prompt label/feature checks; a training–test gap will prompt overfitting checks. Revisions will require fresh test data.

| Week | Deliverable |
| --- | --- |
| 1 | Snapshot, consent, recruitment |
| 2 | Constraints, features, comparison form |
| 3 | Labels, models, interface |
| 4 | Frozen-test evaluation, report |

## 4. Stakeholders, Impact and Ethics

Students will benefit from explained choices; advisers may help interpret conflicts. Shared priorities could concentrate demand on popular classes, so recommendations will not guarantee seats. Commuter under-recruitment could conceal poor usability; recruitment will seek varied schedules and report coverage. User-defined transition buffers will accommodate differing mobility needs without claiming accessible routes.

Consent will cover preferences and choices, with withdrawal by random profile code before anonymised reporting. No names, IDs or reasons for unavailability will be collected. Team-only records will be deleted after assessment. Snapshot dates, unknown-data warnings and official verification will address stale information. Users may override ranking; scores will indicate preference, not objective quality.

## 5. Team Organisation

TUT04-06 will organise workstreams covering data/constraints, preference learning, interface, and evaluation/ethics. Weekly integration, cross-review and a contribution log will track delivery. Recruitment delays will reduce evaluation scope.

## References

1. University of Sydney. *Class timetables*. https://www.sydney.edu.au/students/timetables.html (accessed 20 September 2026).
2. University of Sydney. *2026 Timetable*. https://timetable.sydney.edu.au/even/timetable/ (accessed 20 September 2026).

3. H. Alghamdi, T. Alsubait, H. Alhakami, and A. Baz (2020). A Review of Optimization Algorithms for University Timetable Scheduling. *Engineering, Technology & Applied Science Research*, 10(6), 6410–6417. https://doi.org/10.48084/etasr.3832
4. F. Dunke and S. Nickel (2023). A matheuristic for customized multi-level multi-criteria university timetabling. *Annals of Operations Research*, 328, 1313–1348. https://doi.org/10.1007/s10479-023-05325-2
5. E. Steiner, U. Pferschy, and A. Schaerf (2025). Curriculum-based university course timetabling considering individual course of studies. *Central European Journal of Operations Research*, 33, 277–314. Published online 21 June 2024. https://doi.org/10.1007/s10100-024-00923-2

## Appendix A. Generative AI Use Record

The following selected technical exchanges with OpenAI Codex are translated from the original Chinese dialogue. They cover candidate sampling, evaluation time, sample size, feasibility constraints and failure diagnosis. These are excerpts from the wider conversation, not a complete transcript. In addition to these technical discussions, OpenAI Codex assisted with drafting, revision, translation and formatting of the proposal. Responses refer to the draft at the time of each exchange.

## Technical discussion 1 --- 20 September 2026, 13:52 AEST

**User**

Selected passage: The current draft has moved from being specific to having methods that align with evaluation, giving it a basis for aiming at HD. Clarifying candidate timetable sampling and the definition of time cost would be more useful than adding further algorithms or references.

What are these two things? What do you need?

**Codex**

These are two details that need to be clarified in the method description, not two additional datasets that you need to find.

1. Candidate timetable sampling: which timetables should students compare?

The system may generate dozens of feasible timetables, but we select only ten for training and testing. If they are very similar, we cannot learn how students make trade-offs.

For example, the selection should cover:
- Fewer campus days but longer gaps between classes.
- More campus days but compact daily schedules.
- Short gaps but early or late classes.

I suggest specifying that ten distinct timetables are selected using the three features, avoiding duplicate feature vectors. Training and test timetables should be separated before comparison pairs are generated. Training comparisons should include these trade-offs rather than consist entirely of easy choices in which one option is clearly better.

2. Time-cost definition: when does timing begin?

The learning model requires students to compare 12 pairs of timetables first. This is part of the cost of using the system. Counting only the time spent choosing after recommendations appear would be unfair to raw tables or manually weighted methods.

I suggest measuring total first-use time:

From entering courses and preferences to confirming an acceptable timetable, including the form, setting weights or completing 12 training comparisons, computation time and reviewing recommendations. Research-only test questions and feedback questionnaires should be recorded separately.

I do not currently need additional material from you to include these points in the proposal. Real timetable data and participants will be needed during implementation. Once training-comparison time is included, the learning approach may not be faster on first use. This must be tested rather than guaranteed in advance.

## Technical discussion 2 --- 20 September 2026, 13:56 AEST

**User**

1. The quantitative basis in Project Goals is weak.
The main selling point, less planning time, currently rests entirely on assumptions. There are no data showing average planning time with existing tools or manual methods, or the effects of similar preference-learning systems in other settings. Even one or two figures, such as the average number of minutes students spend deciding on a timetable, could turn a reasonable assumption into an evidence-supported objective.

2. The statistical explanation for a sample of 16 is missing.
A pilot with 16 students and 16 comparisons each is acceptable for feasibility research, but the proposal does not explain why 16 rather than 10 or 20, how wide confidence intervals might be, or how limited generalisability would be. Even a sentence explaining that the sample is constrained by the four-week timeline and provides only feasibility evidence would address this gap.

3. The tension between objectivity and subjectivity is not explicitly addressed.
The model learns students' pairwise preferences, but timetabling also involves objective feasibility, such as conflicts and buffer time. Could these judgements interfere with each other when combined in G/D/O? For example, a student may prefer a timetable because of tight commuting time, while the learned coefficient could be misread as objectively better. The statement that scores express preference rather than objective quality is only a disclaimer; the method does not explain how to mitigate this confusion.

4. Responses to failure modes are not developed.
The proposal repeatedly says that these are prospective targets and that failure will lead to the baseline. That is honest, but it does not explain how the team would diagnose worse-than-baseline performance: insufficient data, poor features or excessive variance in individual models. A sentence or two about likely failure causes and initial checks would make the technical account more complete.

Are these reasonable comments?

**Codex**

The four comments are broadly reasonable. Points 2, 3 and 4 are worth implementing directly. Point 1 is directionally right, but we should not cite an unsuitable study merely to include a number.

Assessment of the comments:
1. Lack of quantitative support: partly valid. Existing literature supports the problem and methodological direction, but not a 20% time saving. The HD criteria also accept well-reasoned justification; they do not require existing time-use statistics.
2. Lack of justification for 16 participants: valid. This should be described as a feasibility sample under four-week resource constraints, rather than a confirmatory sample determined by a statistical power calculation.
3. Confusion between objective feasibility and subjective preferences: the risk is valid, but the interpretation of the current structure needs correcting. Hard constraints are not scored together with G/D/O; they filter schedules before ranking. This boundary needs to be clearer.
4. Insufficient failure diagnosis: valid. Returning to a baseline is a product response, not a research diagnosis. The proposal should explain how causes will be investigated.

1. Quantitative evidence: add evidence where appropriate, but do not force in a number of minutes.

The 20% figure is currently a success target we set, not an expected effect derived from the literature. This distinction must remain. Results from similar systems in other settings can support the value of the research but cannot directly establish how much time UniPlan will save.

If no credible, comparable study of student timetable-planning time can be found, it is better to write:

Existing planning time remains to be measured; the raw-timetable condition will establish a local benchmark, and 20% is a predefined project target.

The suggestion that one or two figures would make the objective evidence-supported is therefore slightly too strong. What matters is whether the figures match the users, task and comparison conditions.

2. Sample size: this should be added.

The current draft says feasibility pilot and plans confidence intervals, but it does not explain the choice of 16 students.

We can clarify:

Sixteen is the target sample that can be recruited and labelled within four weeks; the results assess feasibility and do not support population-wide generalisation.

In particular, 16 people making 16 comparisons each do not constitute 256 independent participants. Each person provides only four test judgements, so individual accuracy will be unstable. Interval widths depend on the observed results and differences between participants; they cannot be invented now.

3. Objective versus subjective judgement: strengthen structural separation, not just a disclaimer.

The current workflow is: check hard constraints, retain only feasible timetables, then learn preferences and rank using G/D/O.

Even if the model strongly favours a schedule, it must not reintroduce a schedule that violates constraints. G/D/O are measurable attributes; the value assigned to those attributes is subjective.

I suggest stating three points:
- Independent rules verify hard constraints; learned coefficients cannot override them.
- The interface separately displays constraint checks and reasons for preference ranking.
- Restrictions such as commuting that are not sufficiently represented by the features should be declared by users as constraints. Coefficients should not be interpreted as causal effects of those factors.

A transition buffer is also a user-provided requirement, not a verified objective walking time.

4. Failure diagnosis: this is a particularly useful addition to the technical account.

We can specify in advance:
- Poor training and test performance: check ambiguous labels, insufficient feature coverage or trade-offs the linear model cannot represent.
- Good training but poor test performance: check overfitting, insufficient diversity in training comparisons and coefficient instability caused by the small sample.
- Failure for only some students: check whether their needs extend beyond G/D/O.

However, subsequent tuning or feature changes should use training or new data. Repeatedly inspecting the original test set and modifying the model does not leave it as an independent test.

My recommendation is to accept the central direction of all four comments, prioritising the sample's purpose, separation of hard constraints from learned ranking, and failure diagnosis. Quantitative background should be checked first; if suitable data cannot be found, explicitly establish a local benchmark. The body is already close to 1,000 words, so repetitive wording should be replaced rather than four new paragraphs simply added.

