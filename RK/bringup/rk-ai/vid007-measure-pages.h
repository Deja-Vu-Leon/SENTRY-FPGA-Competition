#include "vid007-polished-alerts.h"

static const uint32_t panel_bg=0x101719, panel_surface=0x172123, panel_alt=0x1b282a;
static const uint32_t panel_edge=0x334143, panel_text=0xeef4ef, panel_dim=0xaebeb9;
static const uint32_t panel_mint=0xa4f2d0, panel_amber=0xf6ad76;
static const wchar_t *const panel_ports[]={L"A0",L"A1",L"B0",L"B1"};

static void panel_title(struct surface *s,int x,int y,const wchar_t *name) {
    if(font) FT_Set_Pixel_Sizes(font,0,32);
    if(cjk_font) FT_Set_Pixel_Sizes(cjk_font,0,30);
    rk_label(s,x,y,name,panel_text);
    if(font) FT_Set_Pixel_Sizes(font,0,21);
    if(cjk_font) FT_Set_Pixel_Sizes(cjk_font,0,18);
}

static void panel_button(struct surface *s,int x,int y,int w,const wchar_t *name,int enabled) {
    box(s,x,y,w,39,panel_alt);
    box(s,x,y+38,w,1,panel_edge);
    rk_label(s,x+12,y+27,name,enabled?panel_text:0x788986);
}

static unsigned log_first(void) {
    return ui_event/LOG_ROWS*LOG_ROWS;
}

static const wchar_t *alert_reason(int reason) {
    if(reason==1) return L"距离过近";
    if(reason==2) return L"快速接近";
    return L"高风险车辆";
}

