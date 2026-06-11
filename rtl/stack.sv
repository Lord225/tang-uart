module stack #(
    parameter DEPTH = 256,
    parameter WIDTH = 8,
    parameter IDX_BITS = $clog2(DEPTH + 1)
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
    reg [WIDTH-1:0] memory[DEPTH];
    reg [IDX_BITS-1:0] idx;

    assign empty_o = (idx == 0);
    assign full_o  = (idx == (IDX_BITS)'($unsigned(DEPTH)));

    always @(negedge nrst_i, posedge clk_i) begin
        if (!nrst_i) begin
            idx <= 0;
            data_o <= 0;
        end else begin
            if (data_push_i && !data_pop_i) begin
                if (idx < $unsigned(DEPTH)) begin
                    memory[idx] <= data_i;
                    idx <= idx + 1;
                end
            end else if (!data_push_i && data_pop_i) begin
                if (idx > 0) begin
                    data_o <= memory[idx-1];
                    idx <= idx - 1;
                end
            end else if (data_push_i && data_pop_i) begin
                if (idx > 0) begin
                    data_o <= memory[idx-1];
                    memory[idx-1] <= data_i;
                end else begin
                    memory[idx] <= data_i;
                    if (idx < $unsigned(DEPTH - 1)) begin
                        idx <= idx + 1;
                    end
                end
            end
        end
    end
endmodule
