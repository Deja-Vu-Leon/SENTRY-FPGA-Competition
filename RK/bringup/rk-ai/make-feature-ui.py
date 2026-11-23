from pathlib import Path

root=Path(__file__).resolve().parent
def read(name):
    return (root/name).read_text(encoding="utf-8-sig")
def edit(source,old,new):
    if source.count(old)!=1:
        raise ValueError(old)
    return source.replace(old,new)
def save(name,source):
    (root/name).write_text(source,encoding="utf-8")
s=read("vid007-rk-controls.h")
a=s.index("            if (input.code == BTN_LEFT")
b=s.index("\n        }",a)
s=s[:a]+"""            if (input.code>=KEY_F1 && input.code<=KEY_F4)
                ui_page=input.code-KEY_F1;
            if (input.code != BTN_LEFT) continue;
            if (ui->y>=PAGE_Y && ui->y<PAGE_Y+PAGE_H && ui->x>=PAGE_X) {
                unsigned dx=ui->x-PAGE_X;
                if(dx/PAGE_STEP<4 && dx%PAGE_STEP<PAGE_W) ui_page=dx/PAGE_STEP;
            } else if(ui_page==1 && ui->y>=211 && ui->y<249 && ui->x>=38) {
                unsigned dx=ui->x-38;
                if(dx/250<3 && dx%250<226) atomic_fetch_xor(&requested_mode,1u<<(dx/250));
            } else if(ui_page==3 && ui->y>=203 && ui->y<241) {
                if(ui->x>=38 && ui->x<168 && ui_event) ui_event--;
                if(ui->x>=180 && ui->x<310 && ui_event<23) ui_event++;
            }"""+s[b:]
save("vid007-feature-controls.h",s)
s=read("vid007-rk-chrome.h")
a=s.index("        const wchar_t *labels[]")
b=s.index("        const wchar_t *ports[]",a)
s=s[:a]+"""        const wchar_t *pages[]={L"F1  图像传输",L"F2  FPGA 预处理",L"F3  链路诊断",L"F4  检测日志"};
        for(unsigned i=0;i<4;i++) {
            int x=PAGE_X+i*PAGE_STEP;
            box(&bar,x,PAGE_Y,PAGE_W,PAGE_H,i==ui_page?0x24443a:0x202a2e);
            box(&bar,x,PAGE_Y+PAGE_H-2,PAGE_W,2,i==ui_page?mint:0x435456);
            rk_label(&bar,x+12,43,pages[i],i==ui_page?mint:ink);
        }
        wchar_t status[48];
        swprintf(status,48,L"%u / 4 路有信号",4-(unsigned)__builtin_popcount(offline&15));
        if(ui_page) rk_label(&bar,1390,43,mode<0?L"等待画面":status,mode<0?amber:mint);
"""+s[b:]
s=edit(s,'rk_label(&bar,191,40,L"四路视觉监控",ink);','rk_label(&bar,191,40,L"RK 监控",ink);')
s=edit(s,'    static int last_mode=-2;','    static int last_mode=-2;\n    static unsigned last_page=~0u;')
s=edit(s,'if (mode!=last_mode || request!=last_request','if (ui_page!=last_page || mode!=last_mode || request!=last_request')
s=edit(s,'        last_mode=mode;','        last_mode=mode;\n        last_page=ui_page;')
s=edit(s,'    for (unsigned ch=0;ch<4;ch++) {','    if(ui_page) return;\n    for (unsigned ch=0;ch<4;ch++) {')
save("vid007-feature-chrome.h",s)
s=read("vid007-rk-kms.h")
s=edit(s,"struct display_frame { uint32_t id; uint8_t data[PIXELS]; };","struct display_frame { uint32_t id; double received; uint8_t data[PIXELS]; };")
s=edit(s,"    queues[channel].frames[position].id = id;","    queues[channel].frames[position].id = id;\n    queues[channel].frames[position].received = now();")
s=edit(s,'#include "vid007-rk-controls.h"\n#include "vid007-rk-chrome.h"','#include "vid007-feature-state.h"\n#include "vid007-feature-controls.h"\n#include "vid007-feature-chrome.h"\n#include "vid007-feature-pages.h"')
s=edit(s,"    uint64_t flips, shown[4];","""    uint64_t flips, shown[4], submitted_count[4], skipped[4];
    uint32_t source_id[4], previous_id[4];
    unsigned have_id[4], mode;
    double submitted_at, last[4];
    struct ui_times intervals[4], latency[4], waits[4];""")
s=edit(s,"    for (unsigned i=0; i<4; i++) flip->shown[i] += (flip->fresh >> i) & 1;","""    const double displayed=now();
    for (unsigned i=0; i<4; i++) if((flip->fresh>>i)&1) {
        flip->shown[i]++;
        if(flip->last[i]) ui_sample(&flip->intervals[i],1000*(displayed-flip->last[i]));
        flip->last[i]=displayed;
        ui_sample(&flip->latency[i],1000*(displayed-flip->submitted_at));
        if(flip->have_id[i]) {
            unsigned delta=flip->mode&4 ? flip->source_id[i]-flip->previous_id[i] :
                                         (uint16_t)(flip->source_id[i]-flip->previous_id[i]);
            if(delta>0 && delta<4096) flip->skipped[i]+=delta-1;
        }
        flip->previous_id[i]=flip->source_id[i];
        flip->have_id[i]=1;
    }""")
