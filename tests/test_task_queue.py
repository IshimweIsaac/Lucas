from __future__ import annotations

from agent.task_queue import TaskQueue, TaskPriority, TaskStatus

def test_task_submit_and_status():
    q = TaskQueue(max_concurrent=1)
    
    # We won't call start() so we can inspect it without it running
    task_id = q.submit("Test goal", priority=TaskPriority.NORMAL)
    
    assert q.pending_count() == 1
    
    status = q.get_status(task_id)
    assert status is not None
    assert status["task_id"] == task_id
    assert status["goal"] == "Test goal"
    assert status["status"] == TaskStatus.PENDING.value

def test_task_priority_ordering():
    q = TaskQueue(max_concurrent=1)
    
    id_low = q.submit("Low", priority=TaskPriority.LOW)
    id_high = q.submit("High", priority=TaskPriority.HIGH)
    id_normal = q.submit("Normal", priority=TaskPriority.NORMAL)
    
    # Check internal queue order
    assert len(q._queue) == 3
    # HIGHEST priority first (lowest number)
    assert q._queue[0].task_id == id_high
    assert q._queue[1].task_id == id_normal
    assert q._queue[2].task_id == id_low

def test_task_cancel():
    q = TaskQueue(max_concurrent=1)
    task_id = q.submit("Test cancel", priority=TaskPriority.NORMAL)
    
    # Cancel it
    success = q.cancel(task_id)
    assert success is True
    
    status = q.get_status(task_id)
    assert status["status"] == TaskStatus.CANCELLED.value
