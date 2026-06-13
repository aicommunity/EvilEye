import pytest

from evileye.core.gpu_errors import (
    CudaOutOfMemoryError,
    MP_EXIT_CUDA_OOM,
    format_cuda_oom_message,
    is_cuda_oom_error,
)


@pytest.mark.unit
def test_is_cuda_oom_error_detects_runtime_error_message():
    exc = RuntimeError(
        "CUDA error: out of memory\nCUDA kernel errors might be asynchronously reported"
    )
    assert is_cuda_oom_error(exc) is True


@pytest.mark.unit
def test_is_cuda_oom_error_follows_cause_chain():
    root = RuntimeError("CUDA error: out of memory")
    wrapped = RuntimeError("predict failed")
    wrapped.__cause__ = root
    assert is_cuda_oom_error(wrapped) is True


@pytest.mark.unit
def test_is_cuda_oom_error_rejects_unrelated_errors():
    assert is_cuda_oom_error(ValueError("queue full")) is False


@pytest.mark.unit
def test_cuda_oom_error_is_runtime_error():
    err = CudaOutOfMemoryError("boom")
    assert isinstance(err, RuntimeError)
    assert is_cuda_oom_error(err) is False


@pytest.mark.unit
def test_format_cuda_oom_message_includes_component():
    text = format_cuda_oom_message(component="det-mp-1-worker", detail="load failed")
    assert "det-mp-1-worker" in text
    assert "load failed" in text


@pytest.mark.unit
def test_mp_exit_cuda_oom_is_nonzero():
    assert MP_EXIT_CUDA_OOM not in (0, -15)
