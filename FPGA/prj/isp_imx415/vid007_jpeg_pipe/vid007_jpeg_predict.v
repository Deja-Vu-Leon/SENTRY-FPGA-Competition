`timescale 1ns/1ps

// JPEG T.81 SOF3 predictor 1, one raster component, precision 8.
// A point transform of zero retains every input byte. For a nonzero point
// transform the lowest input bits are discarded before prediction.
module vid007_jpeg_predict (
    input wire clk, reset_n, valid, sof, eol, eof,
    input wire [31:0] pixels,
    input wire [2:0] point_transform,
    output reg valid_q, sof_q, eof_q,
    output reg [51:0] code,
    output reg [5:0] bits
);
    reg first_column;
    reg [7:0] previous, row_first;
    wire [7:0] current [0:3];
    wire [7:0] predict [0:3];
    wire [12:0] codes [0:3];
    wire [3:0] lengths [0:3];
    reg signed [8:0] differences [0:3];
    assign predict[0]=sof ? 8'd128 >> point_transform : first_column ? row_first : previous;

    function [16:0] encode;
        input signed [8:0] delta;
        reg [7:0] magnitude, amplitude;
        reg [3:0] size;
        reg [4:0] prefix;
        reg [7:0] mask;
        begin
            magnitude=delta[8] ? -delta : delta;
            casez(magnitude)
                8'b1???????: size=8;
                8'b01??????: size=7;
                8'b001?????: size=6;
                8'b0001????: size=5;
                8'b00001???: size=4;
                8'b000001??: size=3;
                8'b0000001?: size=2;
                8'b00000001: size=1;
                default: size=0;
            endcase
            mask=~(8'hff<<size);
            amplitude=(delta[8] ? ~magnitude : magnitude)&mask;
            prefix=size==8 ? 5'd30 : size!=0 ? {1'b0,size}+5'd7 : 0;
            encode={size+(size==8?4'd5:size!=0?4'd4:4'd1),
                    ({8'd0,prefix}<<size)|{5'd0,amplitude}};
        end
    endfunction

    genvar i;
    generate for(i=0;i<4;i=i+1) begin : lane
        assign current[i]=pixels[i*8+:8]>>point_transform;
        if(i!=0) assign predict[i]=current[i-1];
        always @(posedge clk)
            differences[i]<=$signed({1'b0,current[i]})-$signed({1'b0,predict[i]});
        assign {lengths[i],codes[i]}=encode(differences[i]);
    end endgenerate

    reg [12:0] code1 [0:3];
    reg [3:0] len1 [0:3];
    reg [25:0] ab, cd;
    reg [4:0] ab_bits,cd_bits;
    reg [2:0] valid_pipe, sof_pipe, eof_pipe;
    integer j;
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin
            previous<=0; row_first<=0; first_column<=1;
            valid_pipe<=0; sof_pipe<=0; eof_pipe<=0; valid_q<=0; sof_q<=0; eof_q<=0;
        end else begin
            if(valid) begin
                if(sof || first_column) row_first<=current[0];
                previous<=current[3];
                first_column<=eol;
            end
            valid_pipe<={valid_pipe[1:0],valid};
            sof_pipe<={sof_pipe[1:0],sof};
            eof_pipe<={eof_pipe[1:0],eof};
            valid_q<=valid_pipe[2]; sof_q<=sof_pipe[2]; eof_q<=eof_pipe[2];
        end
    end
    always @(posedge clk) begin
        for(j=0;j<4;j=j+1) begin code1[j]<=codes[j]; len1[j]<=lengths[j]; end
        ab<=({13'd0,code1[0]}<<len1[1])|{13'd0,code1[1]};
        cd<=({13'd0,code1[2]}<<len1[3])|{13'd0,code1[3]};
        ab_bits<={1'b0,len1[0]}+len1[1]; cd_bits<={1'b0,len1[2]}+len1[3];
        code<=({26'd0,ab}<<cd_bits)|{26'd0,cd};
        bits<={1'b0,ab_bits}+cd_bits;
    end
endmodule
