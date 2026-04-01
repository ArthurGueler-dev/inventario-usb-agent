# tests/test_local_db.py
import pytest
import tempfile
from pathlib import Path
from agent.local_db import LocalDB


@pytest.fixture
def db(tmp_path):
    return LocalDB(db_path=tmp_path / 'test_agent.db')


class TestConfig:
    def test_get_missing_key_returns_none(self, db):
        assert db.get_config('nonexistent') is None

    def test_set_and_get(self, db):
        db.set_config('foo', 'bar')
        assert db.get_config('foo') == 'bar'

    def test_overwrite(self, db):
        db.set_config('key', 'v1')
        db.set_config('key', 'v2')
        assert db.get_config('key') == 'v2'

    def test_server_url_property(self, db):
        assert db.server_url is None
        db.server_url = 'http://localhost:3000'
        assert db.server_url == 'http://localhost:3000'

    def test_token_property(self, db):
        db.token = 'mytoken'
        assert db.token == 'mytoken'

    def test_machine_id_property(self, db):
        db.machine_id = 'uuid-abc'
        assert db.machine_id == 'uuid-abc'

    def test_agent_version_default(self, db):
        assert db.agent_version == '1.0.0'

    def test_agent_version_property(self, db):
        db.agent_version = '1.2.3'
        assert db.agent_version == '1.2.3'


class TestEventQueue:
    def test_enqueue_and_pop(self, db):
        payload = {'event_type': 'connected', 'vid': '046D', 'pid': 'C52B'}
        db.enqueue_event(payload)
        batch = db.pop_pending_events()
        assert len(batch) == 1
        event_id, event_payload = batch[0]
        assert event_payload['event_type'] == 'connected'

    def test_pending_count(self, db):
        assert db.pending_count() == 0
        db.enqueue_event({'event_type': 'connected'})
        db.enqueue_event({'event_type': 'disconnected'})
        assert db.pending_count() == 2

    def test_mark_sent_reduces_pending(self, db):
        db.enqueue_event({'event_type': 'connected'})
        db.enqueue_event({'event_type': 'disconnected'})
        batch = db.pop_pending_events()
        ids = [eid for eid, _ in batch]
        db.mark_sent(ids)
        assert db.pending_count() == 0

    def test_mark_sent_empty_list(self, db):
        db.enqueue_event({'event_type': 'connected'})
        db.mark_sent([])
        assert db.pending_count() == 1

    def test_pop_respects_batch_size(self, db):
        for i in range(60):
            db.enqueue_event({'event_type': 'connected', 'i': i})
        batch = db.pop_pending_events()
        assert len(batch) == 50  # BATCH_SIZE

    def test_pop_returns_fifo_order(self, db):
        db.enqueue_event({'seq': 1})
        db.enqueue_event({'seq': 2})
        db.enqueue_event({'seq': 3})
        batch = db.pop_pending_events()
        seqs = [p['seq'] for _, p in batch]
        assert seqs == [1, 2, 3]

    def test_sent_events_not_returned_again(self, db):
        db.enqueue_event({'event_type': 'connected'})
        batch = db.pop_pending_events()
        db.mark_sent([eid for eid, _ in batch])
        assert db.pop_pending_events() == []

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / 'persist.db'
        db1 = LocalDB(db_path=path)
        db1.enqueue_event({'event_type': 'connected'})
        db1.token = 'tok123'

        db2 = LocalDB(db_path=path)
        assert db2.pending_count() == 1
        assert db2.token == 'tok123'
