`timescale 1ns/1ps

// 4x4 tiles (480x270), 16 bins. Sample one pixel per four-pixel beat.
// Learn one frame while displaying the previous LUT; calculate on the next.
module vid007_clahe (
    input wire clk, reset_n, valid, sof, eol,
    input wire [31:0] pixels,
    input wire enable,
    input wire [7:0] clip,
    output reg out_valid, out_sof,
    output reg [31:0] out_pixels
);
    reg [8:0] x;
    reg [10:0] y;
    wire [8:0] col = sof ? 9'd0 : x;
    wire [10:0] row = sof ? 11'd0 : y;
    wire last_pixel = valid && eol && row == 1079;
    wire [1:0] tx = col<120 ? 0 : col<240 ? 1 : col<360 ? 2 : 3;
    wire [1:0] ty = row<270 ? 0 : row<540 ? 1 : row<810 ? 2 : 3;

    reg [8:0] cursor;
    localparam INIT=0, READY=1, ACC=2, SCAN=3, BUILD=4, SWAP=5;
    reg [2:0] state;
    reg bank, have_lut;
    wire swap_now = state==SWAP && valid && sof && enable;
    wire learn = enable && valid && (state==ACC || (sof && state==READY) || swap_now);
    wire [7:0] address = {ty,tx,pixels[7:4]};
    reg last_learn;
    reg [7:0] previous_address;
    wire [14:0] hist_q;
    reg last_write;
    reg [7:0] last_address;
    reg [14:0] last_data;
    reg delayed_read;
    reg [7:0] delayed_address;
    wire [14:0] increment = (last_write && last_address==previous_address ? last_data : hist_q)+1'b1;
    wire scan_hist = (state==SCAN || state==BUILD) && cursor<256;
    wire hist_write = last_learn || state==INIT || (state==BUILD && delayed_read);
    wire [7:0] hist_waddr = last_learn ? previous_address : state==INIT ? cursor[7:0] : delayed_address;
    wire [14:0] hist_data = last_learn ? increment : 15'd0;
    pp_sdp_ram #(.DW(15),.AW(8)) histogram (
        .clk(clk),.we(hist_write),.waddr(hist_waddr),.wdata(hist_data),
        .re(learn || scan_hist),.raddr(learn ? address : cursor[7:0]),.rdata(hist_q)
    );

    reg [14:0] excess [0:15];
    reg [14:0] accumulated, cdf;
    wire [14:0] limit = clip<8 ? 15'd1024 : {clip,7'b0};
    wire [14:0] limited = hist_q>limit ? limit : hist_q;
    wire [14:0] extra = hist_q-limited;
    wire [14:0] tile_excess = excess[delayed_address[7:4]];
    wire [14:0] redistributed = limited+{4'b0,tile_excess[14:4]}+
                                (delayed_address[3:0]<tile_excess[3:0]);
    wire [14:0] cumulative = (delayed_address[3:0]==0 ? 15'd0 : cdf)+redistributed;
    reg [7:0] lut_address;
    reg lut_write;
    reg [14:0] lut_cdf;
    reg [23:0] product;
    reg [7:0] product_address;
    reg product_write;
    wire [7:0] lut_value = product[23] ? 8'hff : product[22:15];

    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            x<=0; y<=0; cursor<=0; state<=INIT; bank<=0; have_lut<=0;
            last_learn<=0; previous_address<=0; last_write<=0; last_address<=0; last_data<=0;
            delayed_read<=0; delayed_address<=0; accumulated<=0; cdf<=0;
            lut_address<=0; lut_write<=0; lut_cdf<=0;
            product<=0; product_address<=0; product_write<=0;
        end else begin
            if(valid) begin
                x<=eol?0:col+1'b1;
                y<=eol?row+1'b1:row;
            end
            last_learn<=learn;
            previous_address<=address;
            last_write<=last_learn;
            last_address<=previous_address;
            last_data<=increment;
            delayed_read<=scan_hist;
            delayed_address<=cursor[7:0];
            lut_write<=state==BUILD && delayed_read;
            lut_address<=delayed_address;
            lut_cdf<=cumulative;
            // floor(cdf*257/32768) differs by at most one code from cdf*255/32400.
            product<={1'b0,lut_cdf,8'b0}+{9'b0,lut_cdf};
            product_address<=lut_address;
            product_write<=lut_write;
            case(state)
                INIT: if(cursor==255) begin state<=READY; cursor<=0; end
                      else cursor<=cursor+1'b1;
                READY: if(learn) state<=ACC;
                ACC: if(last_pixel) begin state<=SCAN; cursor<=0; end
                SCAN: begin
                    if(cursor<256) cursor<=cursor+1'b1;
                    if(delayed_read) begin
                        accumulated<=(delayed_address[3:0]==0?15'd0:accumulated)+extra;
                        if(delayed_address[3:0]==15)
                            excess[delayed_address[7:4]]<=accumulated+extra;
                        if(delayed_address==255) begin state<=BUILD; cursor<=0; end
                    end
                end
                BUILD: begin
                    if(cursor<256) cursor<=cursor+1'b1;
                    if(delayed_read) cdf<=cumulative;
                    if(product_write && product_address==255) state<=SWAP;
                end
                SWAP: if(swap_now) begin state<=ACC; bank<=~bank; have_lut<=1; end
            endcase
        end
    end

    // Tile-centered bilinear interpolation. Four tile-parity banks allow four
    // adjacent lookup results per lane without duplicating the whole table.
    wire [1:0] right = col<60 ? 0 : col<180 ? 1 : col<300 ? 2 : 3;
    wire [1:0] bottom = row<135 ? 0 : row<405 ? 1 : row<675 ? 2 : 3;
    wire [1:0] left = col<60 ? 0 : col<180 ? 0 : col<300 ? 1 : col<420 ? 2 : 3;
    wire [1:0] top = row<135 ? 0 : row<405 ? 0 : row<675 ? 1 : row<945 ? 2 : 3;
    wire [8:0] x_start = left==0 ? 9'd60 : left==1 ? 9'd180 : 9'd300;
    wire [10:0] y_start = top==0 ? 11'd135 : top==1 ? 11'd405 : 11'd675;
    wire [8:0] x_dist = left==right ? 9'd0 : col-x_start;
    wire [10:0] y_dist = top==bottom ? 11'd0 : row-y_start;
    reg [8:0] wx1;
    reg [8:0] wy1;
    reg [15:0] wy_product;
    reg [2:0] pass, valid_tags, sof_tags;
    reg [31:0] pixels1, pixels2, pixels3;
    reg [3:0] parity;
    wire read_bank = swap_now ? ~bank : bank;
    wire [31:0] mapped;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            valid_tags<=0; sof_tags<=0; pass<=0; out_valid<=0; out_sof<=0;
        end else begin
            valid_tags<={valid_tags[1:0],valid}; sof_tags<={sof_tags[1:0],sof};
            pass<={pass[1:0],enable && (have_lut || swap_now)};
            out_valid<=valid_tags[2]; out_sof<=sof_tags[2];
        end
    end
    always @(posedge clk) begin
        // 17/8 is within 1.1% of 256/120. 243/256 approximates 256/270.
        wx1<=x_dist*17>>3;
        wy_product<=y_dist*243;
        wy1<={1'b0,wy_product[15:8]};
        parity<={top[0],bottom[0],left[0],right[0]};
        pixels1<=pixels; pixels2<=pixels1; pixels3<=pixels2;
        out_pixels<=pass[2]?mapped:pixels3;
    end
    genvar lane, table_bank;
    generate for(lane=0; lane<4; lane=lane+1) begin : sample_lane
        wire [7:0] q [0:3];
        for(table_bank=0; table_bank<4; table_bank=table_bank+1) begin : tables
            localparam XP=table_bank&1, YP=table_bank>>1;
            wire [1:0] ax=left[0]==XP ? left : right;
            wire [1:0] ay=top[0]==YP ? top : bottom;
            pp_sdp_dram #(.DW(8),.AW(7)) lut (
                .clk(clk),.we(product_write && product_address[4]==XP && product_address[6]==YP),
                .waddr({~bank,product_address[7],product_address[5],product_address[3:0]}),.wdata(lut_value),
                .re(valid),.raddr({read_bank,ay[1],ax[1],pixels[lane*8+4+:4]}),.rdata(q[table_bank])
            );
        end
        reg [7:0] upper, lower;
        wire [16:0] mix1=q[{parity[3],parity[1]}]*(9'd256-wx1)+q[{parity[3],parity[0]}]*wx1;
        wire [16:0] mix2=q[{parity[2],parity[1]}]*(9'd256-wx1)+q[{parity[2],parity[0]}]*wx1;
        reg [16:0] vertical;
        always @(posedge clk) begin
            upper<=mix1[15:8]; lower<=mix2[15:8];
            vertical<=upper*(9'd256-wy1)+lower*wy1;
        end
        assign mapped[lane*8+:8]=vertical[15:8];
    end endgenerate
endmodule
