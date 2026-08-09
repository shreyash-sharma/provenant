from provenant.core.telemetry.adapters.ccusage import (
    _normalize_blocks,
    _normalize_daily,
    _normalize_sessions,
    _sum_rows,
)


def test_normalize_daily_instances_with_agent_breakdown():
    rows = _normalize_daily(
        {
            "projects": {
                "repo-a": [
                    {
                        "date": "20260809",
                        "inputTokens": 100,
                        "outputTokens": 20,
                        "cacheCreationTokens": 5,
                        "cacheReadTokens": 10,
                        "totalCost": 0.12,
                        "agents": [
                            {"agent": "codex", "inputTokens": 70, "outputTokens": 15},
                            {"agent": "claude", "inputTokens": 30, "outputTokens": 5},
                        ],
                    }
                ]
            }
        }
    )

    daily = [row for row in rows if row.report_type == "daily"]
    agents = [row for row in rows if row.report_type == "agent"]

    assert len(daily) == 1
    assert daily[0].project == "repo-a"
    assert daily[0].total_tokens == 135
    assert {row.agent for row in agents} == {"codex", "claude"}


def test_normalize_sessions_computes_total_tokens_when_missing():
    rows = _normalize_sessions(
        {
            "sessions": [
                {
                    "sessionId": "s1",
                    "project": "repo-a",
                    "agent": "codex",
                    "model": "gpt-test",
                    "inputTokens": 12,
                    "outputTokens": 3,
                    "cacheReadTokens": 4,
                }
            ]
        }
    )

    assert len(rows) == 1
    assert rows[0].session_id == "s1"
    assert rows[0].total_tokens == 19


def test_normalize_daily_handles_period_model_name_and_cost_field():
    rows = _normalize_daily(
        {
            "daily": [
                {
                    "period": "2026-01-02",
                    "inputTokens": 100,
                    "outputTokens": 50,
                    "totalTokens": 150,
                    "modelBreakdowns": [
                        {
                            "modelName": "gpt-5",
                            "inputTokens": 100,
                            "outputTokens": 50,
                            "totalTokens": 150,
                            "cost": 0.03,
                        }
                    ],
                }
            ]
        }
    )

    daily = [row for row in rows if row.report_type == "daily"]
    model = [row for row in rows if row.report_type == "model"]

    assert daily[0].date == "2026-01-02"
    assert model[0].model == "gpt-5"
    assert model[0].total_cost == 0.03


def test_normalize_blocks_handles_token_counts_shape():
    rows = _normalize_blocks(
        {
            "blocks": [
                {
                    "startTime": "2026-05-16T09:00:00.000Z",
                    "endTime": "2026-05-16T14:00:00.000Z",
                    "tokenCounts": {
                        "inputTokens": 10,
                        "outputTokens": 20,
                        "cacheCreationInputTokens": 3,
                        "cacheReadInputTokens": 4,
                    },
                    "costUSD": 0.05,
                }
            ]
        }
    )

    assert rows[0].first_activity == "2026-05-16T09:00:00.000Z"
    assert rows[0].last_activity == "2026-05-16T14:00:00.000Z"
    assert rows[0].total_tokens == 37
    assert rows[0].total_cost == 0.05


def test_sum_rows_prefers_daily_to_avoid_double_counting_sessions():
    daily_rows = _normalize_daily(
        {
            "daily": [
                {
                    "date": "2026-08-09",
                    "inputTokens": 100,
                    "outputTokens": 50,
                    "totalTokens": 150,
                    "totalCost": 0.2,
                }
            ]
        }
    )
    session_rows = _normalize_sessions(
        {
            "sessions": [
                {
                    "sessionId": "s1",
                    "inputTokens": 100,
                    "outputTokens": 50,
                    "totalTokens": 150,
                    "totalCost": 0.2,
                }
            ]
        }
    )

    totals = _sum_rows([*daily_rows, *session_rows])

    assert totals["total_tokens"] == 150
    assert totals["total_cost"] == 0.2
