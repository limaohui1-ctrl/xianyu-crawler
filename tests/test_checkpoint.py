"""
Tests for acs.storage.checkpoint — checkpoint save/resume.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
import shutil

from acs.storage.checkpoint import CheckpointManager, CheckpointState


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def checkpoint(temp_dir):
    return CheckpointManager(checkpoint_dir=temp_dir, run_id="test_run", save_interval=2)


class TestCheckpointState:

    def test_progress_pct(self):
        state = CheckpointState(urls_total=100, urls_processed=45)
        assert state.progress_pct == 45.0

    def test_can_resume(self):
        state = CheckpointState(
            status="running",
            pending_urls=["http://a.com", "http://b.com"],
        )
        assert state.can_resume

        state2 = CheckpointState(status="completed", pending_urls=["http://a.com"])
        assert not state2.can_resume

        state3 = CheckpointState(status="running", pending_urls=[])
        assert not state3.can_resume

    def test_to_from_dict(self):
        state = CheckpointState(
            run_id="test",
            status="running",
            urls_total=10,
            urls_processed=5,
            pending_urls=["http://a.com", "http://b.com"],
            error_summary={"http://x.com": "timeout"},
        )
        d = state.to_dict()
        restored = CheckpointState.from_dict(d)
        assert restored.run_id == "test"
        assert restored.urls_total == 10
        assert restored.pending_urls == ["http://a.com", "http://b.com"]


class TestCheckpointManager:

    def test_init_and_progress(self, checkpoint):
        urls = ["http://a.com", "http://b.com", "http://c.com", "http://d.com", "http://e.com"]
        checkpoint.init(urls, config={"template": "test"})

        # Process first 2
        checkpoint.record_progress("http://a.com")
        checkpoint.record_progress("http://b.com")

        state = checkpoint.get_state()
        assert state.urls_processed == 2
        assert state.urls_total == 5
        assert state.last_url == "http://b.com"

    def test_auto_save_at_interval(self, checkpoint):
        urls = ["http://a.com", "http://b.com", "http://c.com", "http://d.com"]
        checkpoint.init(urls)

        # Process 2 (interval is 2, so should auto-save)
        checkpoint.record_progress("http://a.com")
        checkpoint.record_progress("http://b.com")

        # Check file exists
        assert os.path.exists(checkpoint.checkpoint_file)

    def test_mark_completed(self, checkpoint):
        checkpoint.init(["http://a.com"])
        checkpoint.record_progress("http://a.com")
        checkpoint.mark_completed()

        state = checkpoint.load_latest()
        assert state.status == "completed"

    def test_mark_failed(self, checkpoint):
        checkpoint.init(["http://a.com"])
        checkpoint.mark_failed("Network error")

        state = checkpoint.load_latest()
        assert state.status == "failed"
        assert "_fatal" in state.error_summary

    def test_can_resume_checkpoint(self, checkpoint):
        urls = ["http://a.com", "http://b.com", "http://c.com"]
        checkpoint.init(urls)
        checkpoint.record_progress("http://a.com")
        checkpoint.save()

        # Create a new manager with the same dir/run_id
        mgr2 = CheckpointManager(
            checkpoint_dir=checkpoint.checkpoint_dir,
            run_id="test_run",
        )
        assert mgr2.can_resume()

        pending = mgr2.resume_pending_urls()
        assert pending is not None
        assert len(pending) == 3  # all 3 — progress saved but pending_urls still has originals

    def test_record_error(self, checkpoint):
        checkpoint.init(["http://a.com"])
        checkpoint.record_error("http://a.com", "Connection timeout")

        state = checkpoint.load_latest()
        assert "http://a.com" in state.error_summary
        assert len(state.failed_urls) == 1

    def test_delete(self, checkpoint):
        checkpoint.init(["http://a.com"])
        checkpoint.save()
        assert os.path.exists(checkpoint.checkpoint_file)

        checkpoint.delete()
        assert not os.path.exists(checkpoint.checkpoint_file)

    def test_list_checkpoints(self, checkpoint):
        checkpoint.init(["http://a.com"])
        checkpoint.save()

        checkpoints = CheckpointManager.list_checkpoints(checkpoint.checkpoint_dir)
        assert len(checkpoints) >= 1
        assert any(c["run_id"] == "test_run" for c in checkpoints)

    def test_force_save(self, checkpoint):
        checkpoint.init(["http://a.com"])
        checkpoint.record_progress("http://a.com")
        checkpoint.save()  # Force save

        state = checkpoint.load_latest()
        assert state is not None
        assert state.urls_processed == 1

    def test_get_progress(self, checkpoint):
        checkpoint.init(["http://a.com", "http://b.com"])
        progress = checkpoint.get_progress()
        assert progress["status"] == "running"
        assert progress["total"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
