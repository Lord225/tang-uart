`timescale 1ns / 1ps
`include "uart.sv"
`include "queue.sv"

typedef enum logic [1:0] {
    RECIVING,
    FETCH_NEXT,
    START_TRANSMIT,
    TRANSMITTING
} state_t;

module top #(
    parameter int unsigned BAUD = 9600,
    parameter int unsigned CLOCK_FREQ = 27_000_000,
    parameter int unsigned QUEUE_CAPACITY = 256
) (
    input  logic       clk,
    input  logic       btn1,
    input  logic       btn2,
    output logic [5:0] led,
    output logic       uart_tx,
    input  logic       uart_rx
);
    logic         reset;
    logic         nrst;

    logic   [7:0] uart_data_out;
    logic         uart_data_out_valid;
    logic         uart_tx_done;
    logic         queue_empty;
    logic         queue_full;
    state_t       state;

    logic   [7:0] uart_data_in;
    logic         data_pop;
    logic         uart_data_in_valid;

    state_t       state_next;

    logic         btn1_tick;
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

    queue #(
        .CAPACITY(QUEUE_CAPACITY),
        .WIDTH   (8)
    ) queue (
        .clk_i      (clk),
        .nrst_i     (nrst),
        .data_i     (uart_data_out),
        .data_enqueue_i(uart_data_out_valid),
        .data_o     (uart_data_in),
        .data_dequeue_i(data_pop),
        .empty_o    (queue_empty),
        .full_o     (queue_full)
    );

    uart #(
        .BAUD(BAUD),
        .CLOCK_FREQ(CLOCK_FREQ)
    ) uart (
        .clk(clk),
        .reset(reset),
        .data_in(uart_data_in),
        .data_in_valid(uart_data_in_valid),
        .tx(uart_tx),
        .rx(uart_rx),
        .data_out(uart_data_out),
        .tx_done(uart_tx_done),
        .data_out_valid(uart_data_out_valid)
    );

    always_ff @(posedge clk) begin
        if (btn2_tick) begin
            reset <= 1;
            nrst  <= 0;
            state <= RECIVING;
        end else begin
            reset <= 0;
            nrst  <= 1;
            state <= state_next;
        end
    end

    always_comb begin
        state_next = state;
        data_pop = 1'b0;
        uart_data_in_valid = 1'b0;

        case (state)
            RECIVING: begin
                if (btn1_tick && !queue_empty) begin
                    state_next = FETCH_NEXT;
                end
            end
            FETCH_NEXT: begin
                data_pop = 1'b1;
                state_next = START_TRANSMIT;
            end
            START_TRANSMIT: begin
                uart_data_in_valid = 1'b1;
                state_next = TRANSMITTING;
            end
            TRANSMITTING: begin
                if (uart_tx_done) begin
                    state_next = RECIVING;
                end
            end
            default: begin
                state_next = RECIVING;
            end
        endcase
    end

    always_comb begin
        led = '0;
        led[0] = btn1_tick;
        led[1] = btn2_tick;
    end

endmodule
