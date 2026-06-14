from __future__ import annotations

from collections import deque
from pathlib import Path
import os
import shutil
from typing import Any, Deque, Literal, NamedTuple

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_tools.runner import get_runner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "queue"
WAVES = os.getenv("WAVES", "0").lower() in {"1", "true", "yes", "on"}
CLOCK_PERIOD_NS = 10
CAPACITY = 4
WIDTH = 8

Dut = Any
Runner = Any
Operation = Literal["push", "pop", "push_pop", "idle"]


class QueueStep(NamedTuple):
    operation: Operation
    value: int = 0


async def _start_clock_and_reset(dut: Dut) -> None:
    dut.clk_i.value = 0
    dut.nrst_i.value = 0
    dut.data_i.value = 0
    dut.data_enqueue_i.value = 0
    dut.data_dequeue_i.value = 0

    clock = Clock(dut.clk_i, CLOCK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    await Timer(1, unit="ns")
    assert int(dut.empty_o.value) == 1
    assert int(dut.full_o.value) == 0
    assert int(dut.data_o.value) == 0

    await RisingEdge(dut.clk_i)
    await Timer(1, unit="ns")

    dut.nrst_i.value = 1
    await Timer(1, unit="ns")


async def _clock(dut: Dut) -> None:
    await RisingEdge(dut.clk_i)
    await Timer(1, unit="ns")


async def _push(dut: Dut, value: int) -> None:
    dut.data_i.value = value
    dut.data_enqueue_i.value = 1
    dut.data_dequeue_i.value = 0
    await _clock(dut)
    dut.data_enqueue_i.value = 0
    await Timer(1, unit="ns")


async def _pop(dut: Dut) -> int:
    dut.data_enqueue_i.value = 0
    dut.data_dequeue_i.value = 1
    await _clock(dut)
    value = int(dut.data_o.value)
    dut.data_dequeue_i.value = 0
    await Timer(1, unit="ns")
    return value


async def _push_pop(dut: Dut, value: int) -> int:
    dut.data_i.value = value
    dut.data_enqueue_i.value = 1
    dut.data_dequeue_i.value = 1
    await _clock(dut)
    observed = int(dut.data_o.value)
    dut.data_enqueue_i.value = 0
    dut.data_dequeue_i.value = 0
    await Timer(1, unit="ns")
    return observed


async def _drive_step(dut: Dut, step: QueueStep) -> int:
    dut.data_i.value = step.value
    dut.data_enqueue_i.value = step.operation in {"push", "push_pop"}
    dut.data_dequeue_i.value = step.operation in {"pop", "push_pop"}

    await _clock(dut)
    observed = int(dut.data_o.value)

    dut.data_enqueue_i.value = 0
    dut.data_dequeue_i.value = 0
    await Timer(1, unit="ns")

    return observed


def _apply_model_step(model: Deque[int], step: QueueStep) -> int | None:
    if step.operation == "idle":
        return None

    if step.operation == "push":
        if len(model) < CAPACITY:
            model.append(step.value)
        return None

    if step.operation == "pop":
        if model:
            return model.popleft()
        return None

    if model:
        observed = model.popleft()
        model.append(step.value)
        return observed

    model.append(step.value)
    return None


@cocotb.test()
async def queue_reset_starts_empty_and_clears_output(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    await _push(dut, 0xA5)
    assert int(dut.empty_o.value) == 0

    dut.nrst_i.value = 0
    await Timer(1, unit="ns")
    assert int(dut.empty_o.value) == 1
    assert int(dut.full_o.value) == 0
    assert int(dut.data_o.value) == 0


@cocotb.test()
async def queue_preserves_fifo_order_across_wraparound(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    for value in [0x10, 0x20, 0x30]:
        await _push(dut, value)

    assert await _pop(dut) == 0x10
    assert await _pop(dut) == 0x20

    for value in [0x40, 0x50, 0x60]:
        await _push(dut, value)

    assert int(dut.full_o.value) == 1

    observed = [await _pop(dut) for _ in range(CAPACITY)]
    assert observed == [0x30, 0x40, 0x50, 0x60]
    assert int(dut.empty_o.value) == 1
    assert int(dut.full_o.value) == 0


@cocotb.test()
async def queue_drops_push_when_full_without_corrupting_contents(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    expected = [0x01, 0x02, 0x03, 0x04]
    for value in expected:
        await _push(dut, value)

    assert int(dut.full_o.value) == 1

    await _push(dut, 0xEE)
    assert int(dut.full_o.value) == 1

    observed = [await _pop(dut) for _ in range(CAPACITY)]
    assert observed == expected
    assert int(dut.empty_o.value) == 1


@cocotb.test()
async def queue_pop_when_empty_does_not_change_output_or_flags(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    await _pop(dut)
    assert int(dut.empty_o.value) == 1
    assert int(dut.full_o.value) == 0

    await _push(dut, 0x5A)
    assert await _pop(dut) == 0x5A
    assert int(dut.empty_o.value) == 1


@cocotb.test()
async def queue_simultaneous_push_pop_outputs_oldest_and_keeps_length(
    dut: Dut,
) -> None:
    await _start_clock_and_reset(dut)

    await _push(dut, 0x11)
    await _push(dut, 0x22)

    assert await _push_pop(dut, 0x33) == 0x11
    assert int(dut.empty_o.value) == 0
    assert int(dut.full_o.value) == 0

    assert await _pop(dut) == 0x22
    assert await _pop(dut) == 0x33
    assert int(dut.empty_o.value) == 1


@cocotb.test()
async def queue_simultaneous_push_pop_when_empty_stores_new_value(
    dut: Dut,
) -> None:
    await _start_clock_and_reset(dut)

    await _push_pop(dut, 0xC3)
    assert int(dut.empty_o.value) == 0
    assert await _pop(dut) == 0xC3
    assert int(dut.empty_o.value) == 1


@cocotb.test()
async def queue_matches_reference_model_for_mixed_operations(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    steps = [
        QueueStep("idle"),
        QueueStep("pop"),
        QueueStep("push", 0x10),
        QueueStep("push", 0x20),
        QueueStep("push_pop", 0x30),
        QueueStep("push", 0x40),
        QueueStep("push", 0x50),
        QueueStep("push", 0x60),
        QueueStep("push", 0xEE),
        QueueStep("push_pop", 0x70),
        QueueStep("pop"),
        QueueStep("pop"),
        QueueStep("push_pop", 0x80),
        QueueStep("pop"),
        QueueStep("pop"),
        QueueStep("pop"),
        QueueStep("pop"),
        QueueStep("push_pop", 0x90),
        QueueStep("pop"),
    ]
    model: Deque[int] = deque()

    for index, step in enumerate(steps):
        expected_output = _apply_model_step(model, step)
        observed_output = await _drive_step(dut, step)

        if expected_output is not None:
            assert observed_output == expected_output, (
                f"step {index} {step}: expected output 0x{expected_output:02X}, "
                f"observed 0x{observed_output:02X}"
            )
        assert int(dut.empty_o.value) == int(len(model) == 0), (
            f"step {index} {step}: empty flag mismatch for model={list(model)}"
        )
        assert int(dut.full_o.value) == int(len(model) == CAPACITY), (
            f"step {index} {step}: full flag mismatch for model={list(model)}"
        )


@pytest.fixture(scope="module")
def queue_runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)

    shutil.rmtree(SIM_BUILD, ignore_errors=True)

    runner.build(
        sources=[RTL_DIR / "queue.sv"],
        includes=[RTL_DIR],
        parameters={
            "CAPACITY": CAPACITY,
            "WIDTH": WIDTH,
        },
        build_args=["-Wno-UNUSEDSIGNAL", "-Wno-WIDTHTRUNC"],
        hdl_toplevel="queue",
        build_dir=SIM_BUILD,
        always=True,
        waves=WAVES,
    )

    return runner


def _run_cocotb_test(runner: Runner, testcase: str) -> None:
    dump_vcd = SIM_BUILD / "dump.vcd"
    testcase_vcd = SIM_BUILD / f"{testcase}.vcd"
    exit_code: object = 0

    if WAVES:
        dump_vcd.unlink(missing_ok=True)
        testcase_vcd.unlink(missing_ok=True)

    try:
        runner.test(
            hdl_toplevel="queue",
            test_module=__name__,
            build_dir=SIM_BUILD,
            test_filter=testcase,
            waves=WAVES,
        )
    except SystemExit as exc:
        exit_code = exc.code
    finally:
        if WAVES and dump_vcd.exists():
            dump_vcd.replace(testcase_vcd)

    if exit_code:
        pytest.fail(
            f"cocotb test {testcase!r} failed; see captured log above",
            pytrace=False,
        )


def test_queue_reset_starts_empty_and_clears_output(queue_runner: Runner) -> None:
    _run_cocotb_test(queue_runner, "queue_reset_starts_empty_and_clears_output")


def test_queue_preserves_fifo_order_across_wraparound(queue_runner: Runner) -> None:
    _run_cocotb_test(queue_runner, "queue_preserves_fifo_order_across_wraparound")


def test_queue_drops_push_when_full_without_corrupting_contents(
    queue_runner: Runner,
) -> None:
    _run_cocotb_test(
        queue_runner,
        "queue_drops_push_when_full_without_corrupting_contents",
    )


def test_queue_pop_when_empty_does_not_change_output_or_flags(
    queue_runner: Runner,
) -> None:
    _run_cocotb_test(
        queue_runner,
        "queue_pop_when_empty_does_not_change_output_or_flags",
    )


def test_queue_simultaneous_push_pop_outputs_oldest_and_keeps_length(
    queue_runner: Runner,
) -> None:
    _run_cocotb_test(
        queue_runner,
        "queue_simultaneous_push_pop_outputs_oldest_and_keeps_length",
    )


def test_queue_simultaneous_push_pop_when_empty_stores_new_value(
    queue_runner: Runner,
) -> None:
    _run_cocotb_test(
        queue_runner,
        "queue_simultaneous_push_pop_when_empty_stores_new_value",
    )


def test_queue_matches_reference_model_for_mixed_operations(
    queue_runner: Runner,
) -> None:
    _run_cocotb_test(
        queue_runner,
        "queue_matches_reference_model_for_mixed_operations",
    )
