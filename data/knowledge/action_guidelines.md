# Action Recommendation Logic

## Overview

This document defines the decision logic used by Insurance Copilot to produce prioritised actions from performance gaps, competition progress, pending premium, and attribution indicators.

## Core Decision Tree

### Step 1: Assess Pending Premium

```text
Pending premium > 0?
├── Yes: prioritise follow-up on pending policies
│   ├── Pending amount > 50% of the gap
│   │   └── Focus on outstanding underwriting actions because approval could substantially reduce the gap.
│   ├── Pending amount > 20% of the gap
│   │   └── Accelerate underwriting while continuing new-business activity.
│   └── Pending amount < 20% of the gap
│       └── Pending premium has limited impact; place greater emphasis on new opportunities.
└── No: continue to Step 2
```

### Step 2: Assess Gap Size

```text
Completion rate = current / target
├── At least 80%: sprint stage
│   ├── Message: the target is close; concentrate effort on completion.
│   └── Action: prioritise existing-client reviews and active proposals.
├── 50%–79%: steady progress
│   ├── Message: progress is reasonable; maintain a consistent cadence.
│   └── Action: balance prospecting with existing-client service.
├── 30%–49%: acceleration required
│   ├── Message: progress is behind plan and activity must increase.
│   └── Action: increase weekly meetings and broaden lead sources.
└── Below 30%: warning
    ├── Message: progress is materially behind plan; prepare a recovery plan with a supervisor.
    └── Action: review the full sales pipeline and request team support.
```

### Step 3: Assess Time Urgency

```text
Remaining days = deadline - current date
├── 30 days or fewer: urgent
│   └── Raise priority and review progress daily.
├── 31–60 days: attention required
│   └── Set weekly targets and review them regularly.
├── 61–90 days: normal
│   └── Continue according to plan.
└── More than 90 days: sufficient time
    └── Treat as a medium- or long-term objective.
```

### Step 4: Generate Attribution-Based Actions

Use underperforming attribution indicators to select targeted recommendations.

#### Insufficient Lead Follow-up

```text
Condition: lead_conversion_rate < peer_avg or response_hours > peer_avg
Actions:
- Set a target for the first response within four hours.
- Follow up each qualified lead at least three times.
- Use AI practice sessions to improve needs analysis and objection handling.
```

#### Low Activity Participation

```text
Condition: activity indicators < peer_avg
Actions:
- Attend at least two client activities this month.
- Co-host one seminar with an experienced colleague.
- Publish one or two useful professional updates each week.
```

#### Unbalanced Product Mix

```text
Condition: protection product share < 40%
Actions:
- Review whether the low protection share is reducing FYC and competition progress.
- Discuss a suitable protection-and-savings combination where client needs support it.
- Explain how product mix affects average FYC without making unsuitable recommendations.
```

#### Low AI Practice Usage

```text
Condition: training_sessions < peer_avg
Actions:
- Complete at least two AI-supported sales practice sessions each week.
- Focus practice on objection handling, needs analysis, and product explanation.
```

## Recommendation Priority Rules

After generating applicable actions, order them as follows:

1. **Highest priority:** competition or honour deadline within 30 days with a remaining gap.
2. **High priority:** pending-policy follow-up that can directly convert into recognised performance.
3. **Medium priority:** attribution dimensions materially below the peer benchmark.
4. **Routine:** medium-term planning and capability development.

## Suggested Output Structure

```text
Recommended actions, ordered by priority

1. Urgent — Quarterly Sprint, X days remaining
   Gap: Y cases
   Recommended action: ...

2. Important — Follow pending policies
   Pending amount: HKD XXX,XXX
   Recommended action: ...

3. Improvement — Strengthen lead follow-up
   Current versus peer benchmark: ...
   Recommended action: ...
```

## Compliance Notes

- Recommendations are for internal decision support and do not constitute investment advice.
- Recommendations must not present an unsuitable product as the only solution.
- Results depend on internal system records and should be checked with a supervisor when data is uncertain.
- The system does not promise or guarantee performance outcomes.
