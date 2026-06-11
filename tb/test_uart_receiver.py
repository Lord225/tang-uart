from __future__ import annotations

from pathlib import Path
import os
from typing import Any

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_tools.runner import get_runner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "uart_receiver"
WAVES = os.getenv("WAVES", "0").lower() in {"1", "true", "yes", "on"}

BAUD = 3
CLOCK_FREQ = 12
COUNTER_MAX = CLOCK_FREQ // BAUD
CLOCK_PERIOD_NS = 10


def _uart_data_bits(byte: int) -> list[int]:
    return [(byte >> bit_index) & 1 for bit_index in range(8)]


def _valid_values(samples: list[dict[str, int]]) -> list[int]:
    return [sample["data_out"] for sample in samples if sample["data_out_valid"] == 1]


async def _start_clock_and_reset(dut: Any, *, idle_rx: int = 1):
    dut.clk.value = 0
    dut.reset.value = 1
    dut.rx.value = idle_rx

    clock = Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    await Timer(1, unit="ns")
    assert int(dut.data_out_valid.value) == 0

    for _ in range(2):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.data_out_valid.value) == 0

    dut.reset.value = 0
    await Timer(1, unit="ns")


async def _clock_and_sample(dut: Any, samples: list[dict[str, int]] | None = None):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    sample = {
        "rx": int(dut.rx.value),
        "data_out": int(dut.data_out.value),
        "data_out_valid": int(dut.data_out_valid.value),
    }

    if samples is not None:
        samples.append(sample)

    return sample


async def _drive_rx_for_cycles(
    dut: Any,
    value: int,
    cycles: int,
    samples: list[dict[str, int]],
):
    dut.rx.value = value

    for _ in range(cycles):
        await _clock_and_sample(dut, samples)


async def _send_uart_frame(
    dut: Any,
    byte: int,
    samples: list[dict[str, int]],
    *,
    stop_bit: int = 1,
    pre_idle_bits: int = 1,
    post_idle_bits: int = 2,
):
    await _drive_rx_for_cycles(dut, 1, pre_idle_bits * COUNTER_MAX, samples)
    await _drive_rx_for_cycles(dut, 0, COUNTER_MAX, samples)

    for bit in _uart_data_bits(byte):
        await _drive_rx_for_cycles(dut, bit, COUNTER_MAX, samples)

    await _drive_rx_for_cycles(dut, stop_bit, COUNTER_MAX, samples)
    await _drive_rx_for_cycles(dut, 1, post_idle_bits * COUNTER_MAX, samples)


@cocotb.test()
async def uart_receiver_reset_and_idle_line_do_not_emit_valid(dut: Any):
    await _start_clock_and_reset(dut)

    samples: list[dict[str, int]] = []
    await _drive_rx_for_cycles(dut, 1, COUNTER_MAX * 6, samples)

    assert _valid_values(samples) == []


@cocotb.test()
async def uart_receiver_decodes_single_lsb_first_frame(dut: Any):
    await _start_clock_and_reset(dut)

    byte = 0x96
    samples: list[dict[str, int]] = []
    await _send_uart_frame(dut, byte, samples)

    observed = _valid_values(samples)
    assert observed == [byte], (
        f"expected one valid pulse for 0x{byte:02X}, "
        f"observed valid data values {observed}"
    )


@cocotb.test()
async def uart_receiver_decodes_multiple_frames_with_back_to_back_timing(dut: Any):
    await _start_clock_and_reset(dut)

    first_byte = 0x53
    second_byte = 0xAC
    samples: list[dict[str, int]] = []

    await _send_uart_frame(
        dut,
        first_byte,
        samples,
        pre_idle_bits=1,
        post_idle_bits=0,
    )
    await _send_uart_frame(
        dut,
        second_byte,
        samples,
        pre_idle_bits=0,
        post_idle_bits=2,
    )

    observed = _valid_values(samples)
    assert observed == [first_byte, second_byte], (
        f"expected back-to-back bytes {[first_byte, second_byte]}, observed {observed}"
    )


