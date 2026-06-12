
`timescale 1ns / 1ns

module counter #(
    parameter int unsigned COUNTER_MAX,
    parameter COUNTER_WIDTH = $clog2(COUNTER_MAX)
) (
    input logic clk,
    input logic reset,
    input logic enable,
    output logic tick,
    output logic tick_half_cycle,
    output logic [COUNTER_WIDTH-1:0] count
);

    logic [COUNTER_WIDTH-1:0] count_next;
    localparam logic [COUNTER_WIDTH-1:0] TERMINAL_COUNT = COUNTER_WIDTH'(COUNTER_MAX - 1);

    always_ff @(posedge clk) begin
        if (reset) begin
            count <= 0;
        end else if (enable) begin
            count <= count_next;
        end
    end

    always_comb begin
        tick = enable && (count == TERMINAL_COUNT);
        tick_half_cycle = enable && (count == (TERMINAL_COUNT >> 1));

        if (tick) begin
            count_next = '0;
        end else begin
            count_next = count + 1;
        end
    end
endmodule
