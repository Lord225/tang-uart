`timescale 1ns / 1ps
`include "baud_generator.sv"
`include "button.sv"



module top (
    input  logic       clk,   // 27 MHz
    input  logic       btn1,
    input  logic       btn2,
    output logic [5:0] led
);

endmodule
