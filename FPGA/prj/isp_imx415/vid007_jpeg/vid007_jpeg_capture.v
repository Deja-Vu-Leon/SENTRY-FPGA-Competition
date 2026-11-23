`timescale 1ns/1ps

// Share the DDR raw capture storage between the Bayer path and the codec.
// Short packets are described separately; the variable scan byte count and
// point transform occupy an extra footer word only in JPEG mode.
module vid007_jpeg_capture #(
    parameter AW=11
)(
    input wire clk,reset_n,valid,sof,done,good,
    input wire [31:0] pixels,
    input wire [1:0] resolution,codec,
    input wire [7:0] target_kib,
    input wire dclk,dreset_n,pop,pop_desc,
    output wire [127:0] data,
    output wire [25:0] desc,
    output wire have_desc
);
    wire jpg=codec!=0;
    wire jpg_valid,jpg_first,jpg_last;
    wire [127:0] jpg_block;
    wire [21:0] scan_bytes;
    wire [2:0] transform;
    vid007_jpeg_channel encoder (
        .clk(clk),.reset_n(reset_n),.valid(valid),.sof(sof),.pixels(pixels),.resolution(resolution),
        .codec(codec),.target_kib(target_kib),.ready_block(jpg_valid),.first_block(jpg_first),
        .last_block(jpg_last),.block(jpg_block),.scan_bytes(scan_bytes),.actual_transform(transform)
    );
    reg [15:0] frame;
    reg [2:0] cadence;
    reg active,failed,finish,sensor_done,sensor_good,saw_last;
    reg [8:0] chunk;
    reg [7:0] words;
    reg [1:0] lane;
    reg [95:0] partial;
    reg [19:0] groups;
    reg report;
    reg [25:0] report_data;
    wire [AW:0] used;
    wire [5:0] desc_fill,desc_ready;
    wire data_room=used<=(1<<AW)-256 && desc_fill<=29;
    wire room=words!=0 || (!jpg && lane!=0) || data_room;
    wire selected=resolution!=0 || (jpg && codec==2) || cadence!=5;
    wire start=valid && sof && selected && data_room;
    wire take=valid && !sof && active && !failed && room;
    wire jpg_take=jpg_valid && active && !failed && room && !finish;
    wire raw_push=take && lane==3 && !jpg;
    wire [19:0] groups_expected=resolution==1?20'd129600:resolution==2?20'd32400:20'd518400;
    // Finish JPEG on the sensor-validated end of frame, not on EOF of the
    // cropped raster. Reserve one block for a short registered footer.
    wire push_footer=jpg && finish && sensor_good && saw_last && groups==groups_expected && !failed && room;
    wire push=raw_push || (jpg && jpg_take) || push_footer;
    wire [127:0] footer={96'd0,7'h55,transform,scan_bytes};
    wire [127:0] input_data=push_footer?footer:jpg?jpg_block:{pixels,partial};
    wire [7:0] tail_expected=resolution==1?8'd15:resolution==2?8'd195:8'd60;
    wire [7:0] regular_words=jpg?8'd254:8'd255;

    pad_afifo #(.DW(128),.AW(AW)) u_data (
        .wclk(clk),.wrst_n(reset_n),.wr_en(push),.din(input_data),.full(),.wr_used(used),.wr_lost(),
        .rclk(dclk),.rrst_n(dreset_n),.rd_en(pop),.dout(data),.rd_avail()
    );
    pad_afifo #(.DW(26),.AW(5)) u_desc (
        .wclk(clk),.wrst_n(reset_n),.wr_en(report),.din(report_data),.full(),.wr_used(desc_fill),.wr_lost(),
        .rclk(dclk),.rrst_n(dreset_n),.rd_en(pop_desc),.dout(desc),.rd_avail(desc_ready)
    );
    assign have_desc=desc_ready!=0;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            frame<=16'hffff; cadence<=0; active<=0; failed<=0; finish<=0; sensor_done<=0; sensor_good<=0;
            chunk<=0; words<=0; lane<=0; partial<=0; groups<=0; report<=0; report_data<=0; saw_last<=0;
        end else begin
            report<=0;
            if(valid && sof) begin
                frame<=frame+1'b1; cadence<=cadence==5?0:cadence+1'b1;
                active<=start; failed<=0; finish<=0; saw_last<=0; sensor_done<=0; sensor_good<=0;
                chunk<=0; words<=0; lane<=start?2'd1:0;
                partial[31:0]<=pixels; groups<=start?20'd1:0;
                if(active) begin report<=1; report_data<={frame,2'b10,words}; end
            end else if(active) begin
                if((jpg?jpg_valid:valid) && !room) failed<=1;
                if(jpg_valid && jpg_last) saw_last<=1;
                if(take) begin
                    groups<=groups+1'b1; lane<=lane+1'b1;
                    case(lane)
                        0: partial[31:0]<=pixels;
                        1: partial[63:32]<=pixels;
                        2: partial[95:64]<=pixels;
                        default: ;
                    endcase
                end
                if(push) begin
                    if(words==regular_words-1'b1 && !push_footer) begin
                        report<=1; report_data<={frame,2'b00,regular_words};
                        words<=0; chunk<=chunk+1'b1;
                        if(chunk==510 && jpg) failed<=1;
                    end else words<=words+1'b1;
                end
                if(finish) begin
                    active<=0; finish<=0;
                    report<=1; report_data<={frame,1'b1,push_footer,words+{7'd0,push_footer}};
                end
                if(done && !jpg) begin
                    active<=0; report<=1;
                    report_data<={frame,1'b1,(good && !failed && groups==groups_expected && words==tail_expected && lane==0),words};
                end
                if(done && jpg) begin
                    sensor_done<=1;
                    sensor_good<=good;
                end
                if(jpg && sensor_done && (saw_last || !sensor_good || groups!=groups_expected)) finish<=1;
            end
        end
    end
endmodule