static void panel_filters(struct surface *s,int mode) {
    if(advanced_board) {
        panel_title(s,44,128,L"FPGA 图像预处理");
        const unsigned config=channel_config();
        unsigned selected_operation=(config>>4)&7;
        if(selected_operation==7 && (config&0x8000u)) selected_operation=8;
        const unsigned on_board=atomic_load(&live_config[config_channel]);
        for(unsigned ch=0;ch<4;ch++) {
            int x=CHANNEL_X+ch*CHANNEL_STEP;
            box(s,x,CHANNEL_Y,CHANNEL_W,CHANNEL_H,ch==config_channel?0x234037:panel_surface);
            rk_label(s,x+14,CHANNEL_Y+27,panel_ports[ch],ch==config_channel?panel_mint:panel_dim);
        }
        rk_label(s,44,215,L"基础处理",panel_mint);
        const wchar_t *filters[]={L"1  灰度化",L"2  高斯滤波",L"3  Sobel 边缘提取"};
        for(unsigned i=0;i<3;i++) {
            int y=FILTER_FIRST_Y+i*FILTER_STEP;
            int on=(config>>i)&1;
            box(s,FILTER_X,y,FILTER_W,FILTER_H,on?0x203930:panel_surface);
            box(s,FILTER_X,y,3,FILTER_H,on?panel_mint:panel_edge);
            rk_label(s,FILTER_X+17,y+40,filters[i],panel_text);
            rk_label(s,FILTER_X+344,y+40,on?L"开":L"关",on?panel_mint:panel_dim);
        }
        rk_label(s,44,539,L"附加处理",panel_mint);
        const wchar_t *ops[]={L"关闭",L"直方图均化",L"阈值分割",L"形态学膨胀",
                              L"形态学腐蚀",L"单曝光色调映射",L"固定去雾",L"CLAHE",L"亚像素测量"};
        for(unsigned i=0;i<(measurement_board?9u:7u);i++) {
            int x=OP_X+(i%2)*(OP_W+15),y=OP_Y+(i/2)*OP_STEP;
            box(s,x,y,OP_W,OP_H,i==selected_operation?0x234037:panel_surface);
            rk_label(s,x+11,y+26,ops[i],i==selected_operation?panel_mint:panel_dim);
        }
        if((config&4)||selected_operation==2||selected_operation==5||selected_operation>=6) {
            wchar_t label[40];
            unsigned max=selected_operation>=7?127:255;
            unsigned level=(config>>8)&max;
            swprintf(label,40,L"%ls  %u",selected_operation==5?L"提亮上限":
                     selected_operation==6?L"去雾强度":selected_operation==7?L"限幅强度":L"阈值",level);
            rk_label(s,44,819,label,panel_text);
            box(s,LEVEL_X,LEVEL_Y,LEVEL_W,4,panel_edge);
            box(s,LEVEL_X,LEVEL_Y,level*LEVEL_W/max,4,panel_mint);
            box(s,LEVEL_X+level*LEVEL_W/max-5,LEVEL_Y-5,10,14,panel_mint);
        }
        rk_label(s,44,893,mode<0||config!=on_board?L"正在应用":L"参数已应用",
                 mode<0||config!=on_board?panel_amber:panel_mint);
        if(selected_operation==8) {
            uint32_t result=atomic_load(&subpixel_result[config_channel]);
            wchar_t position[48];
            if(result>>31) swprintf(position,48,L"边缘  X %.4f   Y %u px",(result&32767u)/16.,(result>>15)&2047u);
            else swprintf(position,48,L"中央区域未测到有效边缘");
            rk_label(s,44,931,position,panel_text);
        }
    } else {
    panel_title(s,44,133,L"FPGA 图像预处理");
    rk_label(s,44,173,L"四路共用一组 FPGA 设置",panel_dim);
    rk_label(s,44,209,L"处理链",panel_mint);
    const wchar_t *filters[]={L"1  灰度化",L"2  高斯滤波",L"3  Sobel 边缘提取"};
    const unsigned request=atomic_load(&requested_mode);
    for(unsigned i=0;i<3;i++) {
        int y=FILTER_FIRST_Y+i*FILTER_STEP;
        int on=(request>>i)&1;
        box(s,FILTER_X,y,FILTER_W,FILTER_H,on?0x203930:panel_surface);
        box(s,FILTER_X,y,3,FILTER_H,on?panel_mint:panel_edge);
        rk_label(s,FILTER_X+17,y+40,filters[i],panel_text);
        box(s,FILTER_X+319,y+17,66,32,on?0x33594b:0x243133);
        rk_label(s,FILTER_X+343,y+39,on?L"开":L"关",on?panel_mint:panel_dim);
    }
    box(s,44,489,405,1,panel_edge);
    rk_label(s,44,538,L"当前输出",panel_mint);
    rk_label(s,44,575,mode<0?L"切换中":mode&4?L"Sobel 边缘图":mode?L"FPGA 预处理":L"彩色原画",
             mode<0?panel_amber:panel_text);
    rk_label(s,44,617,mode==0?L"NPU 识别开启":L"当前模式暂停 NPU 识别",panel_dim);
    box(s,44,651,405,1,panel_edge);
    rk_label(s,44,700,L"待固件支持",panel_amber);
    rk_label(s,44,737,L"逐路选择、算法参数",panel_dim);
    rk_label(s,44,776,L"均化、阈值分割、形态学、亚像素",panel_dim);
    rk_label(s,44,815,L"HDR、CLAHE、去雾",panel_dim);

    }
    box(s,489,106,1,811,panel_edge);
    rk_label(s,521,140,L"处理结果",panel_mint);
    for(unsigned ch=0;ch<4;ch++) {
        int x=521+ch%2*555, y=164+ch/2*359;
        box(s,x,y,524,328,panel_surface);
        if(resolution_board) {
            const wchar_t *const size[]={L"1920×1080",L"960×540",L"480×270"};
            unsigned scale=resolution(atomic_load(&live_config[ch]));
            rk_label(s,x+380,y+318,size[scale],panel_dim);
        }
        rk_label(s,x+14,y+318,panel_ports[ch],panel_mint);
        rk_label(s,x+70,y+318,ch<2?L"车辆识别 · 测距":L"行人识别",panel_dim);
    }
}

enum metric_value { NA, RX_FPS, SUBMIT_FPS, HDMI_FPS, INTERVAL, DROP, QUEUE,
                    LATENCY50, LATENCY95, SKIP, FRAME_ID, WAIT, TOTAL, REJECT, SENSOR, SENSOR_BAD, AXI };

