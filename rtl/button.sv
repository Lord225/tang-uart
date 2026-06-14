`ifndef BUTTON_SV
`define BUTTON_SV

`timescale 1ns / 1ns

module btn_edge (
    input  logic clk,
    input  logic btn,
    input  logic enable,
    output logic tick
);
    logic btn_prev;
    logic btn_curr;

    always_ff @(posedge clk) begin
        btn_curr <= btn;
        btn_prev <= btn_curr;
    end

    always_comb begin
        if (enable) begin
            if ({btn_prev, btn_curr} == 2'b10) begin
                tick = 1;
            end else begin
                tick = 0;
            end
        end else begin
            tick = 0;
        end
    end
endmodule

`endif
