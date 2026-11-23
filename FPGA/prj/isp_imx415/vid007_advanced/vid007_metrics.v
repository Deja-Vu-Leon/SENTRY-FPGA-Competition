`timescale 1ns/1ps

// A counter changes by one per source event. Synchronize its registered Gray
// representation, then decode it in the PCIe clock domain.
module vid007_event_count (
    input wire source_clk, source_reset_n, event_pulse,
    input wire user_clk, user_reset_n,
    output reg [31:0] count
);
    reg [31:0] binary, gray;
    wire [31:0] incremented = binary + 1'b1;
    (* async_reg = "true" *) reg [31:0] gray_meta, gray_sync;
    reg [31:0] decoded;
    integer bit_index;
    always @* begin
        decoded[31] = gray_sync[31];
        for (bit_index = 30; bit_index >= 0; bit_index = bit_index - 1)
            decoded[bit_index] = decoded[bit_index+1] ^ gray_sync[bit_index];
    end

    always @(posedge source_clk or negedge source_reset_n) begin
        if (!source_reset_n) begin
            binary <= 0;
            gray <= 0;
        end else if (event_pulse) begin
            binary <= incremented;
            gray <= incremented ^ (incremented >> 1);
        end
    end
    always @(posedge user_clk or negedge user_reset_n) begin
        if (!user_reset_n) begin
            gray_meta <= 0;
            gray_sync <= 0;
            count <= 0;
        end else begin
            gray_meta <= gray;
            gray_sync <= gray_meta;
            count <= decoded;
        end
    end
endmodule
