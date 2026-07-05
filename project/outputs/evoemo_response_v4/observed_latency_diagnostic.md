# EvoEmo Observed Online Latency Diagnostic

Source: `outputs/evoemo_selective/turns.jsonl`

Status: `DIAGNOSTIC`

This file summarizes latency fields recorded during EvoEmo selective generation.
The values describe observed online traces from user turn to generated response.
They exclude training, judging, and post hoc statistical analysis. Because the
generation run was not designed as a randomized latency benchmark, these numbers
should be reported as deployment diagnostics, while input tokens remain the
primary resource cost metric.

## Paper Conditions

| Condition | n | Mean latency ms | Median latency ms | P95 latency ms | Mean input tokens | Mean retrieval ms | Mean generation ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Context Only | 1020 | 665.0 | 546.4 | 1100.1 | 393.0 | 0.0 | 652.5 |
| Learned Selector | 1020 | 1952.5 | 1969.4 | 2627.2 | 1291.8 | 1214.1 | 723.2 |
| Rule Selector | 1020 | 3226.2 | 3274.7 | 4075.9 | 1624.0 | 2435.7 | 783.8 |
| Fixed All Structured | 1020 | 2015.3 | 1975.5 | 2602.7 | 1651.3 | 1264.5 | 743.8 |
| Session Retrieval | 1020 | 2170.5 | 2079.0 | 2978.9 | 3236.7 | 1271.0 | 892.3 |
| Full History | 1020 | 2402.6 | 2360.2 | 3054.9 | 14076.2 | 1279.6 | 1115.6 |

## All Conditions

| Condition | n | Mean latency ms | Median latency ms | P95 latency ms | Mean input tokens | Mean retrieval ms | Mean generation ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| All Structured | 1020 | 2270.9 | 2199.2 | 2897.7 | 7488.0 | 1269.7 | 994.2 |
| Fixed All Structured | 1020 | 2015.3 | 1975.5 | 2602.7 | 1651.3 | 1264.5 | 743.8 |
| Full History | 1020 | 2402.6 | 2360.2 | 3054.9 | 14076.2 | 1279.6 | 1115.6 |
| Context Only | 1020 | 665.0 | 546.4 | 1100.1 | 393.0 | 0.0 | 652.5 |
| Strategy Only | 1020 | 1938.7 | 1906.8 | 2539.9 | 648.8 | 1270.2 | 661.0 |
| Learned Selector | 1020 | 1952.5 | 1969.4 | 2627.2 | 1291.8 | 1214.1 | 723.2 |
| Session Retrieval | 1020 | 2170.5 | 2079.0 | 2978.9 | 3236.7 | 1271.0 | 892.3 |
| Rule Selector | 1020 | 3226.2 | 3274.7 | 4075.9 | 1624.0 | 2435.7 | 783.8 |

## Interpretation

- Learned Selector is slower than Context Only, as expected, because it invokes memory and strategy resources.
- Learned Selector has lower observed mean latency than Rule Selector, Session Retrieval, and Full History in this run.
- Policy inference overhead is small compared with retrieval and generation latency.
- Latency is not perfectly proportional to token count; retrieval path, provider scheduling, and response generation variance also matter.
- Use this as an operational diagnostic, not as confirmatory evidence of universal serving latency.
