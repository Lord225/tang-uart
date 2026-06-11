module queue #(
    parameter CAPACITY = 256,
    parameter WIDTH = 8,
    parameter IDX_BITS = $clog2(CAPACITY + 1)
) (
    input clk_i,
    input nrst_i,

    input [WIDTH-1:0] data_i,
    input data_push_i,

    output reg [WIDTH-1:0] data_o,
    input data_pop_i,

    output wire empty_o,
    output wire full_o
);

    localparam [IDX_BITS-1:0] CAP_TRUNC = CAPACITY[IDX_BITS-1:0];

    reg [WIDTH-1:0] memory[CAPACITY];

    reg [IDX_BITS-1:0] start_idx;
    reg [IDX_BITS-1:0] len;
    wire [IDX_BITS-1:0] end_idx;

    function [IDX_BITS-1:0] wrapping_add(input [IDX_BITS-1:0] a, b);
        begin
            if ({1'b0, a} + {1'b0, b} >= {1'b0, CAP_TRUNC}) begin
                wrapping_add = IDX_BITS'({1'b0, a} + {1'b0, b} - {1'b0, CAP_TRUNC});
            end else begin
                wrapping_add = a + b;
            end
        end
    endfunction

    assign end_idx = wrapping_add(start_idx, len);

    assign empty_o = (len == 0);
    assign full_o  = (len == CAP_TRUNC);

    always @(negedge nrst_i, posedge clk_i) begin
        if (!nrst_i) begin
            start_idx <= 0;
            len       <= 0;
            data_o    <= 0;
        end else begin
            if (data_push_i && !data_pop_i) begin
                if (len < CAP_TRUNC) begin
                    memory[end_idx] <= data_i;
                    len             <= len + 1;
                end
            end else if (!data_push_i && data_pop_i) begin
                if (len > 0) begin
                    data_o    <= memory[start_idx];
                    start_idx <= wrapping_add(start_idx, 1);
                    len       <= len - 1;
                end
            end else if (data_push_i && data_pop_i) begin
                if (len > 0) begin
                    memory[end_idx] <= data_i;
                    data_o          <= memory[start_idx];
                    start_idx       <= wrapping_add(start_idx, 1);
                end else begin
                    memory[end_idx] <= data_i;
                    len             <= len + 1;
                end
            end
        end
    end
endmodule