@cocotb.test()
async def uart_receiver_rejects_short_start_glitch(dut: Any):
    await _start_clock_and_reset(dut)

    samples: list[dict[str, int]] = []
    await _drive_rx_for_cycles(dut, 1, COUNTER_MAX, samples)
    await _drive_rx_for_cycles(dut, 0, max(1, COUNTER_MAX // 2), samples)
    await _drive_rx_for_cycles(dut, 1, COUNTER_MAX * 12, samples)

    assert _valid_values(samples) == []


@cocotb.test()
async def uart_receiver_start_detector_uses_falling_edge(dut: Any):
    await _start_clock_and_reset(dut)

    dut.rx.value = 0
    await _clock_and_sample(dut)
    falling_edge_tick = int(dut.start_bit_tick.value)

    dut.rx.value = 1
    await _clock_and_sample(dut)
    rising_edge_tick = int(dut.start_bit_tick.value)

    assert (falling_edge_tick, rising_edge_tick) == (1, 0), (
        "UART start detection should pulse on the idle-high to low transition "
        f"only, observed falling={falling_edge_tick}, rising={rising_edge_tick}"
    )


@cocotb.test()
async def uart_receiver_requires_high_stop_bit_before_valid(dut: Any):
    await _start_clock_and_reset(dut)

    byte = 0xA3
    samples: list[dict[str, int]] = []
    await _send_uart_frame(dut, byte, samples, stop_bit=0)

    observed = _valid_values(samples)
    assert observed == [], (
        "data_out_valid must wait for and require a high stop bit, "
        f"observed valid data values {observed}"
    )


@pytest.fixture(scope="module")
def uart_receiver_runner():
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)

    runner.build(
        sources=[
            RTL_DIR / "uart.sv",
        ],
        includes=[RTL_DIR],
        parameters={
            "BAUD": BAUD,
            "CLOCK_FREQ": CLOCK_FREQ,
            "COUNTER_MAX": COUNTER_MAX,
        },
        build_args=["-Wno-MODDUP"],
        hdl_toplevel="uart_receiver",
        build_dir=SIM_BUILD,
        always=True,
        waves=WAVES,
    )

    return runner


def _run_cocotb_test(runner: Any, testcase: str):
    dump_vcd = SIM_BUILD / "dump.vcd"
    testcase_vcd = SIM_BUILD / f"{testcase}.vcd"

    if WAVES:
        dump_vcd.unlink(missing_ok=True)
        testcase_vcd.unlink(missing_ok=True)

    try:
        runner.test(
            hdl_toplevel="uart_receiver",
            test_module=__name__,
            build_dir=SIM_BUILD,
            testcase=testcase,
            waves=WAVES,
        )
    finally:
        if WAVES and dump_vcd.exists():
            dump_vcd.replace(testcase_vcd)


def test_uart_receiver_reset_and_idle_line_do_not_emit_valid(
    uart_receiver_runner: Any,
):
    _run_cocotb_test(
        uart_receiver_runner,
        "uart_receiver_reset_and_idle_line_do_not_emit_valid",
    )


def test_uart_receiver_decodes_single_lsb_first_frame(uart_receiver_runner: Any):
    _run_cocotb_test(
        uart_receiver_runner,
        "uart_receiver_decodes_single_lsb_first_frame",
    )


def test_uart_receiver_decodes_multiple_frames_with_back_to_back_timing(
    uart_receiver_runner: Any,
):
    _run_cocotb_test(
        uart_receiver_runner,
        "uart_receiver_decodes_multiple_frames_with_back_to_back_timing",
    )


def test_uart_receiver_rejects_short_start_glitch(uart_receiver_runner: Any):
    _run_cocotb_test(
        uart_receiver_runner,
        "uart_receiver_rejects_short_start_glitch",
    )


def test_uart_receiver_start_detector_uses_falling_edge(uart_receiver_runner: Any):
    _run_cocotb_test(
        uart_receiver_runner,
        "uart_receiver_start_detector_uses_falling_edge",
    )


def test_uart_receiver_requires_high_stop_bit_before_valid(
    uart_receiver_runner: Any,
):
    _run_cocotb_test(
        uart_receiver_runner,
        "uart_receiver_requires_high_stop_bit_before_valid",
    )