s=edit(s,"    double start=now();","""    double start=now();
    ui_started=start;
    for(unsigned ch=0;ch<4;ch++)
        ui_stats[ch].interval95=ui_stats[ch].latency50=ui_stats[ch].latency95=ui_stats[ch].wait95=-1;
    double alert_refresh=0;
    unsigned previous_event=~0u;""")
s=edit(s,"                old_mode = active;","""                old_mode = active;
                memset(flip.have_id,0,sizeof(flip.have_id));
                memset(flip.last,0,sizeof(flip.last));""")
s=edit(s,"                    memcpy(raw,queues[ch].frames[queues[ch].head].data,payload_size(active));","""                    const struct display_frame *frame=&queues[ch].frames[queues[ch].head];
                    flip.source_id[ch]=frame->id;
                    ui_sample(&flip.waits[ch],1000*(frame_time-frame->received));
                    memcpy(raw,frame->data,payload_size(active));""")
s=edit(s,"            for (unsigned ch=0; ch<4; ch++) {\n                const unsigned x=(ch%2)*TILE_W, y0=68+(ch/2)*TILE_H;","            if(!ui_page) for (unsigned ch=0; ch<4; ch++) {\n                const unsigned x=(ch%2)*TILE_W, y0=68+(ch/2)*TILE_H;")
s=edit(s,"            if (active == 0) for","            if (!ui_page && active == 0) for")
s=edit(s,"            rk_chrome(s, fps, active, offline);","""            if(ui_page==3 && (frame_time>=alert_refresh || previous_event!=ui_event)) {
                ui_load_alerts();
                previous_event=ui_event;
                alert_refresh=frame_time+2;
            }
            rk_chrome(s, fps, active, offline);
            ui_panel(s,active);
            if(ui_page==2) {
                for(unsigned ch=0;ch<4;ch++)
                    for(unsigned y=0;y<115;y++) {
                        uint32_t *line=(uint32_t *)(s->memory+(930+y)*s->pitch)+280+335*ch;
                        for(unsigned x=0;x<205;x++)
                            line[x]=tiles[ch][(y*TILE_H/115)*TILE_W+x*TILE_W/205];
                    }
            } else if(ui_page) fresh=0;""")
s=edit(s,"                if (offline & (1u << ch))\n                    rk_label","                if (!ui_page && (offline & (1u << ch)))\n                    rk_label")
s=edit(s,"            flip.fresh=fresh;","""            flip.fresh=fresh;
            if(active>=0) flip.mode=active;
            flip.submitted_at=now();
            for(unsigned ch=0;ch<4;ch++) flip.submitted_count[ch]+=(fresh>>ch)&1;""")
s=edit(s,"                fps[ch] = (unsigned)(flip.shown[ch] / elapsed + 0.5);","""                struct ui_channel *a=&ui_stats[ch];
                a->depth=queues[ch].queued;
                a->drops=queues[ch].overrun;
                a->submit_fps=flip.submitted_count[ch]/elapsed;
                a->hdmi_fps=flip.shown[ch]/elapsed;
                a->skips=flip.skipped[ch];
                a->interval95=ui_percentile(&flip.intervals[ch],95);
                a->latency50=ui_percentile(&flip.latency[ch],50);
                a->latency95=ui_percentile(&flip.latency[ch],95);
                a->wait95=ui_percentile(&flip.waits[ch],95);
                flip.intervals[ch].count=flip.intervals[ch].next=0;
                flip.latency[ch].count=flip.latency[ch].next=0;
                flip.waits[ch].count=flip.waits[ch].next=0;
                flip.submitted_count[ch]=flip.skipped[ch]=0;
                fps[ch] = (unsigned)(flip.shown[ch] / elapsed + 0.5);""")
save("vid007-feature-kms.h",s)
s=read("vid007-rk-preview.c")
s=edit(s,'#include "vid007-rk-kms.h"','#include "vid007-feature-kms.h"')
s=edit(s,"            present_frame(channel, id);","""#ifdef KMS
            atomic_store(&ui_source_id[channel],id);
            atomic_fetch_add(&ui_rx_total[channel],1);
#endif
            present_frame(channel, id);""")

s=edit(s,"            printf(\"DMA %.2f MB/s mode=%u bad_packets=", """#ifdef KMS
            atomic_store(&ui_mbps_x100,(unsigned)(bytes/elapsed/10000.));
#endif
            printf("DMA %.2f MB/s mode=%u bad_packets=""")
s=edit(s,"                totals[i] = cam->complete;","""#ifdef KMS
                atomic_store(&ui_rx_fps_x100[i],(unsigned)((cam->complete-totals[i])*100/elapsed));
#endif
                totals[i] = cam->complete;""")
s=s.replace("cam->bad++;","""cam->bad++;
#if defined(HDMI) && defined(KMS)
            atomic_fetch_add(&ui_bad_total[channel],1);
#endif""")
save("vid007-feature-preview.c",s)
