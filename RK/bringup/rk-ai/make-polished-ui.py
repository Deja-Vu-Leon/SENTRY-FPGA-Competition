"""Build the native HDMI UI variant from the existing RK video pipeline."""
from pathlib import Path

root = Path(__file__).resolve().parent
def read(name):
    return (root / name).read_text(encoding="utf-8-sig")

def write(name, text):
    (root / name).write_text(text, encoding="utf-8", newline="\n")

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source location for {old!r}")
    return text.replace(old, new)

controls = read("vid007-feature-controls.h")
controls = replace_once(controls, "enum { BUTTON_W = 150, BUTTON_STEP = 162, BUTTON_X = 390, BUTTON_Y = 19 };",
                        """enum { FILTER_X=44, FILTER_W=405, FILTER_FIRST_Y=226, FILTER_STEP=79, FILTER_H=66,
       LOG_X=1044, LOG_Y=263, LOG_ROW_H=56, LOG_ROWS=11, LOG_W=590 };""")
controls = replace_once(controls, "            if (input.code != BTN_LEFT) continue;", """            if (ui_page==3 && (input.code==KEY_UP || input.code==KEY_LEFT) && ui_event)
                ui_event--;
            if (ui_page==3 && (input.code==KEY_DOWN || input.code==KEY_RIGHT) && ui_event+1<ui_log_count)
                ui_event++;
            if (input.code != BTN_LEFT) continue;""")
start = controls.index("            } else if(ui_page==1")
end = controls.index("\n        }", start)
controls = controls[:start] + """            } else if(ui_page==1 && ui->x>=FILTER_X && ui->x<FILTER_X+FILTER_W &&
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
            }""" + controls[end:]
write("vid007-polished-controls.h", controls)

alerts = read("vid007-alert-view.h").replace("ui_alert_count","ui_log_count")
alerts = replace_once(alerts,"static unsigned ui_log_count;\n","")
alerts = replace_once(alerts,"static void ui_load_alerts(void) {","""static void ui_load_alerts(int preserve) {
    char selected[48]={0};
    if(preserve && ui_event<ui_log_count)
        memcpy(selected,ui_alerts[ui_event].file,sizeof(selected));""")
alerts = replace_once(alerts,"    if(ui_event>=ui_log_count) ui_event=ui_log_count-1;","""    if(selected[0]) for(unsigned i=0;i<ui_log_count;i++)
        if(!strcmp(selected,ui_alerts[i].file)) { ui_event=i; break; }
    if(ui_event>=ui_log_count) ui_event=ui_log_count-1;""")
write("vid007-polished-alerts.h",alerts)
state=read("vid007-feature-state.h")
write("vid007-polished-state.h",replace_once(state,"static unsigned ui_page, ui_event;",
                                             "static unsigned ui_page, ui_event, ui_log_count;"))

source = read("vid007-feature-kms.h")
for name in ("state","controls","pages"):
    source=replace_once(source,f'"vid007-feature-{name}.h"',f'"vid007-polished-{name}.h"')
source = replace_once(source,"                ui_load_alerts();",
                       "                ui_load_alerts(previous_event==ui_event);")
start = source.index("            if(ui_page==2) {")
end = source.index("\n            for (unsigned ch = 0;",start)
source=source[:start]+"""            if(ui_page==3) fresh=0;"""+source[end:]
source = replace_once(source,"            ui_panel(s,active);",
                      "            ui_panel(s,active,tiles,offline);")
source = replace_once(source, """                pthread_mutex_unlock(&queues[ch].mutex);
                struct ui_channel *a=&ui_stats[ch];
                a->depth=queues[ch].queued;
                a->drops=queues[ch].overrun;""", """                struct ui_channel *a=&ui_stats[ch];
                a->depth=queues[ch].queued;
                a->drops=queues[ch].overrun;
                pthread_mutex_unlock(&queues[ch].mutex);""")
write("vid007-polished-kms.h",source)
write("vid007-polished-preview.c",replace_once(read("vid007-feature-preview.c"),
                                                '"vid007-feature-kms.h"','"vid007-polished-kms.h"'))
write("start-rk-polished.sh",replace_once(read("start-rk-features.sh"),
                                          "./rk-ai/vid007-feature-preview","./rk-ai/vid007-polished-preview"))