static void panel_diag(struct surface *s) {
    panel_title(s,44,128,L"链路诊断");
    wchar_t summary[85];
    unsigned elapsed=(unsigned)(now()-ui_started);
    swprintf(summary,85,L"运行 %02u:%02u:%02u     PCIe %.2f MB/s",
             elapsed/3600,elapsed/60%60,elapsed%60,atomic_load(&ui_mbps_x100)/100.);
    rk_label(s,1115,123,summary,panel_mint);
    box(s,44,151,1592,37,0x223733);
    rk_label(s,59,176,L"测量阶段",panel_mint);
    for(unsigned ch=0;ch<4;ch++) rk_label(s,710+223*ch,176,panel_ports[ch],panel_mint);
    const struct {const wchar_t *name; enum metric_value value;} rows[]={
        {L"采集与接收",NA},
        {L"传感器完整帧捕获 / fps",SENSOR},
        {L"FPGA 交付 · RK 校验通过 / fps",RX_FPS},
        {L"最近接收帧号",FRAME_ID},
        {L"RK 接收完整帧累计",TOTAL},
        {L"RK 拒收帧累计",REJECT},
        {L"传感器拒收帧累计",SENSOR_BAD},
        {L"AXI 写错误",AXI},
        {L"队列与显示",NA},
        {L"转换前队列拥塞与丢帧累计",DROP},
        {L"转换前队列深度 / 容量",QUEUE},
        {L"独立送显队列拥塞与丢帧",NA},
        {L"转换前排队等待 P95 / ms",WAIT},
        {L"提交显示 / fps",SUBMIT_FPS},
        {L"HDMI 实际呈现 / fps",HDMI_FPS},
        {L"HDMI 帧间隔 P95 / ms",INTERVAL},
        {L"提交至 DRM 完成 P50 / ms",LATENCY50},
        {L"提交至 DRM 完成 P95 / ms",LATENCY95},
        {L"送显帧号跳跃 / 最近 5 秒",SKIP},
        {L"JPEG 解码",NA},
        {L"已解码帧 / 严格 JPEG 拒绝",NA},
        {L"解码队列深度 / 丢帧",NA},
        {L"解码耗时 P95 / ms",NA}
    };
    for(unsigned i=0;i<sizeof(rows)/sizeof(*rows);i++) {
        int y=188+29*i;
        int group=i==0||i==8||i==19;
        box(s,44,y,1592,28,group?0x23302f:i%2?panel_surface:panel_alt);
        rk_label(s,59,y+21,rows[i].name,group?panel_mint:panel_text);
        if(group) continue;
        for(unsigned ch=0;ch<4;ch++) {
            const struct ui_channel *a=&ui_stats[ch];
            const double values[]={ [NA]=-1, [RX_FPS]=atomic_load(&ui_rx_fps_x100[ch])/100.,
                [SUBMIT_FPS]=a->submit_fps,[HDMI_FPS]=a->hdmi_fps,[INTERVAL]=a->interval95,
                [DROP]=a->drops,[LATENCY50]=a->latency50,[LATENCY95]=a->latency95,
                [SKIP]=a->skips,[FRAME_ID]=atomic_load(&ui_source_id[ch]),[WAIT]=a->wait95,
                [TOTAL]=atomic_load(&ui_rx_total[ch]),[REJECT]=atomic_load(&ui_bad_total[ch]),
                [SENSOR]=advanced_board?atomic_load(&capture_fps[ch])/100.:-1,
                [SENSOR_BAD]=advanced_board?(double)atomic_load(&capture_bad[ch]):-1,
                [AXI]=advanced_board?(double)atomic_load(&axi_write_errors[ch]):-1 };
            enum metric_value id=rows[i].value;
            int x=710+223*ch;
            wchar_t value[32];
            uint32_t color=panel_text;
            if(id==QUEUE) {
                swprintf(value,32,L"%u / %u",a->depth,DEPTH);
                if(a->depth>=DEPTH-1) color=panel_amber;
            } else if(values[id]<0) {
                swprintf(value,32,L"—");
                color=0x849590;
            } else {
                int digits=(id==SENSOR||id==RX_FPS||id==SUBMIT_FPS||id==HDMI_FPS||id==INTERVAL||
                            id==LATENCY50||id==LATENCY95||id==WAIT)?2:0;
                swprintf(value,32,L"%.*f",digits,values[id]);
                if(id==RX_FPS||id==HDMI_FPS) color=panel_mint;
            }
            rk_label(s,x,y+21,value,color);
        }
    }
    rk_label(s,44,887,L"—  未提供测量值    |    帧号跳跃包含 FPGA 主动抽帧。",panel_dim);
    rk_label(s,44,938,L"实时画面",panel_mint);
    for(unsigned ch=0;ch<4;ch++) rk_label(s,266+335*ch,920,panel_ports[ch],panel_mint);
}

