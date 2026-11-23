enum { CHANNEL_X=44, CHANNEL_Y=154, CHANNEL_STEP=104, CHANNEL_W=93, CHANNEL_H=40,
       OP_X=44, OP_Y=555, OP_STEP=45, OP_W=195, OP_H=38,
       LEVEL_X=52, LEVEL_Y=840, LEVEL_W=385 };

static atomic_uint requested_config[4], live_config[4];
static atomic_uint capture_fps[4], capture_bad[4], axi_write_errors[4];
static unsigned config_channel;
static int advanced_board, resolution_board, measurement_board;
static atomic_uint subpixel_result[4];

static unsigned channel_config(void) {
    return atomic_load(&requested_config[config_channel]);
}

static void config_toggle(unsigned flag) {
    unsigned config=channel_config() ^ flag;
    if(flag==4 && (config&4)) config &= ~0x70u;
    atomic_store(&requested_config[config_channel],config);
}

static void config_operator(unsigned operation) {
    unsigned config=channel_config();
    unsigned previous=(config>>4)&7u;
    config&=~0x70u;
    if(operation) config&=~4u;
    if(operation>=7) {
        config&=0x00ffu;
        config|=(operation==8?0xa000u:0x1000u)|0x70u;
    } else {
        if(previous==7) config=(config&255u)|0x5000u;
        config|=operation<<4;
    }
    atomic_store(&requested_config[config_channel],config);
}

static void config_level(int level) {
    if(level<0) level=0;
    unsigned config=channel_config();
    if((config&0x70u)==0x70u) {
        if(level>127) level=127;
        config&=0x80ffu;
    } else {
        if(level>255) level=255;
        config&=255u;
    }
    atomic_store(&requested_config[config_channel],config|((unsigned)level<<8));
}

static void config_click(int x,int y) {
    if(y>=CHANNEL_Y && y<CHANNEL_Y+CHANNEL_H && x>=CHANNEL_X) {
        unsigned dx=x-CHANNEL_X;
        if(dx/CHANNEL_STEP<4 && dx%CHANNEL_STEP<CHANNEL_W) config_channel=dx/CHANNEL_STEP;
    } else if(y>=FILTER_FIRST_Y && y<FILTER_FIRST_Y+3*FILTER_STEP && x>=FILTER_X && x<FILTER_X+FILTER_W) {
        unsigned dy=y-FILTER_FIRST_Y;
        if(dy%FILTER_STEP<FILTER_H) config_toggle(1u<<(dy/FILTER_STEP));
    } else if(y>=OP_Y && y<OP_Y+(measurement_board?5:4)*OP_STEP && x>=OP_X && x<OP_X+405) {
        unsigned dy=y-OP_Y, dx=x-OP_X;
        unsigned operation=(dy/OP_STEP)*2+(dx>=OP_W+15);
        if(dy%OP_STEP<OP_H && operation<(measurement_board?9u:7u) && dx%(OP_W+15)<OP_W) config_operator(operation);
    } else if(y>=LEVEL_Y-16 && y<=LEVEL_Y+24 && x>=LEVEL_X-6 && x<=LEVEL_X+LEVEL_W+6) {
        config_level((x-LEVEL_X)*(((channel_config()&0x70u)==0x70u)?127:255)/LEVEL_W);
    }
}

enum { RESOLUTION_X=16, RESOLUTION_W=175, RESOLUTION_STEP=205 };
static void resolution_click(int x,int y) {
    if(y<1012||x<RESOLUTION_X) return;
    unsigned dx=x-RESOLUTION_X, ch=dx/RESOLUTION_STEP;
    if(ch>=4||dx%RESOLUTION_STEP>=RESOLUTION_W) return;
    unsigned config=atomic_load(&requested_config[ch]);
    unsigned next=(resolution(config)+1)%3;
    atomic_store(&requested_config[ch],(config&~136u)|(next==1?128u:next==2?8u:0));
}

static int jpeg_board;
static int jpeg_panel;
static atomic_uint jpeg_request[4], jpeg_live[4], jpeg_actual[4], jpeg_bytes[4];

static void jpeg_click(int x,int y) {
    if(y<166) return;
    unsigned ch=(y-166)/92, row=(y-166)%92;
    if(ch>=4) return;
    unsigned requested=atomic_load(&jpeg_request[ch]);
    if(row<35 && x>=1130 && x<1580) {
        unsigned mode=(x-1130)/150;
        atomic_store(&jpeg_request[ch],(requested&~3u)|mode);
    } else if(row>=42 && row<80 && x>=1170 && x<1560 && (requested&3u)==2) {
        unsigned scale=resolution(atomic_load(&requested_config[ch]));
        unsigned min=scale==0?17u:scale==1?5u:2u;
        unsigned value=min+(unsigned)(x-1170)*(64-min)/389;
        atomic_store(&jpeg_request[ch],(value<<2)|2u);
    }
}
