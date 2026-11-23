/* Fixed 1680x1050 DRM layout. Keep the existing camera crop coordinates. */
#include <wchar.h>

enum { RK_BUTTON_X = 390, RK_BUTTON_Y = 19, RK_BUTTON_W = 150, RK_BUTTON_STEP = 162 };
static FT_Face cjk_font;

static void rk_font_init(void) {
    if (font_library &&
        !FT_New_Face(font_library, "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0, &cjk_font))
        FT_Set_Pixel_Sizes(cjk_font, 0, 18);
}

static void rk_label(struct surface *s, int x, int baseline, const wchar_t *label, uint32_t color) {
    for (; *label; label++) {
        FT_Face face = *label < 128 ? font : cjk_font;
        if (!face || FT_Load_Char(face, (FT_ULong)*label, FT_LOAD_RENDER)) continue;
        FT_GlyphSlot glyph = face->glyph;
        for (unsigned y=0; y<glyph->bitmap.rows; y++) {
            int py=baseline-glyph->bitmap_top+(int)y;
            if (py<0 || py>=HEIGHT) continue;
            uint32_t *line=(uint32_t *)(s->memory+py*s->pitch);
            for (unsigned col=0; col<glyph->bitmap.width; col++) {
                int px=x+glyph->bitmap_left+(int)col;
                if (px>=0 && px<WIDTH && glyph->bitmap.buffer[y*glyph->bitmap.pitch+col]>75)
                    line[px]=color;
            }
        }
        x += glyph->advance.x >> 6;
    }
}

static void rk_chrome(struct surface *s, const unsigned fps[4], int mode, unsigned offline) {
    static uint32_t header[68][WIDTH];
    static uint32_t ribbons[4][34][340];
    static int last_mode=-2;
    static unsigned last_offline=~0u, last_request=~0u, last_fps[4];
    const unsigned request=atomic_load(&requested_mode);
    const uint32_t ink=0xeef4ef, muted=0xaebeb9, mint=0xa4f2d0, amber=0xf6ad76;
    if (mode!=last_mode || request!=last_request || offline!=last_offline ||
        memcmp(last_fps,fps,sizeof(last_fps))) {
        struct surface bar={.memory=(uint8_t *)header,.pitch=sizeof(header[0])};
        box(&bar,0,0,WIDTH,68,0x101719);
        box(&bar,0,67,WIDTH,1,0x3b494a);
        box(&bar,22,19,26,26,mint);
        rk_label(&bar,28,40,L"S",0x0f1a17);
        rk_label(&bar,61,41,L"SENTRY",ink);
        box(&bar,173,16,1,36,0x3a4a49);
        rk_label(&bar,191,40,L"四路视觉监控",ink);
        const wchar_t *labels[]={L"1   灰度",L"2   高斯",L"3   Sobel"};
        for (unsigned i=0;i<3;i++) {
            int x=RK_BUTTON_X+i*RK_BUTTON_STEP;
            int on=(request>>i)&1;
            box(&bar,x,RK_BUTTON_Y,RK_BUTTON_W,32,on?0x24443a:0x1e282b);
            box(&bar,x,RK_BUTTON_Y+31,RK_BUTTON_W,1,on?mint:0x435456);
            box(&bar,x+10,32,7,7,on?mint:0x72827d);
            rk_label(&bar,x+27,41,labels[i],on?mint:ink);
        }
        rk_label(&bar,900,40,mode<0?L"切换中":mode&4?L"边缘图":mode?L"预处理":L"彩色原画",
                 mode<0?amber:muted);
        rk_label(&bar,1060,40,L"1920 × 1080",ink);
        const unsigned online=4-(unsigned)__builtin_popcount(offline&15);
        wchar_t status[48];
        swprintf(status,48,L"%u / 4 路有信号",online);
        box(&bar,1410,31,8,8,online==4?mint:amber);
        rk_label(&bar,1430,40,mode<0?L"等待画面":status,online==4?mint:amber);

        const wchar_t *ports[]={L"A0",L"A1",L"B0",L"B1"};
        for (unsigned i=0;i<4;i++) {
            struct surface tile={.memory=(uint8_t *)ribbons[i],.pitch=sizeof(ribbons[i][0])};
            int lost=(offline>>i)&1;
            box(&tile,0,0,340,34,0x121a1d);
            box(&tile,0,0,3,34,lost?amber:mint);
            rk_label(&tile,12,24,ports[i],lost?amber:mint);
            rk_label(&tile,61,24,i<2?L"车辆识别 · 测距":L"行人识别",ink);
            wchar_t rate[32];
            swprintf(rate,32,L"%u FPS",fps[i]);
            rk_label(&tile,243,24,lost?L"无信号":mode<0?L"切换中":rate,lost?amber:muted);
        }
        last_mode=mode;
        last_request=request;
        last_offline=offline;
        memcpy(last_fps,fps,sizeof(last_fps));
    }
    for (unsigned y=0;y<68;y++) memcpy(s->memory+y*s->pitch,header[y],sizeof(header[y]));
    for (unsigned ch=0;ch<4;ch++) {
        unsigned x=(ch%2)*TILE_W+12, y=68+(ch/2)*TILE_H+TILE_H-45;
        for (unsigned row=0;row<34;row++)
            memcpy(s->memory+(y+row)*s->pitch+x*4,ribbons[ch][row],sizeof(ribbons[ch][row]));
    }
    box(s,TILE_W-1,68,2,2*TILE_H,0x243335);
    box(s,0,68+TILE_H-1,WIDTH,2,0x243335);
    box(s,0,68+2*TILE_H,WIDTH,HEIGHT-(68+2*TILE_H),0x101719);
}