static void panel_log(struct surface *s) {
    panel_title(s,44,132,L"检测日志");
    wchar_t count[48];
    swprintf(count,48,L"最近 %u 条高风险车辆告警",ui_log_count);
    rk_label(s,44,175,count,panel_dim);
    rk_label(s,44,236,L"告警留图",panel_mint);
    rk_label(s,LOG_X,236,L"事件列表",panel_mint);
    box(s,44,263,960,540,0x141d20);
    box(s,44,803,960,1,panel_edge);
    box(s,LOG_X,LOG_Y,LOG_W,LOG_ROW_H*LOG_ROWS,panel_surface);
    if(!ui_log_count) {
        rk_label(s,389,533,L"暂无告警留图",panel_dim);
        rk_label(s,LOG_X+20,LOG_Y+47,L"暂无告警记录",panel_dim);
        return;
    }
    const struct ui_alert *a=&ui_alerts[ui_event];
    if(ui_photo_ready) {
        for(unsigned y=0;y<536;y++) {
            uint32_t *line=(uint32_t *)(s->memory+(265+y)*s->pitch)+46;
            for(unsigned x=0;x<956;x++)
                line[x]=ui_photo[(y*236/536)*420+x*420/956];
        }
    } else rk_label(s,408,533,L"告警图片无法读取",panel_amber);
    wchar_t detail[96];
    swprintf(detail,96,L"%hs    %hs    置信率 %u%%",a->port,a->when,a->confidence);
    rk_label(s,44,863,alert_reason(a->reason),panel_amber);
    rk_label(s,44,909,detail,panel_text);
    for(unsigned i=log_first();i<ui_log_count && i<log_first()+LOG_ROWS;i++) {
        const struct ui_alert *row=&ui_alerts[i];
        int y=LOG_Y+(i-log_first())*LOG_ROW_H;
        int active=i==ui_event;
        box(s,LOG_X,y,LOG_W,LOG_ROW_H-1,active?0x234037:panel_alt);
        if(active) box(s,LOG_X,y,3,LOG_ROW_H-1,panel_mint);
        swprintf(detail,96,L"%hs   %ls",row->port,alert_reason(row->reason));
        rk_label(s,LOG_X+16,y+34,detail,active?panel_mint:panel_text);
        swprintf(detail,96,L"%hs    %u%%",row->when,row->confidence);
        rk_label(s,LOG_X+290,y+34,detail,panel_dim);
    }
    panel_button(s,LOG_X,909,130,L"上一条",ui_event>0);
    panel_button(s,LOG_X+142,909,130,L"下一条",ui_event+1<ui_log_count);
    swprintf(detail,96,L"%u / %u",ui_event+1,ui_log_count);
    rk_label(s,LOG_X+309,936,detail,panel_dim);
}

