enum { CHANNEL_X=44, CHANNEL_Y=154, CHANNEL_STEP=104, CHANNEL_W=93, CHANNEL_H=40,
       OP_X=44, OP_Y=555, OP_STEP=45, OP_W=195, OP_H=38,
       LEVEL_X=52, LEVEL_Y=800, LEVEL_W=385 };

static atomic_uint requested_config[4], live_config[4];
static atomic_uint capture_fps[4], capture_bad[4], axi_write_errors[4];
static unsigned config_channel;
static int advanced_board, resolution_board;

static unsigned channel_config(void) {
    return atomic_load(&requested_config[config_channel]);
}

static void config_toggle(unsigned flag) {
    unsigned config=channel_config() ^ flag;
    if(flag==4 && (config&4)) config &= ~0x70u;
    atomic_store(&requested_config[config_channel],config);
}

static void config_operator(unsigned operation) {
    unsigned config=channel_config() & ~0x70u;
    if(operation) config&=~4u;
    atomic_store(&requested_config[config_channel],config | (operation<<4));
}

static void config_level(int level) {
    if(level<0) level=0;
    if(level>255) level=255;
    atomic_store(&requested_config[config_channel],(channel_config()&255u)|((unsigned)level<<8));
}

static void config_click(int x,int y) {
    if(y>=CHANNEL_Y && y<CHANNEL_Y+CHANNEL_H && x>=CHANNEL_X) {
        unsigned dx=x-CHANNEL_X;
        if(dx/CHANNEL_STEP<4 && dx%CHANNEL_STEP<CHANNEL_W) config_channel=dx/CHANNEL_STEP;
    } else if(y>=FILTER_FIRST_Y && y<FILTER_FIRST_Y+3*FILTER_STEP && x>=FILTER_X && x<FILTER_X+FILTER_W) {
        unsigned dy=y-FILTER_FIRST_Y;
        if(dy%FILTER_STEP<FILTER_H) config_toggle(1u<<(dy/FILTER_STEP));
    } else if(y>=OP_Y && y<OP_Y+4*OP_STEP && x>=OP_X && x<OP_X+405) {
        unsigned dy=y-OP_Y, dx=x-OP_X;
        unsigned operation=(dy/OP_STEP)*2+(dx>=OP_W+15);
        if(dy%OP_STEP<OP_H && operation<7 && dx%(OP_W+15)<OP_W) config_operator(operation);
    } else if(y>=LEVEL_Y-16 && y<=LEVEL_Y+24 && x>=LEVEL_X-6 && x<=LEVEL_X+LEVEL_W+6) {
        config_level((x-LEVEL_X)*255/LEVEL_W);
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
