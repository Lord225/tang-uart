from __future__ import annotations

from pathlib import Path
import os
import shutil
from typing import Any

import cocotb
import pytest
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_tools.runner import get_runner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "top"
WAVES = os.getenv("WAVES", "0").lower() in {"1", "true", "yes", "on"}

BAUD = 3
CLOCK_FREQ = 12
COUNTER_MAX = CLOCK_FREQ // BAUD
CLOCK_PERIOD_NS = 10
QUEUE_CAPACITY = 4

Dut = Any
Runner = Any


def _uart_data_bits(byte: int) -> list[int]:
    return [(byte >> bit_index) & 1 for bit_index in range(8)]


def _uart_frame_bits(byte: int) -> list[int]:
    return [0, *_uart_data_bits(byte), 1]


async def _clock(dut: Dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def _wait_cycles(dut: Dut, cycles: int) -> None:
    for _ in range(cycles):
        await _clock(dut)


async def _click_button(dut: Dut, button_name: str) -> None:
    button = getattr(dut, button_name)

    button.value = 1
    await _wait_cycles(dut, 3)
    button.value = 0
    await _wait_cycles(dut, 3)
    button.value = 1
    await _wait_cycles(dut, 2)


async def _start_clock_and_reset(dut: Dut) -> None:
    dut.clk.value = 0
    dut.btn1.value = 1
    dut.btn2.value = 1
    dut.uart_rx.value = 1

    clock = Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    await _wait_cycles(dut, 3)
    await _click_button(dut, "btn2")
    await _wait_cycles(dut, 3)

    assert int(dut.uart_tx.value) == 1
    assert int(dut.queue_empty.value) == 1


async def _drive_rx_for_cycles(dut: Dut, value: int, cycles: int) -> list[int]:
    observed: list[int] = []
    dut.uart_rx.value = value
    for _ in range(cycles):
        await _clock(dut)
        if int(dut.uart_data_out_valid.value) == 1:
            observed.append(int(dut.uart_data_out.value))
    return observed


async def _send_uart_frame_to_top(dut: Dut, byte: int) -> list[int]:
    observed: list[int] = []
    observed += await _drive_rx_for_cycles(dut, 1, COUNTER_MAX)
    observed += await _drive_rx_for_cycles(dut, 0, COUNTER_MAX)

    for bit in _uart_data_bits(byte):
        observed += await _drive_rx_for_cycles(dut, bit, COUNTER_MAX)

    observed += await _drive_rx_for_cycles(dut, 1, COUNTER_MAX)
    observed += await _drive_rx_for_cycles(dut, 1, COUNTER_MAX * 2)
    return observed


async def _wait_for_queue_nonempty(dut: Dut, *, max_cycles: int = 80) -> None:
    for _ in range(max_cycles):
        if int(dut.queue_empty.value) == 0:
            return
        await _clock(dut)

    assert False, f"queue did not become non-empty within {max_cycles} cycles"


async def _wait_for_tx_start(dut: Dut, *, max_cycles: int = 80) -> None:
    for _ in range(max_cycles):
        if int(dut.uart_tx.value) == 0:
            return
        await _clock(dut)

    assert False, f"UART TX start bit not observed within {max_cycles} cycles"


async def _sample_after_transmitter_baud_update(dut: Dut) -> int:
    await Timer(1, unit="ns")

    while int(dut.uart.transmitter.baud_clk.value) == 0:
        await _clock(dut)

    await _clock(dut)
    return int(dut.uart_tx.value)


async def _capture_top_tx_frame(dut: Dut) -> list[int]:
    await _wait_for_tx_start(dut)
    return [0, *[await _sample_after_transmitter_baud_update(dut) for _ in range(9)]]


def _decode_uart_frame(frame: list[int]) -> int:
    assert frame[0] == 0
    assert frame[-1] == 1
    return sum(bit << index for index, bit in enumerate(frame[1:9]))


@cocotb.test()
async def top_reset_holds_tx_idle_and_queue_empty(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    for _ in range(COUNTER_MAX * 4):
        await _clock(dut)
        assert int(dut.uart_tx.value) == 1
        assert int(dut.queue_empty.value) == 1


@cocotb.test()
async def top_button_does_not_transmit_when_queue_empty(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    await _click_button(dut, "btn1")

    for _ in range(COUNTER_MAX * 4):
        await _clock(dut)
        assert int(dut.uart_tx.value) == 1


@cocotb.test()
async def top_receives_byte_and_transmits_it_after_button_click(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    byte = 0x55
    received = await _send_uart_frame_to_top(dut, byte)
    assert received == [byte]
    await _wait_for_queue_nonempty(dut)

    await _click_button(dut, "btn1")
    observed_frame = await _capture_top_tx_frame(dut)

    assert observed_frame == _uart_frame_bits(byte)
    assert _decode_uart_frame(observed_frame) == byte


@cocotb.test()
async def top_receives_multiple_bytes_before_any_click_and_reprints_fifo(
    dut: Dut,
) -> None:
    await _start_clock_and_reset(dut)

    bytes_in = [0x11, 0xA5, 0x3C, 0xF0]
    received: list[int] = []
    for byte in bytes_in:
        received += await _send_uart_frame_to_top(dut, byte)
        await _wait_for_queue_nonempty(dut)

    assert received == bytes_in

    observed: list[int] = []
    for byte in bytes_in:
        await _click_button(dut, "btn1")
        observed_frame = await _capture_top_tx_frame(dut)
        assert observed_frame == _uart_frame_bits(byte)
        observed.append(_decode_uart_frame(observed_frame))

        await _sample_after_transmitter_baud_update(dut)
        assert int(dut.uart_tx.value) == 1

    assert observed == bytes_in
    assert int(dut.queue_empty.value) == 1


@cocotb.test()
async def top_clicks_do_not_duplicate_or_skip_queued_bytes(dut: Dut) -> None:
    await _start_clock_and_reset(dut)

    bytes_in = [0x00, 0xFF, 0x5A]
    for byte in bytes_in:
        assert await _send_uart_frame_to_top(dut, byte) == [byte]

    observed: list[int] = []
    for _ in bytes_in:
        await _click_button(dut, "btn1")
        observed.append(_decode_uart_frame(await _capture_top_tx_frame(dut)))
        await _sample_after_transmitter_baud_update(dut)

    await _click_button(dut, "btn1")
    for _ in range(COUNTER_MAX * 4):
        await _clock(dut)
        assert int(dut.uart_tx.value) == 1

    assert observed == bytes_in


@pytest.fixture(scope="module")
def top_runner() -> Runner:
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)

    shutil.rmtree(SIM_BUILD, ignore_errors=True)

    runner.build(
        sources=[RTL_DIR / "top.sv"],
        includes=[RTL_DIR],
        parameters={
            "BAUD": BAUD,
            "CLOCK_FREQ": CLOCK_FREQ,
            "QUEUE_CAPACITY": QUEUE_CAPACITY,
        },
        build_args=["-Wno-MODDUP", "-Wno-WIDTHTRUNC"],
        hdl_toplevel="top",
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
            hdl_toplevel="top",
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


def test_top_reset_holds_tx_idle_and_queue_empty(top_runner: Runner) -> None:
    _run_cocotb_test(top_runner, "top_reset_holds_tx_idle_and_queue_empty")


def test_top_button_does_not_transmit_when_queue_empty(top_runner: Runner) -> None:
    _run_cocotb_test(top_runner, "top_button_does_not_transmit_when_queue_empty")


def test_top_receives_byte_and_transmits_it_after_button_click(
    top_runner: Runner,
) -> None:
    _run_cocotb_test(
        top_runner,
        "top_receives_byte_and_transmits_it_after_button_click",
    )


def test_top_receives_multiple_bytes_before_any_click_and_reprints_fifo(
    top_runner: Runner,
) -> None:
    _run_cocotb_test(
        top_runner,
        "top_receives_multiple_bytes_before_any_click_and_reprints_fifo",
    )


def test_top_clicks_do_not_duplicate_or_skip_queued_bytes(top_runner: Runner) -> None:
    _run_cocotb_test(
        top_runner,
        "top_clicks_do_not_duplicate_or_skip_queued_bytes",
    )
