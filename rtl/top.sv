`timescale 1ns / 1ps
`include "uart.sv"

module top (
    input  logic       clk,
    input  logic       btn1,
    input  logic       btn2,
    output logic [5:0] led,
    output logic       uart_tx,
    input  logic       uart_rx
);
    logic btn1_tick;
    btn_edge btn1_edge (
        .clk(clk),
        .btn(btn1),
        .enable(1'b1),
        .tick(btn1_tick)
    );

    logic btn2_tick;
    btn_edge btn2_edge (
        .clk(clk),
        .btn(btn2),
        .enable(1'b1),
        .tick(btn2_tick)
    );

    logic [7:0] data_out;
    logic       data_out_valid;
    logic       tx_done;
    logic       reset;
    uart #(
        .BAUD(9600),
        .CLOCK_FREQ(27_000_000)
    ) uart (
        .clk(clk),
        .reset(reset),
        .data_in(8'h55),
        .data_in_valid(btn2_tick),
        .tx(uart_tx),
        .rx(uart_rx),
        .data_out(data_out),
        .tx_done(tx_done),
        .data_out_valid(data_out_valid)
    );

    always_ff @(posedge clk) begin
        if (btn1_tick) begin
            reset <= 1;
        end else begin
            reset <= 0;
        end
    end

    always_comb begin
        led = '0;
        led[0] = btn1_tick;
    end

endmodule
