#include <glob.h>
#include <linux/input.h>
#include <ft2build.h>
#include FT_FREETYPE_H

enum { FILTER_X=44, FILTER_W=405, FILTER_FIRST_Y=226, FILTER_STEP=79, FILTER_H=66,
       LOG_X=1044, LOG_Y=263, LOG_ROW_H=56, LOG_ROWS=11, LOG_W=590 };
static atomic_uint requested_mode;
static atomic_int published_mode;
#include "vid007-cockpit-ui.h"
static FT_Library font_library;
static FT_Face font;

static void box(struct surface *s, int x, int y, int w, int h, uint32_t color) {
    for (int row = y; row < y + h; row++) {
        uint32_t *line = (uint32_t *)(s->memory + row * s->pitch);
        for (int col = x; col < x + w; col++) line[col] = color;
    }
}

#include "vid007-cockpit-input.h"

static void parameter_commit(int field,int value) {
    if(field==TONE_FIELDS) config_level(value);
    else {
        if(value<tone_min[field]) value=tone_min[field];
        if(value>tone_max[field]) value=tone_max[field];
        tone_values[config_channel][field]=value;
    }
    tone_revision++;
}

static void parameter_move(int x) {
    int field=parameter_drag;
    int start=field==TONE_FIELDS?LEVEL_X:TONE_X+field*TONE_STEP;
    int width=field==TONE_FIELDS?LEVEL_W:TONE_W;
    int lo=field==TONE_FIELDS?0:tone_min[field];
    int hi=field==TONE_FIELDS?((channel_config()&0x70u)==0x70u?127:255):tone_max[field];
    int position=x-start;
    if(position<0) position=0;
    if(position>width) position=width;
    parameter_draft=lo+position*(hi-lo)/width;
    tone_revision++;
}

static int parameter_click(int x,int y) {
    int field=(x-TONE_X)/TONE_STEP;
    parameter_focus=-1;
    parameter_text[0]=0;
    tone_revision++;
    if(x>=TONE_X && field<TONE_FIELDS && (x-TONE_X)%TONE_STEP<=TONE_W) {
        if(y>=894 && y<932) { parameter_focus=field; return 1; }
        if(y>=TONE_SLIDER_Y-13 && y<=TONE_SLIDER_Y+17) {
            parameter_drag=field;
            parameter_move(x);
            return 1;
        }
    }
    if(x>=521 && x<704 && y>=987 && y<1027) {
        memcpy(tone_values[config_channel],tone_default,sizeof(tone_default));
        return 1;
    }
    const unsigned config=channel_config(),op=(config>>4)&7;
    if(!(config&4) && op!=2 && op<5) return 0;
    if(x>=327 && x<=440 && y>=788 && y<826) {
        parameter_focus=TONE_FIELDS;
        return 1;
    }
    if(x>=LEVEL_X-6 && x<=LEVEL_X+LEVEL_W+6 && y>=LEVEL_Y-13 && y<=LEVEL_Y+17) {
        parameter_drag=TONE_FIELDS;
        parameter_move(x);
        return 1;
    }
    return 0;
}

static void parameter_key(unsigned code) {
    size_t length=strlen(parameter_text);
    if(code==KEY_ENTER || code==KEY_KPENTER || code==KEY_ESC) {
        char *end;
        long value=strtol(parameter_text,&end,10);
        if(code!=KEY_ESC && length && !*end) parameter_commit(parameter_focus,(int)value);
        parameter_focus=-1;
        parameter_text[0]=0;
    } else if(code==KEY_BACKSPACE && length) parameter_text[length-1]=0;
    else if(length+1<sizeof(parameter_text)) {
        char digit=0;
        if(code>=KEY_1 && code<=KEY_0) digit=code==KEY_0?'0':'1'+code-KEY_1;
        const unsigned keypad[]={KEY_KP0,KEY_KP1,KEY_KP2,KEY_KP3,KEY_KP4,KEY_KP5,KEY_KP6,KEY_KP7,KEY_KP8,KEY_KP9};
        for(unsigned i=0;i<10;i++) if(code==keypad[i]) digit='0'+i;
        if(!length && (code==KEY_MINUS || code==KEY_KPMINUS)) digit='-';
        if(digit) { parameter_text[length]=digit; parameter_text[length+1]=0; }
    }
    tone_revision++;
}

struct controls {
    int fd[32], count, x, y, mouse;
    double rescan;
};

static void close_inputs(struct controls *ui) {
    for (int i = 0; i < ui->count; i++) close(ui->fd[i]);
    ui->count = 0;
}

static void open_inputs(struct controls *ui) {
    glob_t paths = {0};
    close_inputs(ui);
    if (!glob("/dev/input/event*", 0, NULL, &paths))
        for (size_t i = 0; i < paths.gl_pathc && ui->count < 32; i++) {
            int fd = open(paths.gl_pathv[i], O_RDONLY | O_NONBLOCK | O_CLOEXEC);
            if (fd >= 0) ui->fd[ui->count++] = fd;
        }
    globfree(&paths);
    ui->rescan = now() + 3;
}

