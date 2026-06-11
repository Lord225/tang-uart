from __future__ import annotations

from pathlib import Path
import os
from typing import Any

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_tools.runner import get_runner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RTL_DIR = PROJECT_ROOT / "rtl"
SIM_BUILD = PROJECT_ROOT / "build" / "sim" / "baud_generator"
WAVES = os.getenv("WAVES", "0").lower() in {"1", "true", "yes", "on"}

BAUD = 3
CLOCK_FREQ = 12
COUNTER_MAX = CLOCK_FREQ // BAUD


async def _reset(dut: Any):
    dut.reset.value = 1
    await Timer(1, unit="ns")
    assert int(dut.tick.value) == 0

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.tick.value) == 0

    dut.reset.value = 0
    await Timer(1, unit="ns")


async def _sample_tick_after_clock(dut: Any) -> int:
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    return int(dut.tick.value)


@cocotb.test()
async def baud_generator_resets_and_generates_periodic_ticks(dut: Any):
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start(start_high=False))

    await _reset(dut)

    for cycle in range(1, (COUNTER_MAX * 3) + 1):
        expected_tick = int(cycle % COUNTER_MAX == COUNTER_MAX - 1)
        observed_tick = await _sample_tick_after_clock(dut)

        assert observed_tick == expected_tick, (
            f"cycle {cycle}: expected tick={expected_tick}, "
            f"observed tick={observed_tick}"
        )

    dut.reset.value = 1
    await Timer(1, unit="ns")
    assert int(dut.tick.value) == 0


def test_baud_generator_runner():
    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)

    runner.build(
        sources=[
            RTL_DIR / "baud_generator.sv",
        ],
        includes=[RTL_DIR],
        parameters={
            "BAUD": BAUD,
            "CLOCK_FREQ": CLOCK_FREQ,
        },
        hdl_toplevel="baud_generator",
        build_dir=SIM_BUILD,
        always=True,
        waves=WAVES,
    )

    runner.test(
        hdl_toplevel="baud_generator",
        test_module=__name__,
        build_dir=SIM_BUILD,
        waves=WAVES,
    )
