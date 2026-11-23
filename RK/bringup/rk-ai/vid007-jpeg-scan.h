#include <stddef.h>
#include <stdint.h>
#include <pthread.h>

static uint16_t vid007_huffman[8192];
static pthread_once_t vid007_huffman_once=PTHREAD_ONCE_INIT;

static void vid007_init_huffman(void) {
    for(unsigned code=0;code<8192;code++) {
        unsigned size=0,used=1,delta=0;
        if(code&4096u) {
            unsigned prefix=code>>9;
            if(prefix==15 && (code&256u)) continue;
            size=prefix==15?8:prefix-7;
            used=size+(size==8?5:4);
            unsigned mask=(1u<<size)-1;
            delta=(code>>(13-used))&mask;
            if(!(delta>>(size-1))) delta=(delta-mask)&511u;
        }
        vid007_huffman[code]=(uint16_t)((delta<<4)|used);
    }
}

/* The FPGA emits one 8-bit SOF3 component with predictor 1 and the fixed
   Huffman table in write_jpeg_header. Decode exactly those scans, including
   the required byte escaping, fill bits, and raster length. */
static int vid007_decode_scan(const uint8_t *input,size_t length,uint8_t *tokens,
                             uint8_t *raster,unsigned width,unsigned height,unsigned point) {
    size_t count=0;
    for(size_t i=0;i<length;i++) {
        uint8_t value=input[i];
        tokens[count++]=value;
        if(value==0xff && (++i==length || input[i])) return -1;
    }
    size_t offset=0;
    pthread_once(&vid007_huffman_once,vid007_init_huffman);
    unsigned pending=0;
    uint64_t buffer=0;
    unsigned max_value=255u>>point;
    unsigned previous_row=128u>>point;
    for(unsigned y=0;y<height;y++) {
        unsigned predictor=previous_row;
        unsigned x=0;
        while(x<width) {
            if(pending<16 && offset+4<=count) {
                uint32_t block;
                memcpy(&block,tokens+offset,sizeof(block));
                buffer=(buffer<<32)|__builtin_bswap32(block);
                pending+=32;
                offset+=4;
            }
            while(pending<13 && offset<count) {
                buffer=(buffer<<8)|tokens[offset++];
                pending+=8;
            }
            if(!pending) return -1;
            if(x && pending>=8 && !(buffer>>(pending-8)&255u) && x+8<=width) {
                memset(raster+x,predictor<<point,8);
                pending-=8;
                x+=8;
                continue;
            }
            unsigned index=pending>=13 ? (buffer>>(pending-13))&8191u :
                                          (buffer<<(13-pending))&8191u;
            unsigned symbol=vid007_huffman[index],consumed=symbol&15u;
            if(!consumed || pending<consumed) return -1;
            predictor=(predictor+(symbol>>4))&255u;
            if(predictor>max_value) return -1;
            pending-=consumed;
            if(!x) previous_row=predictor;
            raster[x++]=(uint8_t)(predictor<<point);
        }
        raster+=width;
    }
    if(offset!=count || pending>7) return -1;
    uint64_t fill=(UINT64_C(1)<<pending)-1;
    return (buffer&fill)==fill?0:-1;
}
