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
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "uart"
WAVES = os.getenv("WAVES", "0").lower() in {"1", "true", "yes", "on"}

BAUD = 9600
CLOCK_FREQ = 1_000_000
COUNTER_MAX = CLOCK_FREQ // BAUD
CLOCK_PERIOD_NS = 10


def _uart_frame_bits(byte: int) -> list[int]:
    data_bits = [(byte >> bit_index) & 1 for bit_index in range(8)]
    return [0, *data_bits, 1]


async def _loopback_tx_to_rx(dut: Any):
    while True:
        await Timer(1, unit="ns")
        dut.rx.value = int(dut.tx.value)
        await RisingEdge(dut.clk)


async def _start_clock_reset_and_loopback(dut: Any):
    dut.clk.value = 0
    dut.reset.value = 1
    dut.data_in.value = 0
    dut.data_in_valid.value = 0
    dut.rx.value = 1

    clock = Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))
    cocotb.start_soon(_loopback_tx_to_rx(dut))

    await Timer(1, unit="ns")
    assert int(dut.tx.value) == 1
    assert int(dut.data_out_valid.value) == 0

    for _ in range(2):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.tx.value) == 1
        assert int(dut.data_out_valid.value) == 0

    dut.reset.value = 0
    await Timer(1, unit="ns")


async def _wait_for_transmitter_baud_update(dut: Any) -> int:
    await Timer(1, unit="ns")

    while int(dut.transmitter.baud_clk.value) == 0:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    return int(dut.tx.value)


async def _request_byte_and_capture_frame(dut: Any, byte: int) -> list[int]:
    dut.data_in.value = byte
    dut.data_in_valid.value = 1

    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        dut.data_in_valid.value = 0
        if int(dut.tx.value) == 0:
            break
    else:
        assert False, "top-level transmitter did not emit a start bit"

    return [0, *[await _wait_for_transmitter_baud_update(dut) for _ in range(9)]]


async def _wait_for_received_byte(dut: Any, *, max_cycles: int = 80) -> int:
    for _ in range(max_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if int(dut.data_out_valid.value) == 1:
            return int(dut.data_out.value)

    assert False, f"receiver did not assert data_out_valid within {max_cycles} cycles"


@cocotb.test()
async def uart_loopback_transmits_and_receives_bytes(dut: Any):
    await _start_clock_reset_and_loopback(dut)

    for byte in b"Hello, UART!":
        observed_frame = await _request_byte_and_capture_frame(dut, byte)
        expected_frame = _uart_frame_bits(byte)
        assert observed_frame == expected_frame, (
            f"byte 0x{byte:02X}: expected tx frame {expected_frame}, "
            f"observed {observed_frame}"
        )

        observed_byte = await _wait_for_received_byte(dut)
        assert observed_byte == byte, (
            f"byte 0x{byte:02X}: loopback receiver emitted 0x{observed_byte:02X}"
        )

        await _wait_for_transmitter_baud_update(dut)
        assert int(dut.tx.value) == 1


@pytest.fixture(scope="module")
def uart_runner():
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
        hdl_toplevel="uart",
        build_dir=SIM_BUILD,
        always=True,
        waves=WAVES,
    )

    return runner


def test_uart_loopback_transmits_and_receives_bytes(uart_runner: Any):
    dump_vcd = SIM_BUILD / "dump.vcd"
    testcase_vcd = SIM_BUILD / "uart_loopback_transmits_and_receives_bytes.vcd"

    if WAVES:
        dump_vcd.unlink(missing_ok=True)
        testcase_vcd.unlink(missing_ok=True)

    try:
        uart_runner.test(
            hdl_toplevel="uart",
            test_module=__name__,
            build_dir=SIM_BUILD,
            testcase="uart_loopback_transmits_and_receives_bytes",
            waves=WAVES,
        )
    finally:
        if WAVES and dump_vcd.exists():
            dump_vcd.replace(testcase_vcd)
