import pytest

from provenant.core.persistence import create_engine, create_session_factory, init_db
from provenant.core.telemetry.events import record_tool_call
from provenant.core.telemetry.usage import _correlate_savings


def test_correlate_savings_marks_sessions_with_provenant_events() -> None:
    rows = [
        {
            "report_type": "session",
            "session_id": "assisted",
            "first_activity": "2026-08-09T10:00:00+00:00",
            "last_activity": "2026-08-09T10:30:00+00:00",
            "total_tokens": 1000,
            "total_cost": 1.0,
        },
        {
            "report_type": "session",
            "session_id": "unassisted",
            "first_activity": "2026-08-09T12:00:00+00:00",
            "last_activity": "2026-08-09T12:30:00+00:00",
            "total_tokens": 2000,
            "total_cost": 2.0,
        },
    ]
    events = [
        {
            "tool_name": "provenant_context",
            "started_at": "2026-08-09T10:10:00+00:00",
            "success": True,
            "estimated_context_tokens": 120,
        }
    ]

    savings = _correlate_savings(rows, events)

    assert savings["assisted"]["sessions"] == 1
    assert savings["unassisted"]["sessions"] == 1
    assert savings["observed_delta"]["avg_token_reduction_pct"] == 50.0
    assert savings["observed_delta"]["avg_cost_reduction_pct"] == 50.0


def test_correlate_savings_excludes_sessions_without_timestamps() -> None:
    savings = _correlate_savings(
        [{"report_type": "session", "session_id": "missing", "total_tokens": 1000}],
        [{"tool_name": "provenant_context", "started_at": "2026-08-09T10:10:00+00:00"}],
    )

    assert savings["uncorrelated_sessions"] == 1
    assert savings["assisted"]["sessions"] == 0


@pytest.mark.asyncio
async def test_record_tool_call_persists_event() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:", use_static_pool=True)
    await init_db(engine)
    session_factory = create_session_factory(engine)

    try:
        result = await record_tool_call(
            session_factory,
            repository_id=None,
            tool_name="provenant_context",
            query_text="src/app.py",
            target_count=1,
            call=lambda: _return_response(),
        )
        assert result["targets"]["src/app.py"]["target"] == "src/app.py"

        from sqlalchemy import select

        from provenant.core.persistence.database import get_session
        from provenant.core.persistence.models import ProvenantUsageEvent

        async with get_session(session_factory) as session:
            event = (await session.execute(select(ProvenantUsageEvent))).scalar_one()
            assert event.tool_name == "provenant_context"
            assert event.target_count == 1
            assert event.returned_target_count == 1
            assert event.estimated_context_tokens > 0
            assert event.success is True
            assert event.started_at is not None
    finally:
        await engine.dispose()


async def _return_response() -> dict:
    return {
        "targets": {
            "src/app.py": {
                "target": "src/app.py",
                "docs": {"summary": "Example"},
            }
        }
    }
