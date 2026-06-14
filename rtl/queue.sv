`ifndef QUEUE_SV
`define QUEUE_SV

module queue_mem #(
    parameter CAPACITY = 256,
    parameter WIDTH = 8,
    parameter IDX_BITS = $clog2(CAPACITY + 1)
) (
    input clk_i,

    input  [WIDTH-1:0] data_i,
    output [WIDTH-1:0] data_o,

    input read_i,
    write_i,

    input [IDX_BITS-1:0] read_addr,
    input [IDX_BITS-1:0] write_addr
);

    reg [WIDTH-1:0] memory  [CAPACITY-1:0];

    reg [WIDTH-1:0] out_buf;

    assign data_o = out_buf;

    always @(posedge clk_i) begin
        if (write_i) begin
            memory[write_addr] <= data_i;
        end
        if (read_i) begin
            out_buf <= memory[read_addr];
        end
    end

endmodule



module queue #(
    parameter CAPACITY = 256,
    parameter WIDTH = 8,
    parameter IDX_BITS = $clog2(CAPACITY + 1)
) (
    input clk_i,
    input nrst_i,

    input [WIDTH-1:0] data_i,
    input data_enqueue_i,

    output reg [WIDTH-1:0] data_o,
    input data_dequeue_i,

    output wire empty_o,
    output wire full_o
);

    localparam [IDX_BITS-1:0] CAP_TRUNC = CAPACITY[IDX_BITS-1:0];

    reg [IDX_BITS-1:0] start_idx, start_idx_comb;
    reg [IDX_BITS-1:0] len, len_comb;
    wire [IDX_BITS-1:0] end_idx_comb;

    reg [IDX_BITS-1:0] read_addr_comb, write_addr_comb;

    reg mem_read_comb, mem_write_comb;

    wire [WIDTH-1:0] mem_out_comb;

    queue_mem #(
        .CAPACITY(CAPACITY)
    ) memory (
        .clk_i     (clk_i),
        .data_i    (data_i),
        .data_o    (mem_out_comb),
        .read_i    (mem_read_comb),
        .write_i   (mem_write_comb),
        .read_addr (read_addr_comb),
        .write_addr(write_addr_comb)
    );

    function [IDX_BITS-1:0] truncate(input [IDX_BITS:0] value);
        begin
            truncate = value[IDX_BITS-1:0];
        end
    endfunction

    function [IDX_BITS-1:0] wrapping_add(input [IDX_BITS-1:0] a, b);
        begin
            if ({1'b0, a} + {1'b0, b} >= {1'b0, CAP_TRUNC}) begin
                wrapping_add = truncate({1'b0, a} + {1'b0, b} - {1'b0, CAP_TRUNC});
            end else begin
                wrapping_add = a + b;
            end
        end
    endfunction

    assign end_idx_comb = wrapping_add(start_idx, len);

    assign empty_o = (len == 0);
    assign full_o = (len >= CAP_TRUNC);

    always @* begin
        start_idx_comb = start_idx;
        len_comb = len;

        read_addr_comb = start_idx;
        write_addr_comb = end_idx_comb;

        mem_read_comb = 0;
        mem_write_comb = 0;

        if (data_enqueue_i && !data_dequeue_i) begin
            if (!full_o) begin
                len_comb = len + 1;
                mem_write_comb = 1;
            end
        end else if (!data_enqueue_i && data_dequeue_i) begin
            if (!empty_o) begin
                start_idx_comb = wrapping_add(start_idx, 1);
                len_comb = len - 1;
                mem_read_comb = 1;
            end
        end else if (data_enqueue_i && data_dequeue_i) begin
            if (empty_o) begin
                len_comb = len + 1;
                mem_write_comb = 1;
            end else begin
                mem_read_comb  = 1;
                mem_write_comb = 1;
                start_idx_comb = wrapping_add(start_idx, 1);
            end
        end

        data_o = mem_out_comb;
    end

    always @(negedge nrst_i, posedge clk_i) begin
        if (!nrst_i) begin
            start_idx <= 0;
            len       <= 0;
        end else begin
            start_idx <= start_idx_comb;
            len       <= len_comb;
        end
    end

endmodule

`endif
