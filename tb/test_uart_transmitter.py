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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "uart_transmitter"
WAVES = os.getenv("WAVES", "0").lower() in {"1", "true", "yes", "on"}
BAUD = 3
CLOCK_FREQ = 12
COUNTER_MAX = CLOCK_FREQ // BAUD
CLOCK_PERIOD_NS = 10


def _uart_data_bits(byte: int) -> list[int]:
    return [(byte >> bit_index) & 1 for bit_index in range(8)]


async def _start_clock_and_reset(dut: Any):
    dut.clk.value = 0
    dut.reset.value = 1
    dut.data_in.value = 0
    dut.data_in_valid.value = 0

    clock = Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    await Timer(1, unit="ns")
    assert int(dut.tx.value) == 1

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.tx.value) == 1

    dut.reset.value = 0
    await Timer(1, unit="ns")


async def _wait_clock_cycles(dut: Any, cycles: int):
    for _ in range(cycles):
        await RisingEdge(dut.clk)


async def _sample_after_baud_update(dut: Any) -> int:
    await Timer(1, unit="ns")

    while int(dut.baud_clk.value) == 0:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    return int(dut.tx.value)


async def _request_byte_and_wait_for_start_bit(
    dut: Any,
    byte: int,
    *,
    max_latency_cycles: int = 3,
) -> int:
    dut.data_in.value = byte
    dut.data_in_valid.value = 1

    for latency in range(max_latency_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if latency == 0:
            dut.data_in_valid.value = 0

        if int(dut.tx.value) == 0:
            return latency

    dut.data_in_valid.value = 0
    assert False, (
        f"start bit was not observed within {max_latency_cycles} baud ticks "
        "after data_in_valid"
    )


async def _capture_remaining_frame_bits(dut: Any) -> list[int]:
    return [await _sample_after_baud_update(dut) for _ in range(9)]


@cocotb.test()
async def uart_transmitter_holds_tx_high_while_idle(dut: Any):
    await _start_clock_and_reset(dut)

    for cycle in range(8):
        tx = await _sample_after_baud_update(dut)
        assert tx == 1, f"idle cycle {cycle}: expected tx to stay high"


@cocotb.test()
async def uart_transmitter_sends_start_lsb_first_data_and_stop(dut: Any):
    await _start_clock_and_reset(dut)

    byte = 0x96
    start_latency = await _request_byte_and_wait_for_start_bit(dut, byte)
    frame = [0, *await _capture_remaining_frame_bits(dut)]

    expected_frame = [0, *_uart_data_bits(byte), 1]
    assert frame == expected_frame, (
        f"start latency={start_latency} baud ticks, "
        f"expected frame {expected_frame}, observed {frame}"
    )


@cocotb.test()
async def uart_transmitter_sends_full_frame_after_one_cycle_valid_pulse(dut: Any):
    await _start_clock_and_reset(dut)

    for byte in [0x00, 0xFF, 0x53, 0xAC]:
        await _request_byte_and_wait_for_start_bit(dut, byte)
        frame: list[int] = [0, *await _capture_remaining_frame_bits(dut)]

        expected_frame = [0, *_uart_data_bits(byte), 1]
        assert frame == expected_frame, (
            f"byte 0x{byte:02X}: expected frame {expected_frame}, observed {frame}"
        )

        await _sample_after_baud_update(dut)
        assert int(dut.tx.value) == 1


@cocotb.test()
async def uart_transmitter_returns_to_idle_after_one_pulsed_request(dut: Any):
    await _start_clock_and_reset(dut)

    byte = 0x3C
    await _request_byte_and_wait_for_start_bit(dut, byte)
    frame = [0, *await _capture_remaining_frame_bits(dut)]

    assert frame == [0, *_uart_data_bits(byte), 1]

    for cycle in range(4):
        tx = await _sample_after_baud_update(dut)
        assert tx == 1, f"post-frame idle cycle {cycle}: expected tx to stay high"


@cocotb.test()
async def uart_transmitter_starts_next_byte_after_returning_to_idle(dut: Any):
    await _start_clock_and_reset(dut)

    first_byte = 0xA6
    second_byte = 0x59
    await _request_byte_and_wait_for_start_bit(dut, first_byte)

    first_data_bits = [await _sample_after_baud_update(dut) for _ in range(8)]
    assert first_data_bits == _uart_data_bits(first_byte)

    stop_bit = await _sample_after_baud_update(dut)
    assert stop_bit == 1

    start_latency = await _request_byte_and_wait_for_start_bit(dut, second_byte)
    next_frame = [0, *await _capture_remaining_frame_bits(dut)]

    expected_frame = [0, *_uart_data_bits(second_byte), 1]
    assert next_frame == expected_frame, (
        f"start latency={start_latency} clk cycles, "
        f"expected next frame {expected_frame}, observed {next_frame}"
    )


@cocotb.test()
async def uart_transmitter_reset_aborts_active_frame(dut: Any):
    await _start_clock_and_reset(dut)

    await _request_byte_and_wait_for_start_bit(dut, 0xA5)
    for _ in range(3):
        await _sample_after_baud_update(dut)

    dut.reset.value = 1
    await Timer(1, unit="ns")
    assert int(dut.tx.value) == 1

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.tx.value) == 1

    dut.reset.value = 0
    await Timer(1, unit="ns")

    byte = 0x81
    await _request_byte_and_wait_for_start_bit(dut, byte)
    frame = [0, *await _capture_remaining_frame_bits(dut)]

    assert frame == [0, *_uart_data_bits(byte), 1]


@pytest.fixture(scope="module")
def uart_transmitter_runner():
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
        hdl_toplevel="uart_transmitter",
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
            hdl_toplevel="uart_transmitter",
            test_module=__name__,
            build_dir=SIM_BUILD,
            testcase=testcase,
            waves=WAVES,
        )
    finally:
        if WAVES and dump_vcd.exists():
            dump_vcd.replace(testcase_vcd)


def test_uart_transmitter_holds_tx_high_while_idle(uart_transmitter_runner: Any):
    _run_cocotb_test(
        uart_transmitter_runner,
        "uart_transmitter_holds_tx_high_while_idle",
    )


def test_uart_transmitter_sends_start_lsb_first_data_and_stop(
    uart_transmitter_runner: Any,
):
    _run_cocotb_test(
        uart_transmitter_runner,
        "uart_transmitter_sends_start_lsb_first_data_and_stop",
    )


def test_uart_transmitter_sends_full_frame_after_one_cycle_valid_pulse(
    uart_transmitter_runner: Any,
):
    _run_cocotb_test(
        uart_transmitter_runner,
        "uart_transmitter_sends_full_frame_after_one_cycle_valid_pulse",
    )


def test_uart_transmitter_returns_to_idle_after_one_pulsed_request(
    uart_transmitter_runner: Any,
):
    _run_cocotb_test(
        uart_transmitter_runner,
        "uart_transmitter_returns_to_idle_after_one_pulsed_request",
    )


def test_uart_transmitter_starts_next_byte_after_returning_to_idle(
    uart_transmitter_runner: Any,
):
    _run_cocotb_test(
        uart_transmitter_runner,
        "uart_transmitter_starts_next_byte_after_returning_to_idle",
    )


def test_uart_transmitter_reset_aborts_active_frame(uart_transmitter_runner: Any):
    _run_cocotb_test(
        uart_transmitter_runner,
        "uart_transmitter_reset_aborts_active_frame",
    )
