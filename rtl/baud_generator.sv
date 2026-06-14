`ifndef BAUD_GENERATOR_SV
`define BAUD_GENERATOR_SV

`timescale 1ns / 1ns
`include "counter.sv"


module baud_generator #(
    parameter int unsigned BAUD = 9600,
    parameter int unsigned CLOCK_FREQ = 27_000_000,
    parameter int unsigned COUNTER_MAX = CLOCK_FREQ / BAUD,
    parameter COUNTER_WIDTH = $clog2(COUNTER_MAX)
) (
    input  logic clk,
    input  logic reset,
    output logic tick
);
    (*maybe_unused*)
    logic [COUNTER_WIDTH-1:0] count;

    counter #(
        .COUNTER_MAX  (COUNTER_MAX),
        .COUNTER_WIDTH(COUNTER_WIDTH)
    ) counter_inst (
        .clk(clk),
        .reset(reset),
        .enable(1'b1),
        .tick(tick),
        .tick_half_cycle(),
        .count(count)
    );
endmodule

`endif
