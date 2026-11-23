`timescale 1ns/1ps

// Raw preview uses one camera at a time. Each camera keeps its full raster.
module vid007_raw_arbiter (
    input wire clk, rst_n, enable,
    input wire [3:0] valid, sof, done, good,
    input wire [127:0] pixels,
    input wire full,
    input wire [2:0] mode,
    output wire push,
    output wire [34:0] word_out
);
    reg [1:0] channel;
    reg active, trailer, failed, trailer_good;
    reg [19:0] words_seen;
    reg [21:0] cooldown, idle_age;
    // Leave at least one sensor-frame interval for DMA to drain.
    localparam [21:0] FRAME_GAP = 22'd2500000;
    localparam [21:0] WAIT_LIMIT = 22'd3000000;
    wire take = enable && !trailer && cooldown == 0 && valid[channel] && (active || sof[channel]);
    assign push = !full && (take || trailer);
    assign word_out = trailer ? {channel, 1'b1, 24'b0, (trailer_good ? {5'b10100, mode} : 8'b0)} :
                                {channel, 1'b0, pixels[32*channel+:32]};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            channel <= 0;
            active <= 0;
            trailer <= 0;
            failed <= 0;
            trailer_good <= 0;
            words_seen <= 0;
            cooldown <= 0;
            idle_age <= 0;
        end else begin
            if (cooldown != 0)
                cooldown <= cooldown - 1'b1;
            if (trailer && !full) begin
                trailer <= 0;
                channel <= channel + 1'b1;
                cooldown <= FRAME_GAP;
            end
            if (take || trailer || cooldown != 0)
                idle_age <= 0;
            else if (enable) begin
                if (idle_age == WAIT_LIMIT) begin
                    idle_age <= 0;
                    if (active) begin
                        active <= 0;
                        trailer <= 1;
                        trailer_good <= 0;
                    end else channel <= channel + 1'b1;
                end else idle_age <= idle_age + 1'b1;
            end
            if (take && sof[channel] && !active) begin
                active <= 1;
                words_seen <= 1;
                failed <= full;
            end else if (take) begin
                words_seen <= words_seen + 1'b1;
                if (full || sof[channel]) failed <= 1;
            end
            if (enable && active && done[channel]) begin
                active <= 0;
                trailer <= 1;
                trailer_good <= good[channel] && !failed && words_seen == 20'd518400;
            end
        end
    end
endmodule

// Synchronous-read Gray-pointer FIFO. Data sits in FPGA block RAM.
// The read pointer advances into a registered head, which holds on backpressure.
module vid007_raw_cdc #(
    parameter AW = 15
)(
    input wire wr_clk, wr_rst_n, wr_en,
    input wire [34:0] wr_data,
    output wire full,
    input wire rd_clk, rd_rst_n, rd_ready,
    output reg [34:0] rd_data,
    output reg rd_valid
);
    reg [34:0] ram [0:(1<<AW)-1];
    reg [AW:0] wp, wg, rp, rg;
    (* async_reg = "true" *) reg [AW:0] rg1, rg2, wg1, wg2;
    wire [AW:0] wp_next = wp + 1'b1;
    wire [AW:0] rp_next = rp + 1'b1;
    wire advance = !rd_valid || rd_ready;
    wire read_word = advance && rg != wg2;
    assign full = wg == {~rg2[AW:AW-1], rg2[AW-2:0]};

    always @(posedge wr_clk)
        if (wr_en && !full) ram[wp[AW-1:0]] <= wr_data;

    always @(posedge rd_clk)
        if (read_word) rd_data <= ram[rp[AW-1:0]];

    always @(posedge wr_clk or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            wp <= 0;
            wg <= 0;
            rg1 <= 0;
            rg2 <= 0;
        end else begin
            rg1 <= rg;
            rg2 <= rg1;
            if (wr_en && !full) begin
                wp <= wp_next;
                wg <= wp_next ^ (wp_next >> 1);
            end
        end
    end

    always @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            rp <= 0;
            rg <= 0;
            wg1 <= 0;
            wg2 <= 0;
            rd_valid <= 0;
        end else begin
            wg1 <= wg;
            wg2 <= wg1;
            if (advance) rd_valid <= read_word;
            if (read_word) begin
                rp <= rp_next;
                rg <= rp_next ^ (rp_next >> 1);
            end
        end
    end
endmodule

// A 4080-byte staging page preserves the DMA driver's one-page CHNK limit.
// Capture accepts a 32-bit word per clock; transmission supplies 128-bit beats.
module vid007_raw_chunks (
    input wire clk, rst_n, valid,
    input wire [34:0] word_in,
    output wire ready,
    output reg [127:0] m_tdata,
    output reg [15:0] m_tkeep,
    output wire [15:0] m_tuser,
    output reg m_tvalid, m_tlast,
    input wire m_tready
);
    localparam COLLECT = 2'd0, HEADER = 2'd1, BODY = 2'd2, END_BEAT = 2'd3;
    reg [1:0] state;
    reg [127:0] page [0:254];
    reg [95:0] partial;
    reg [9:0] count, length;
    reg [7:0] beat;
    reg [1:0] channel;
    reg eof;
    reg [15:0] seq;
    reg [31:0] frame;
    wire last_word = word_in[32];
    wire [9:0] next_count = count + 1'b1;
    wire ending = last_word || next_count == 1020;
    wire [127:0] store_data = count[1:0] == 0 ? {96'b0, word_in[31:0]} :
                              count[1:0] == 1 ? {64'b0, word_in[31:0], partial[31:0]} :
                              count[1:0] == 2 ? {32'b0, word_in[31:0], partial[63:0]} :
                                              {word_in[31:0], partial};
    wire transfer = !m_tvalid || m_tready;
    wire last_beat = (beat == ((length - 1'b1) >> 2));
    assign ready = state == COLLECT;
    assign m_tuser = m_tkeep;

    always @(posedge clk) begin
        if (valid && ready) begin
            case (count[1:0])
                0: partial[31:0] <= word_in[31:0];
                1: partial[63:32] <= word_in[31:0];
                2: partial[95:64] <= word_in[31:0];
                default: begin end
            endcase
            if (count[1:0] == 3 || ending)
                page[count[9:2]] <= store_data;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= COLLECT;
            count <= 0;
            length <= 0;
            beat <= 0;
            channel <= 0;
            eof <= 0;
            seq <= 0;
            frame <= 0;
            m_tvalid <= 0;
            m_tlast <= 0;
            m_tkeep <= 0;
            m_tdata <= 0;
        end else begin
            if (transfer) m_tvalid <= 0;
            case (state)
                COLLECT: if (valid) begin
                    count <= next_count;
                    if (ending) begin
                        length <= next_count;
                        eof <= last_word;
                        channel <= word_in[34:33];
                        state <= HEADER;
                    end
                end
                HEADER: if (transfer) begin
                    m_tdata <= {frame, 20'b0, length, 2'b0, seq,
                                6'b0, eof, (seq == 0), 6'b0, channel, 32'h4b4e4843};
                    m_tkeep <= 16'hffff;
                    m_tlast <= 0;
                    m_tvalid <= 1;
                    beat <= 0;
                    state <= BODY;
                end
                BODY: if (transfer) begin
                    m_tdata <= page[beat];
                    m_tkeep <= !last_beat || length[1:0] == 0 ? 16'hffff :
                               length[1:0] == 1 ? 16'h000f :
                               length[1:0] == 2 ? 16'h00ff : 16'h0fff;
                    m_tlast <= last_beat;
                    m_tvalid <= 1;
                    beat <= beat + 1'b1;
                    if (last_beat) state <= END_BEAT;
                end
                END_BEAT: if (transfer) begin
                    count <= 0;
                    if (eof) begin
                        frame <= frame + 1'b1;
                        seq <= 0;
                    end else seq <= seq + 1'b1;
                    state <= COLLECT;
                end
            endcase
        end
    end
endmodule
