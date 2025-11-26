import pytest
from lead_generation_app.metrics import get_metrics, inc_success, inc_skip_cap, inc_skip_inactive, inc_trial_used


@pytest.mark.unit
def test_metrics_counters():
    client_id = 999
    inc_success(client_id, 'email', 'restaurants')
    inc_skip_cap(client_id, 'email', 'restaurants')
    inc_skip_inactive(client_id, 'email', 'restaurants')
    inc_trial_used(client_id, 'email', 'restaurants')
    data = get_metrics()
    b = data[client_id]['email']['restaurants']
    assert b['delivered'] == 1
    assert b['skipped_cap'] == 1
    assert b['skipped_inactive'] == 1
    assert b['trial_used'] == 1