static void handle_input(struct controls *ui) {
    if (now() >= ui->rescan) open_inputs(ui);
    for (int i = 0; i < ui->count; i++) {
        struct input_event input;
        for (int n = 0; n < 128 && read(ui->fd[i], &input, sizeof(input)) == sizeof(input); n++) {
            if (input.type == EV_REL && (input.code == REL_X || input.code == REL_Y)) {
                int *axis = input.code == REL_X ? &ui->x : &ui->y;
                int limit = input.code == REL_X ? WIDTH - 12 : HEIGHT - 16;
                *axis += input.value;
                if (*axis < 0) *axis = 0;
                if (*axis > limit) *axis = limit;
                ui->mouse = 1;
                if(ui_page==1 && parameter_drag>=0 && input.code==REL_X) parameter_move(ui->x);
            }
            if(input.type==EV_KEY && input.code==BTN_LEFT && !input.value && parameter_drag>=0) {
                parameter_commit(parameter_drag,parameter_draft);
                parameter_drag=-1;
            }
            if (input.type != EV_KEY || input.value != 1) continue;
            if (input.code>=KEY_F1 && input.code<=KEY_F7) {
                parameter_focus=parameter_drag=-1;
                ui_page=input.code-KEY_F1;
                continue;
            }
            if(ui_page==1 && parameter_focus>=0 && input.code!=BTN_LEFT) {
                parameter_key(input.code);
                continue;
            }
            if (ui_page==6 && input.code!=BTN_LEFT) {
                cockpit_type(input.code);
                continue;
            }
            if (input.code >= KEY_1 && input.code <= KEY_3) {
                unsigned flag=1u<<(input.code-KEY_1);
                if(advanced_board) config_toggle(flag);
                else atomic_fetch_xor(&requested_mode,flag);
            }
            if(advanced_board && ui_page==1) {
                if(input.code>=KEY_5 && input.code<=KEY_8) config_channel=input.code-KEY_5;
                if(input.code==KEY_LEFT || input.code==KEY_RIGHT)
                    config_level((int)(channel_config()>>8)+(input.code==KEY_LEFT?-4:4));
            }
            if (ui_page==3 && (input.code==KEY_UP || input.code==KEY_LEFT) && ui_event)
                ui_event--;
            if (ui_page==3 && (input.code==KEY_DOWN || input.code==KEY_RIGHT) && ui_event+1<ui_log_count)
                ui_event++;
            if (jpeg_board && ui_page==0 && input.code==KEY_J) jpeg_panel=!jpeg_panel;
            if (input.code != BTN_LEFT) continue;
            if(ui_page==0 && ui->x>=24 && ui->x<158 && ui->y>=172 && ui->y<172+7*52) {
                unsigned row=ui->y-172;
                if(row%52<42) {
                    parameter_focus=parameter_drag=-1;
                    ui_page=row/52;
                }
            } else if (ui->y>=PAGE_Y && ui->y<PAGE_Y+PAGE_H && ui->x>=PAGE_X) {
                unsigned dx=ui->x-PAGE_X;
                if(dx/PAGE_STEP<7 && dx%PAGE_STEP<PAGE_W) {
                    parameter_focus=parameter_drag=-1;
                    ui_page=dx/PAGE_STEP;
                }
            } else if(ui_page>=4) {
                cockpit_click(ui->x,ui->y);
            } else if(ui_page==0 && resolution_board) {
                if(jpeg_board && ui->y>=1012 && ui->x>=830 && ui->x<1040) jpeg_panel=!jpeg_panel;
                else if(jpeg_board && jpeg_panel && ui->x>=1024 && ui->y>=85 && ui->y<554)
                    jpeg_click(ui->x,ui->y);
                else resolution_click(ui->x,ui->y);
            } else if(ui_page==1 && advanced_board) {
                if(parameter_click(ui->x,ui->y)) continue;
                if(threshold_active(channel_config()) && ui->x>=THRESHOLD_AUTO_X &&
                   ui->x<THRESHOLD_AUTO_X+THRESHOLD_AUTO_W && ui->y>=THRESHOLD_AUTO_Y &&
                   ui->y<THRESHOLD_AUTO_Y+THRESHOLD_AUTO_H)
                    threshold_use_auto(config_channel);
                else if(hdr_board && ui->x>=44 && ui->x<449 && ui->y>=951 && ui->y<992)
                    atomic_fetch_xor(&hdr_request,1u<<config_channel);
                else config_click(ui->x,ui->y);
            } else if(ui_page==1 && ui->x>=FILTER_X && ui->x<FILTER_X+FILTER_W &&
                       ui->y>=FILTER_FIRST_Y) {
                unsigned dy=ui->y-FILTER_FIRST_Y;
                if(dy/FILTER_STEP<3 && dy%FILTER_STEP<FILTER_H)
                    atomic_fetch_xor(&requested_mode,1u<<(dy/FILTER_STEP));
            } else if(ui_page==3 && ui->x>=LOG_X && ui->x<LOG_X+LOG_W) {
                if(ui->y>=LOG_Y && ui->y<LOG_Y+LOG_ROWS*LOG_ROW_H) {
                    unsigned row=(ui->y-LOG_Y)/LOG_ROW_H;
                    unsigned target=ui_event/LOG_ROWS*LOG_ROWS+row;
                    if(target<ui_log_count) ui_event=target;
                }
                if(ui->y>=909 && ui->y<948) {
                    if(ui->x<LOG_X+130 && ui_event) ui_event--;
                    if(ui->x>=LOG_X+142 && ui->x<LOG_X+272 && ui_event+1<ui_log_count) ui_event++;
                }
            }
        }
    }
}
