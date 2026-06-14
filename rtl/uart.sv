`ifndef UART_SV
`define UART_SV

`timescale 1ns / 1ns
`include "counter.sv"
`include "baud_generator.sv"
`include "button.sv"


typedef enum logic [2:0] {
    IDLE,
    START,
    DATA,
    STOP
} uart_state_t;


module uart_transmitter #(
    parameter int unsigned BAUD = 9600,
    parameter int unsigned CLOCK_FREQ = 27_000_000,
    parameter int unsigned COUNTER_MAX = CLOCK_FREQ / BAUD
) (
    input logic clk,
    input logic reset,
    input logic [7:0] data_in,
    input logic data_in_valid,
    output logic tx,
    output logic tx_done
);
    uart_state_t state;
    logic [2:0] bit_index;

    uart_state_t state_next;
    logic tx_next;
    logic [2:0] bit_index_next;
    logic baud_clk;
    logic reset_baud_clock;

    counter #(
        .COUNTER_MAX(COUNTER_MAX)
    ) counter_inst (
        .clk(clk),
        .reset(reset || reset_baud_clock),
        .enable(1'b1),
        .tick(baud_clk),
        .tick_half_cycle(),
        .count()
    );

    always_ff @(posedge clk, posedge reset) begin
        if (reset) begin
            state <= IDLE;
            tx <= 1'b1;
            bit_index <= 3'd0;
        end else begin
            state <= state_next;
            tx <= tx_next;
            bit_index <= bit_index_next;
        end
    end

    always_comb begin
        state_next = state;
        tx_next = tx;
        bit_index_next = bit_index;
        reset_baud_clock = 0;
        tx_done = 0;

        case (state)
            IDLE: begin
                if (data_in_valid) begin
                    state_next = START;
                    tx_next = 0;
                    reset_baud_clock = 1;
                end else begin
                    tx_next = 1;
                    bit_index_next = 0;
                end
            end

            START: begin
                if (baud_clk == 1) begin
                    state_next = DATA;
                    tx_next = data_in[0];
                    bit_index_next = 1;
                end
            end

            DATA: begin
                if (baud_clk == 1) begin
                    if (bit_index < 7) begin
                        state_next = DATA;
                        tx_next = data_in[bit_index];
                        bit_index_next = bit_index + 1;
                    end else begin
                        state_next = STOP;
                        tx_next = data_in[bit_index];
                        bit_index_next = 0;
                    end
                end
            end

            STOP: begin
                if (baud_clk == 1) begin
                    tx_done = 1;
                    if (data_in_valid) begin
                        state_next = START;
                        tx_next = 1;
                    end else begin
                        state_next = IDLE;
                        tx_next = 1;
                    end
                end
            end
            default: begin
                state_next = IDLE;
                tx_next = 1;
                bit_index_next = 0;
            end
        endcase
    end
endmodule

module uart_receiver #(
    parameter int unsigned BAUD = 9600,
    parameter int unsigned CLOCK_FREQ = 27_000_000,
    parameter int unsigned COUNTER_MAX = CLOCK_FREQ / BAUD
) (
    input logic clk,
    input logic reset,
    output logic [7:0] data_out,
    output logic data_out_valid,
    input logic rx
);
    uart_state_t state;
    logic [2:0] bit_index;

    uart_state_t state_next;
    logic [2:0] bit_index_next;

    logic [7:0] data_next;
    logic data_out_valid_next;

    logic start_bit_tick;
    logic baud_clk_half_cycle;
    counter #(
        .COUNTER_MAX(COUNTER_MAX)
    ) counter_inst (
        .clk(clk),
        .reset(reset || start_bit_tick),
        .enable(1'b1),
        .tick(),
        .tick_half_cycle(baud_clk_half_cycle),
        .count()
    );

    btn_edge start_bit_detector (
        .clk(clk),
        .btn(rx),
        .tick(start_bit_tick),
        .enable(state == IDLE)
    );

    always_ff @(posedge clk, posedge reset) begin
        if (reset) begin
            state <= IDLE;
            bit_index <= 3'd0;
            data_out <= 8'd0;
            data_out_valid <= 0;
        end else begin
            state <= state_next;
            bit_index <= bit_index_next;
            data_out <= data_next;
            data_out_valid <= data_out_valid_next;
        end
    end

    always_comb begin
        state_next = state;
        bit_index_next = bit_index;
        data_next = data_out;
        data_out_valid_next = 0;

        case (state)
            IDLE: begin
                if (start_bit_tick) begin
                    state_next = START;
                    data_next  = 8'd0;
                end else begin
                    bit_index_next = 0;
                    data_next = 8'd0;
                end
            end
            START: begin
                if (baud_clk_half_cycle == 1) begin
                    if (rx == 0) begin
                        state_next = DATA;
                    end else begin
                        state_next = IDLE;
                        data_next  = 8'd0;
                    end
                end
            end
            DATA: begin
                if (baud_clk_half_cycle == 1) begin
                    if (bit_index < 7) begin
                        bit_index_next = bit_index + 1;
                        data_next = {rx, data_out[7:1]};
                    end else begin
                        state_next = STOP;
                        bit_index_next = 0;
                        data_next = {rx, data_out[7:1]};
                    end
                end
            end
            STOP: begin
                if (baud_clk_half_cycle == 1) begin
                    state_next = IDLE;
                    data_out_valid_next = rx;
                end
            end
            default: begin
                state_next = IDLE;
                bit_index_next = 0;
                data_next = 8'd0;
            end
        endcase
    end
endmodule

module uart #(
    parameter int unsigned BAUD = 9600,
    parameter int unsigned CLOCK_FREQ,
    parameter int unsigned COUNTER_MAX = CLOCK_FREQ / BAUD
) (
    input logic clk,
    input logic reset,
    input logic [7:0] data_in,
    input logic data_in_valid,
    output logic [7:0] data_out,
    output logic data_out_valid,
    output logic tx_done,
    input logic rx,
    output logic tx
);
    uart_transmitter #(
        .BAUD(BAUD),
        .CLOCK_FREQ(CLOCK_FREQ),
        .COUNTER_MAX(COUNTER_MAX)
    ) transmitter (
        .clk(clk),
        .reset(reset),
        .data_in(data_in),
        .data_in_valid(data_in_valid),
        .tx(tx),
        .tx_done(tx_done)
    );

    uart_receiver #(
        .BAUD(BAUD),
        .CLOCK_FREQ(CLOCK_FREQ),
        .COUNTER_MAX(COUNTER_MAX)
    ) receiver (
        .clk(clk),
        .reset(reset),
        .data_out(data_out),
        .data_out_valid(data_out_valid),
        .rx(rx)
    );
endmodule

`endif