static void ui_panel(struct surface *s,int mode,
                     uint32_t tiles[4][TILE_W*TILE_H],unsigned offline) {
    static uint32_t canvas[HEIGHT][WIDTH];
    static unsigned last_page=~0u,last_request,last_event,last_channel,last_live;
    static int last_mode=-2;
    static double refresh;
    unsigned request=advanced_board?channel_config():atomic_load(&requested_mode);
    unsigned live=atomic_load(&live_config[config_channel]);
    double timestamp=now();
    if(ui_page!=last_page || request!=last_request || mode!=last_mode ||
       ui_event!=last_event || config_channel!=last_channel || live!=last_live || timestamp>=refresh) {
        struct surface panel={.memory=(uint8_t *)canvas,.pitch=sizeof(canvas[0])};
        if(!ui_page) {
            wchar_t status[80];
            box(&panel,1070,0,610,67,panel_bg);
            box(&panel,1110,13,258,41,panel_alt);
            swprintf(status,80,L"PCIe  %.2f MB/s",atomic_load(&ui_mbps_x100)/100.);
            rk_label(&panel,1125,41,status,panel_mint);
            rk_label(&panel,1400,41,mode<0?L"切换中":advanced_board?L"逐路硬件模式":mode&4?L"Sobel 1-bit":mode?L"FPGA 预处理":L"彩色原画",panel_text);
            box(&panel,0,1012,WIDTH,38,panel_bg);
            box(&panel,0,1012,WIDTH,1,panel_edge);
            if(resolution_board) {
                for(unsigned ch=0;ch<4;ch++) {
                    int x=RESOLUTION_X+ch*RESOLUTION_STEP;
                    const wchar_t *const size[]={L"1080p",L"960×540",L"480×270"};
                    unsigned live_scale=resolution(atomic_load(&live_config[ch]));
                    unsigned wanted_scale=resolution(atomic_load(&requested_config[ch]));
                    wchar_t label[26];
                    swprintf(label,26,L"%ls  %ls",panel_ports[ch],size[wanted_scale]);
                    rk_label(&panel,x+10,1038,label,live_scale==wanted_scale?panel_mint:panel_amber);
                }
            } else rk_label(&panel,24,1038,L"每路 1920 × 1080",panel_text);
            if(!resolution_board) rk_label(&panel,340,1038,advanced_board?L"原画通道运行 NPU":mode==0?L"NPU 识别开启":L"当前模式暂停 NPU 识别",panel_mint);
            rk_label(&panel,890,1038,resolution_board?L"点击通道切换输出分辨率 · JPEG 与多曝光 HDR 待接入":L"当前固件：JPEG、逐路分辨率与 HDR 未接入",panel_dim);
        } else {
            box(&panel,0,68,WIDTH,HEIGHT-68,panel_bg);
            if(ui_page==1) panel_filters(&panel,mode);
            else if(ui_page==2) panel_diag(&panel);
            else panel_log(&panel);
        }
        last_page=ui_page; last_request=request; last_mode=mode; last_event=ui_event;
        last_channel=config_channel; last_live=live;
        refresh=timestamp+1;
    }
    if(!ui_page) {
        for(unsigned y=0;y<67;y++) memcpy(s->memory+y*s->pitch+1070*4,canvas[y]+1070,610*4);
        for(unsigned y=1012;y<HEIGHT;y++) memcpy(s->memory+y*s->pitch,canvas[y],sizeof(canvas[y]));
        return;
    }
    const unsigned width=ui_page==1?524:205, height=ui_page==1?294:115;
    const unsigned count=ui_page==1?2:ui_page==2?4:0;
    unsigned source_x[524];
    for(unsigned col=0;col<width;col++) source_x[col]=col*TILE_W/width;
    for(unsigned y=68;y<HEIGHT;y++) {
        uint32_t *line=(uint32_t *)(s->memory+y*s->pitch);
        unsigned first=0, top=928;
        if(ui_page==1) {
            first=y>=523?2:0;
            top=first?523:164;
        }
        unsigned start=0;
        if(y>=top && y<top+height) {
            for(unsigned col=0;col<count;col++) {
                unsigned x=ui_page==1?521+555*col:266+335*col;
                memcpy(line+start,canvas[y]+start,(x-start)*sizeof(*line));
                const uint32_t *input=tiles[first+col]+((y-top)*TILE_H/height)*TILE_W;
                for(unsigned i=0;i<width;i++) line[x+i]=input[source_x[i]];
                start=x+width;
            }
        }
        memcpy(line+start,canvas[y]+start,(WIDTH-start)*sizeof(*line));
    }
    for(unsigned ch=0;ch<4 && count;ch++)
        if((offline>>ch)&1) {
            unsigned x=ui_page==1?521+(ch%2)*555:266+ch*335;
            unsigned y=ui_page==1?164+(ch/2)*359:928;
            rk_label(s,x+12,y+31,L"\u65e0\u4fe1\u53f7",panel_amber);
        }
}
