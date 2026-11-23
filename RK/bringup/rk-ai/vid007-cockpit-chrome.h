#include "vid007-armour-theme.h"
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


static void rk_chrome(struct surface *s, int mode, unsigned offline) {
    static uint32_t header[68][WIDTH];
    static unsigned previous_page=~0u, previous_offline=~0u;
    static int previous_mode=-2;
    static time_t previous_time;
    time_t timestamp=time(NULL);
    if(timestamp!=previous_time || previous_page!=ui_page ||
       previous_offline!=offline || previous_mode!=mode) {
        struct surface bar={.memory=(uint8_t *)header,.pitch=sizeof(header[0])};
        box(&bar,0,0,WIDTH,68,ARMOUR_WHITE);
        box(&bar,0,0,268,64,ARMOUR_NAVY);
        box(&bar,0,64,WIDTH,4,ARMOUR_BLUE);
        box(&bar,0,64,62,4,ARMOUR_RED);
        for(int y=0;y<30;y++) box(&bar,15+y/3,16+y,22,1,ARMOUR_BLUE);
        rk_label(&bar,22,39,L"S",ARMOUR_PAPER);
        rk_label(&bar,52,30,L"慧行智瞳",ARMOUR_PAPER);
        rk_label(&bar,52,53,L"SENTRY CONTROL",0xbcd1fa);
        const wchar_t *pages[]={L"F1  图像传输",L"F2  预处理",L"F3  链路诊断",L"F4  检测日志",L"F5  驾驶感知",L"F6  循环录像",L"F7  AI 对话"};
        for(unsigned i=0;i<7;i++) {
            int x=PAGE_X+i*PAGE_STEP;
            int active=i==ui_page;
            box(&bar,x,PAGE_Y,PAGE_W,PAGE_H,active?ARMOUR_BLUE:ARMOUR_SILVER);
            box(&bar,x,PAGE_Y+PAGE_H-3,PAGE_W,3,active?ARMOUR_RED:ARMOUR_EDGE);
            rk_label(&bar,x+12,42,pages[i],active?ARMOUR_PAPER:ARMOUR_INK);
        }
        wchar_t status[40],clock_text[24]=L"";
        struct tm civil;
        if(localtime_r(&timestamp,&civil)) wcsftime(clock_text,24,L"%H:%M:%S",&civil);
        swprintf(status,40,L"%u / 4 路在线",4-(unsigned)__builtin_popcount(offline&15));
        box(&bar,1390,17,9,9,mode<0?ARMOUR_YELLOW:offline?ARMOUR_RED:ARMOUR_GREEN);
        rk_label(&bar,1409,28,mode<0?L"设备切换中":status,ARMOUR_INK);
        rk_label(&bar,1409,52,clock_text,ARMOUR_MUTED);
        previous_page=ui_page; previous_offline=offline; previous_mode=mode; previous_time=timestamp;
    }
    for(unsigned y=0;y<68;y++) memcpy(s->memory+y*s->pitch,header[y],sizeof(header[y]));
}
