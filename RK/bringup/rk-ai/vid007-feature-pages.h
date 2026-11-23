#include "vid007-alert-view.h"

static void ui_button(struct surface *s,int x,int y,int w,const wchar_t *label,int chosen) {
    box(s,x,y,w,38,chosen?0x24443a:0x202a2e);
    box(s,x,y+37,w,1,chosen?0xa4f2d0:0x435456);
    rk_label(s,x+14,y+26,label,chosen?0xa4f2d0:0xeef4ef);
}
static void ui_metric(struct surface *s,int x,int y,double number,unsigned digits) {
    wchar_t value[26];
    if(number<0) rk_label(s,x,y,L"—",0x81918c);
    else {
        swprintf(value,26,L"%.*f",(int)digits,number);
        rk_label(s,x,y,value,0xeef4ef);
    }
}
static void ui_draw_panel(struct surface *s,int mode) {
    const uint32_t ink=0xeef4ef, dim=0xaebeb9, mint=0xa4f2d0, amber=0xf6ad76;
    const wchar_t *ports[]={L"A0",L"A1",L"B0",L"B1"};
    if(ui_page==0) {
        box(s,1120,18,532,38,0x1c282a);
        wchar_t label[90];
        swprintf(label,90,L"PCIe   %.2f MB/s   /   %ls",atomic_load(&ui_mbps_x100)/100.0,
                 mode<0?L"切换中":mode&4?L"Sobel 1-bit":L"Bayer8");
        rk_label(s,1136,44,label,mint);
        box(s,0,1013,WIDTH,37,0x101719);
        rk_label(s,23,1038,L"四路固定 1920 × 1080    |    JPEG 编码、码率滑块、无损模式、逐路分辨率和 HDR 需四路 FPGA 固件支持",dim);
        return;
    }
    box(s,0,68,WIDTH,HEIGHT-68,0x101719);
    if(ui_page==1) {
        rk_label(s,38,128,L"FPGA 图像预处理",mint);
        rk_label(s,38,174,L"当前硬件对四路应用同一组设置",dim);
        const wchar_t *filters[]={L"1   灰度化",L"2   高斯滤波",L"3   Sobel 边缘提取"};
        for(unsigned i=0;i<3;i++) ui_button(s,38+i*250,211,226,filters[i],(atomic_load(&requested_mode)>>i)&1);
        rk_label(s,38,320,L"通道状态",mint);
        for(unsigned i=0;i<4;i++) {
            int x=38+i*306;
            box(s,x,353,290,138,0x1c282a);
            rk_label(s,x+18,394,ports[i],mint);
            rk_label(s,x+18,448,mode<0?L"切换中":mode&4?L"Sobel 边缘图":mode?L"FPGA 预处理":L"彩色原画",ink);
        }
        rk_label(s,38,566,L"需要扩展四路固件",amber);
        rk_label(s,38,614,L"逐路算法选择、参数滑块、直方图均化、阈值分割、形态学、亚像素测量",dim);
        rk_label(s,38,658,L"HDR、CLAHE、去雾",dim);
        return;
    }
    if(ui_page==2) {
        wchar_t uptime[80];
        unsigned seconds=(unsigned)(now()-ui_started);
        swprintf(uptime,80,L"运行 %02u:%02u:%02u    |    PCIe %.2f MB/s",seconds/3600,(seconds/60)%60,seconds%60,
                 atomic_load(&ui_mbps_x100)/100.0);
        rk_label(s,38,113,L"链路诊断",mint);
        rk_label(s,1125,113,uptime,ink);
        const wchar_t *labels[]={
            L"完整帧捕获 FPS（传感器端）",L"FPGA 交付 FPS（RK 校验通过）",L"送入显示管线 FPS",L"HDMI 渲染 FPS",
            L"HDMI 帧间隔 P95 / ms",L"转换前队列拥塞事件",L"送显前队列拥塞事件",L"送显队列当前帧数 / 容量",
            L"显示提交至 DRM 完成 P50 / ms",L"显示提交至 DRM 完成 P95 / ms",L"送显源帧号跳帧 / 最近 5 秒",
            L"已解码帧",L"解码队列丢帧",L"显示前队列丢帧",L"最近接收帧号（Sobel 为输出序号）",L"严格 JPEG 拒绝",
            L"采集丢帧累计",L"JPEG 解码耗时 P95 / ms",L"排队等待 P95 / ms",L"解码队列深度",
            L"AXI 写错误",L"RK 接收完整帧累计",L"RK 拒收帧累计"
        };
        box(s,38,136,1604,36,0x244039);
        rk_label(s,52,161,L"指标",mint);
        for(unsigned ch=0;ch<4;ch++) rk_label(s,690+236*ch,161,ports[ch],mint);
        for(unsigned row=0;row<sizeof(labels)/sizeof(*labels);row++) {
            int y=172+row*30;
            box(s,38,y,1604,29,row%2?0x151e21:0x1c282a);
            rk_label(s,52,y+23,labels[row],ink);
            for(unsigned ch=0;ch<4;ch++) {
                const struct ui_channel *a=&ui_stats[ch];
                double values[]={-1,atomic_load(&ui_rx_fps_x100[ch])/100.,a->submit_fps,a->hdmi_fps,
                    a->interval95,(double)a->drops,-1,-1,a->latency50,a->latency95,(double)a->skips,
                    -1,-1,(double)a->drops,(double)atomic_load(&ui_source_id[ch]),-1,-1,-1,a->wait95,
                    -1,-1,(double)atomic_load(&ui_rx_total[ch]),(double)atomic_load(&ui_bad_total[ch])};
                if(row==7) {
                    wchar_t queue[20];
                    swprintf(queue,20,L"%u / %u",a->depth,DEPTH);
                    rk_label(s,690+236*ch,y+23,queue,ink);
                } else ui_metric(s,690+236*ch,y+23,values[row],row==1||row==2||row==3||
                                 row==4||row==8||row==9||row==18?2:0);
            }
        }
        rk_label(s,40,890,L"— 表示当前数据通路未提供对应指标。帧号跳跃含 FPGA 主动抽帧。",dim);
        rk_label(s,40,935,L"实时画面",mint);
        for(unsigned ch=0;ch<4;ch++) rk_label(s,280+335*ch,924,ports[ch],mint);
        return;
    }
    rk_label(s,38,124,L"检测告警日志",mint);
    rk_label(s,38,166,L"最近 24 条高风险车辆事件",dim);
    if(!ui_alert_count) {
        rk_label(s,38,265,L"暂无告警记录",ink);
        return;
    }
    ui_button(s,38,203,130,L"上一条",0);
    ui_button(s,180,203,130,L"下一条",0);
    struct ui_alert *event=&ui_alerts[ui_event];
    wchar_t summary[96];
    swprintf(summary,96,L"%hs    %hs    置信率 %u%%",event->port,event->when,event->confidence);
    rk_label(s,38,291,summary,ink);
    rk_label(s,38,337,event->reason==1?L"距离过近":event->reason==2?L"快速接近":L"高风险车辆",amber);
    wchar_t position[36];
    swprintf(position,36,L"%u / %u",ui_event+1,ui_alert_count);
    rk_label(s,334,228,position,dim);
    if(ui_photo_ready) {
        box(s,38,375,844,476,0x354545);
        for(unsigned y=0;y<472;y++) {
            uint32_t *line=(uint32_t *)(s->memory+(377+y)*s->pitch)+40;
            for(unsigned x=0;x<840;x++) line[x]=ui_photo[(y/2)*420+x/2];
        }
    } else rk_label(s,38,414,L"告警图片无法读取",amber);
}


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
