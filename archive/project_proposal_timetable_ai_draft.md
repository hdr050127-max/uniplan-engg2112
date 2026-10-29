# Project Proposal Draft

## Title

AI-assisted timetable planning support for engineering students

## Project Aim

This project aims to build a small AI-assisted timetable planning tool that helps engineering students make better timetable choices using public class information such as class time, location, activity type, teaching weeks, and available seats. The goal is not to replace the university timetable system or automatically enrol students into classes. Instead, the project focuses on helping students compare timetable options more clearly, especially when they need to balance travel time, workload, class availability, and personal constraints.

## Problem and Motivation

University timetable planning can be stressful because students often need to compare many class options across different units. A class may be technically available, but still be a poor choice if it creates long campus walks, awkward gaps, back-to-back sessions in distant buildings, or a high risk of becoming full. This can be harder for first-year students, commuting students, students with work commitments, and students unfamiliar with campus buildings.

This problem links to the "AI for Good" theme because the project uses AI to improve access, reduce planning stress, and support better student decision-making. A responsible system should make timetable information easier to understand, while still leaving final decisions to students and following university rules around data access and privacy.

## Proposed Solution

The proposed system will take public timetable data for selected engineering units and turn it into a clear decision-support tool. For each possible class option or timetable combination, the tool could estimate a "schedule difficulty" or "student convenience" score based on features such as:

- time of day
- day of week
- class duration
- number of teaching weeks
- available seats
- campus location
- travel time between back-to-back classes
- size of gaps between classes
- number of days students need to come to campus

The output could be a ranked list or simple dashboard showing which timetable choices are likely to be easier, riskier, or less convenient. The model should also explain why an option receives a particular score, for example: "low seat availability", "long gap", or "back-to-back classes in distant buildings".

## Data Sources and Feasibility

An initial feasibility check has already been completed using ENGG2112 as a sample unit. The public Sydney Timetable page returned class-level information including semester, activity type, day, start time, duration, location, teaching dates, and available seats. For ENGG2112, the extracted data included both Semester 1 and Semester 2 lecture and tutorial options.

The current local prototype data includes:

- `usyd_ENGG2112_timetable_2026_public.csv`: class time, location, teaching dates, and availability for ENGG2112
- `usyd_mechanical_engineering_unit_details_2026_public.csv`: public unit information for selected mechanical engineering units
- `usyd_mechanical_engineering_assessments_2026_public.csv`: assessment information from public unit outline pages
- `usyd_mechanical_engineering_weekly_schedule_2026_public.csv`: weekly topic and learning activity information from public unit outline pages

The timetable data source should be treated carefully. The project should avoid uncontrolled bulk scraping. A responsible data collection plan would use small, cached, unit-level queries, public unit pages, or manually exported timetable data where possible. The proposal should describe the data source as suitable for a prototype, not as a guaranteed large-scale official API.

## AI / Machine Learning Approach

The project can begin with an interpretable baseline model and then compare it with a machine learning model.

The baseline system can use transparent rules, such as:

- lower score if available seats are very low
- lower score if two classes are far apart with little transition time
- lower score if the timetable creates many isolated campus visits
- higher score if classes are grouped efficiently on fewer days

The machine learning component could then be built in one of two ways:

1. Supervised learning: collect a small anonymous survey where students rate example timetable options as "good", "acceptable", or "difficult". A model such as logistic regression, decision tree, or random forest can learn which timetable features best predict student preference.

2. Ranking or clustering: if labelled survey data is limited, the project can group timetable options into clusters such as "seat risk", "travel risk", "gap-heavy", and "balanced". This would still provide useful decision support while avoiding overclaiming prediction accuracy.

Because this is a student-facing support tool, interpretable models are preferred. A simpler model that students can understand may be more appropriate than a complex black-box model.

## Evaluation Plan

The project can be evaluated in two ways.

First, the technical model can be compared against a simple rule-based baseline. Metrics may include accuracy or F1 score for classification, or ranking agreement if students are asked to rank timetable options. Cross-validation can be used if enough labelled examples are collected.

Second, the usefulness of the tool can be evaluated through a small user study. Students could be asked to compare raw timetable information with the tool's ranked output. Useful evaluation questions include:

- Does the tool reduce the time needed to compare timetable options?
- Are the explanations clear?
- Do students agree with the risk or convenience scores?
- Does the tool help students notice issues they may otherwise miss?

## Ethical and Responsible AI Considerations

This project should avoid collecting sensitive personal data unless it is clearly necessary and consented to. The first version can work with public timetable data and anonymous preference labels only. The system should not access private student accounts, make enrolment decisions, or claim that one timetable is objectively best for everyone.

Potential ethical issues include:

- Privacy: student constraints and preferences should be anonymous or optional.
- Fairness: the model should not assume all students have the same travel time, work schedule, mobility, or caring responsibilities.
- Transparency: the tool should explain its scores instead of only giving a recommendation.
- Data reliability: seat availability and timetable details can change, so the tool should show when data was last updated.
- Compliance: data collection should respect public website rules and avoid high-frequency scraping.

## Expected Outcome

By the end of the project, the team aims to produce:

- a cleaned dataset for selected engineering units
- a notebook or script that extracts timetable features
- a baseline scoring method
- a small machine learning model or clustering method
- a simple visual output or dashboard
- a final discussion of model limitations, ethics, and connection to AI for Good

The project is feasible because a small ENGG2112 timetable dataset has already been extracted successfully. The next step is to narrow the scope, decide whether to use supervised preference labels or unsupervised grouping, and build a first prototype using one or two units before expanding to more mechanical engineering units.

