#include <glob.h>
#include <linux/input.h>
#include <ft2build.h>
#include FT_FREETYPE_H

enum { FILTER_X=44, FILTER_W=405, FILTER_FIRST_Y=226, FILTER_STEP=79, FILTER_H=66,
       LOG_X=1044, LOG_Y=263, LOG_ROW_H=56, LOG_ROWS=11, LOG_W=590 };
static atomic_uint requested_mode;
static atomic_int published_mode;
static FT_Library font_library;
static FT_Face font;

static void box(struct surface *s, int x, int y, int w, int h, uint32_t color) {
    for (int row = y; row < y + h; row++) {
        uint32_t *line = (uint32_t *)(s->memory + row * s->pitch);
        for (int col = x; col < x + w; col++) line[col] = color;
    }
}

static void text_at(struct surface *s, int x, int baseline, const char *label) {
    if (!font) return;
    for (; *label; label++) {
        if (FT_Load_Char(font, (unsigned char)*label, FT_LOAD_RENDER)) continue;
        FT_GlyphSlot glyph = font->glyph;
        for (unsigned y = 0; y < glyph->bitmap.rows; y++)
            for (unsigned col = 0; col < glyph->bitmap.width; col++) {
                int dx = x + glyph->bitmap_left + col;
                int dy = baseline - glyph->bitmap_top + y;
                if (dx < 0 || dx >= WIDTH || dy < 0 || dy >= HEIGHT) continue;
                unsigned value = glyph->bitmap.buffer[y * glyph->bitmap.pitch + col];
                if (value > 80) {
                    uint32_t *line = (uint32_t *)(s->memory + dy * s->pitch);
                    line[dx] = 0xf1f5f9;
                }
            }
        x += glyph->advance.x >> 6;
    }
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
            }
            if (input.type != EV_KEY || input.value != 1) continue;
            if (input.code >= KEY_1 && input.code <= KEY_3)
                atomic_fetch_xor(&requested_mode, 1u << (input.code - KEY_1));
            if (input.code>=KEY_F1 && input.code<=KEY_F4)
                ui_page=input.code-KEY_F1;
            if (ui_page==3 && (input.code==KEY_UP || input.code==KEY_LEFT) && ui_event)
                ui_event--;
            if (ui_page==3 && (input.code==KEY_DOWN || input.code==KEY_RIGHT) && ui_event+1<ui_log_count)
                ui_event++;
            if (input.code != BTN_LEFT) continue;
            if (ui->y>=PAGE_Y && ui->y<PAGE_Y+PAGE_H && ui->x>=PAGE_X) {
                unsigned dx=ui->x-PAGE_X;
                if(dx/PAGE_STEP<4 && dx%PAGE_STEP<PAGE_W) ui_page=dx/PAGE_STEP;
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
