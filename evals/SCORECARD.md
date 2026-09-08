# Landfall eval scorecard

_Generated 2026-09-08 - offline harness (`python evals/runner.py`)_

| Suite | Result | Gate |
|---|---|---|
| Golden text-to-SQL (E7.1) | 32/32 (100%) | >=95% -> PASS |
| Full-estimate scenarios (E7.2) | 8/8 | all pass -> PASS |
| **Overall** | **PASS** | |

## Golden SQL

| Case | Question | Result |
|---|---|---|
| Q01 | How many servers are in scope? | PASS |
| Q02 | How many servers are powered on? | PASS |
| Q03 | What is the total vCPU across all servers? | PASS |
| Q04 | What is the total RAM in GB? | PASS |
| Q05 | How many production servers are there? | PASS |
| Q06 | Break down server count by environment. | PASS |
| Q07 | How many Windows servers? | PASS |
| Q08 | How many Linux servers? | PASS |
| Q09 | How many servers are past OS end-of-support? | PASS |
| Q10 | How many servers have no p95 CPU reading? | PASS |
| Q11 | How many applications are there? | PASS |
| Q12 | Break down applications by criticality. | PASS |
| Q13 | How many internet-facing applications? | PASS |
| Q14 | How many applications are in PCI-DSS scope? | PASS |
| Q15 | How many distinct compliance scopes appear in the portfolio? | PASS |
| Q16 | What is the total provisioned disk in GB? | PASS |
| Q17 | What is the total used disk in GB? | PASS |
| Q18 | Break down storage volumes by type. | PASS |
| Q19 | What is the total file-share storage in GB? | PASS |
| Q20 | What is the total database-volume storage in GB? | PASS |
| Q21 | How many dependency rows are there? | PASS |
| Q22 | Break down dependency rows by confidence. | PASS |
| Q23 | How many high-confidence dependencies? | PASS |
| Q24 | Total observed outbound data over 30 days, in GB. | PASS |
| Q25 | How many performance sample rows are there? | PASS |
| Q26 | How many distinct servers have performance samples? | PASS |
| Q27 | What is the average p95 CPU for production servers? | PASS |
| Q28 | Which 3 applications have the most users? | PASS |
| Q29 | How many servers are not mapped to an application? | PASS |
| Q30 | Break down databases by engine. | PASS |
| Q31 | What is the single largest server by vCPU? | PASS |
| Q32 | Break down EOL-OS servers by environment. | PASS |

## Scenarios

| Scenario | Result | Checks |
|---|---|---|
| SC1 Full estate, house defaults | PASS | run_rate_monthly=113910.62, run_rate_annual=1366927.44, one_time_cost=73217.65, effort_pd=833.7, services_cost=650286, wave_count=7 |
| SC2 Production servers only | PASS | run_rate_monthly=87242.47, effort_pd=759.4, services_cost=592301 |
| SC3 3-year reserved instances at 100% coverage | PASS | run_rate_monthly=97751.63, run_rate_annual=1173019.56 |
| SC4 Dev/test pricing on non-production | PASS | run_rate_monthly=108181.85 |
| SC5 Aggressive disposition appetite | PASS | effort_pd=968.1, services_cost=755118 |
| SC6 Low data-quality confidence | PASS | effort_pd=893.2, run_rate_monthly=113910.62 |
| SC7 No Azure Hybrid Benefit | PASS | run_rate_monthly=132607.87, one_time_cost=87240.59 |
| SC8 Small 10-server slice | PASS | run_rate_monthly=19185.25, effort_pd=564.9, services_cost=440622 |
