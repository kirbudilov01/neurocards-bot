
import pytest
from unittest.mock import patch, MagicMock

@patch('app.db.create_client')
def test_atomic_job_claim(mock_create_client):
    from app.db import supabase

    # Mock the RPC call
    supabase.rpc = MagicMock()

    # First worker succeeds
    supabase.rpc.return_value.execute.return_value.data = [{'id': 'test_job_id'}]

    res1 = supabase.rpc("claim_next_job", {"p_worker_id": "worker-1"}).execute()
    job1 = res1.data[0] if res1.data else None

    assert job1 is not None
    assert job1['id'] == 'test_job_id'

    # Second worker fails (no jobs left)
    supabase.rpc.return_value.execute.return_value.data = []

    res2 = supabase.rpc("claim_next_job", {"p_worker_id": "worker-2"}).execute()
    job2 = res2.data[0] if res2.data else None

    assert job2 is None
