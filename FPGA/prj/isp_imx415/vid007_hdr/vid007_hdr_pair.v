`timescale 1ns/1ps

// Pair two independent CSI-2 exposure streams after RAW10 unpacking and crop.
// Each FIFO entry carries position tags from its receiver. Frame starts must
// carry the same physical sensor frame sequence for fusion to be possible.
module vid007_hdr_pair #(
    parameter AW=10
)(
    input wire clk,reset_n,
    input wire long_valid,long_sof,long_eol,
    input wire [15:0] long_frame,
    input wire [39:0] long_pixels,
    input wire short_valid,short_sof,short_eol,
    input wire [15:0] short_frame,
    input wire [39:0] short_pixels,
    input wire [2:0] exposure_shift,
    output wire valid,sof,eol,
    output wire [39:0] pixels,
    output reg [31:0] lost_pairs
);
    reg [21:0] long_index,short_index;
    reg [15:0] long_id,short_id;
    wire [21:0] long_offset=long_sof?22'd0:long_index;
    wire [21:0] short_offset=short_sof?22'd0:short_index;
    wire [15:0] long_sequence=long_sof?long_frame:long_id;
    wire [15:0] short_sequence=short_sof?short_frame:short_id;

    wire [79:0] a,b;
    wire have_a,have_b;
    wire [15:0] delta=a[79:64]-b[79:64];
    wire same_position=delta==0 && a[63:42]==b[63:42];
    wire long_before=delta==0 ? a[63:42]<b[63:42] : delta[15];
    wire [1:0] tags_a=a[41:40], tags_b=b[41:40];
    wire matching=have_a && have_b && same_position && tags_a==tags_b;
    wire pop_a=have_a && have_b && (same_position || long_before);
    wire pop_b=have_a && have_b && (same_position || !long_before);
    wire overflow_a,overflow_b;
    vid007_hdr_fifo #(.DW(80),.AW(AW)) long_fifo (
        .clk(clk),.reset_n(reset_n),.clear(1'b0),.push(long_valid),.input_word({long_sequence,long_offset,long_sof,long_eol,long_pixels}),
        .pop(pop_a),.head(a),.have_head(have_a),.overflow(overflow_a)
    );
    vid007_hdr_fifo #(.DW(80),.AW(AW)) short_fifo (
        .clk(clk),.reset_n(reset_n),.clear(1'b0),.push(short_valid),.input_word({short_sequence,short_offset,short_sof,short_eol,short_pixels}),
        .pop(pop_b),.head(b),.have_head(have_b),.overflow(overflow_b)
    );
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin long_index<=0; short_index<=0; long_id<=0; short_id<=0; lost_pairs<=0; end
        else begin
            if(long_valid) begin
                long_index<=long_offset+1'b1;
                if(long_sof) long_id<=long_frame;
            end
            if(short_valid) begin
                short_index<=short_offset+1'b1;
                if(short_sof) short_id<=short_frame;
            end
            if(overflow_a || overflow_b || ((pop_a || pop_b) && !matching)) lost_pairs<=lost_pairs+1'b1;
        end
    end
    vid007_hdr_merge merge (
        .clk(clk),.reset_n(reset_n),.valid(matching),.sof(matching && tags_a[1]),.eol(matching && tags_a[0]),
        .long_pixels(a[39:0]),.short_pixels(b[39:0]),.exposure_shift(exposure_shift),
        .out_valid(valid),.out_sof(sof),.out_eol(eol),.fused_pixels(pixels)
    );
endmodule

// Both exposures are already in the receiver clock domain. Prefetch from
// registered RAM addresses, with three cache slots including an in-flight read.
module vid007_hdr_fifo #(
    parameter DW=40,AW=10
)(
    input wire clk,reset_n,clear,push,pop,
    input wire [DW-1:0] input_word,
    output wire [DW-1:0] head,
    output wire have_head,overflow
);
    localparam [AW:0] DEPTH=1<<AW;
    reg [AW:0] write_ptr,fetch_ptr;
    reg [1:0] put_slot,head_slot;
    reg [1:0] cached;
    reg fetched;
    wire full=(write_ptr-fetch_ptr)==DEPTH;
    wire store=push && !full;
    wire fetch=write_ptr!=fetch_ptr && (cached!=3 && !(cached==2 && fetched) || pop);
    reg [DW-1:0] mem [0:(1<<AW)-1],memory_word;
    reg [DW-1:0] cache [0:2];
    assign overflow=push && full;
    assign have_head=cached!=0;
    assign head=cache[head_slot];
    always @(posedge clk) begin
        if(store) mem[write_ptr[AW-1:0]]<=input_word;
        memory_word<=mem[fetch_ptr[AW-1:0]];
        if(fetched) cache[put_slot]<=memory_word;
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            write_ptr<=0; fetch_ptr<=0; put_slot<=0; head_slot<=0; cached<=0; fetched<=0;
        end else if(clear) begin
            write_ptr<=0; fetch_ptr<=0; put_slot<=0; head_slot<=0; cached<=0; fetched<=0;
        end else begin
            if(store) write_ptr<=write_ptr+1'b1;
            if(fetch) fetch_ptr<=fetch_ptr+1'b1;
            fetched<=fetch;
            if(fetched) put_slot<=put_slot==2?2'd0:put_slot+1'b1;
            if(pop) head_slot<=head_slot==2?2'd0:head_slot+1'b1;
            case({fetched,pop})
                2'b10: cached<=cached+1'b1;
                2'b01: cached<=cached-1'b1;
                default: cached<=cached;
            endcase
        end
    end
endmodule

// The CSI wrapper checks both frame IDs, CRCs and the output raster count.
// Reset the FIFOs at the first FS so an overrun cannot contaminate later pairs.
module vid007_hdr_pair_compact #(
    parameter LONG_AW=12, SHORT_AW=9, WIDTH=1920
)(
    input wire clk,reset_n,clear,
    input wire long_valid,short_valid,
    input wire [39:0] long_pixels,short_pixels,
    input wire [2:0] exposure_shift,
    output wire valid,sof,eol,
    output wire [39:0] pixels,
    output reg [31:0] lost_pairs,
    output reg failed
);
    wire have_long,have_short,overflow_long,overflow_short;
    wire [39:0] long_word,short_word;
    wire matching=have_long && have_short && !failed && !clear;
    reg [8:0] x;
    reg first;
    wire last=x==WIDTH/4-1;
    vid007_hdr_fifo #(.AW(LONG_AW)) long_fifo (
        .clk(clk),.reset_n(reset_n),.clear(clear),.push(long_valid && !failed),.input_word(long_pixels),
        .pop(matching),.head(long_word),.have_head(have_long),.overflow(overflow_long)
    );
    vid007_hdr_fifo #(.AW(SHORT_AW)) short_fifo (
        .clk(clk),.reset_n(reset_n),.clear(clear),.push(short_valid && !failed),.input_word(short_pixels),
        .pop(matching),.head(short_word),.have_head(have_short),.overflow(overflow_short)
    );
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin x<=0; first<=1; failed<=0; lost_pairs<=0; end
        else if(clear) begin x<=0; first<=1; failed<=0; end
        else begin
            if(matching) begin
                x<=last?9'd0:x+1'b1;
                first<=0;
            end
            if(overflow_long || overflow_short) begin
                lost_pairs<=lost_pairs+1'b1;
                failed<=1;
            end
        end
    end
    vid007_hdr_merge merge (
        .clk(clk),.reset_n(reset_n),.valid(matching),.sof(matching && first),.eol(matching && last),
        .long_pixels(long_word),.short_pixels(short_word),.exposure_shift(exposure_shift),
        .out_valid(valid),.out_sof(sof),.out_eol(eol),.fused_pixels(pixels)
    );
endmodule
