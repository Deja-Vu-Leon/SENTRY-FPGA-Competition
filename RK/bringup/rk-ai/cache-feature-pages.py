from pathlib import Path
r=Path(__file__).parent
p=r/"vid007-feature-pages.h"
s=p.read_text(encoding="utf-8-sig")
s=s.replace("static void ui_panel(struct surface *s,int mode) {","static void ui_draw_panel(struct surface *s,int mode) {")
s+="""
static void ui_panel(struct surface *s,int mode) {
    if(!ui_page) {
        ui_draw_panel(s,mode);
        return;
    }
    static uint32_t canvas[HEIGHT][WIDTH];
    static unsigned last_page=~0u,last_request=~0u,last_event=~0u;
    static int last_mode=-2;
    static double refresh;
    unsigned request=atomic_load(&requested_mode);
    double timestamp=now();
    if(ui_page!=last_page || request!=last_request || mode!=last_mode ||
       ui_event!=last_event || timestamp>=refresh) {
        struct surface panel={.memory=(uint8_t *)canvas,.pitch=sizeof(canvas[0])};
        ui_draw_panel(&panel,mode);
        last_page=ui_page;
        last_request=request;
        last_mode=mode;
        last_event=ui_event;
        refresh=timestamp+1;
    }
    for(unsigned y=68;y<HEIGHT;y++)
        memcpy(s->memory+y*s->pitch,canvas[y],sizeof(canvas[y]));
}
"""
p.write_text(s,encoding="utf-8")
