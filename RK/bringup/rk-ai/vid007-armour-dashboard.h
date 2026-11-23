static void armour_monitor(struct surface *s, uint32_t tiles[4][TILE_W*TILE_H],
                           const unsigned fps[4], int mode, unsigned offline, double timestamp) {
    static uint32_t canvas[HEIGHT][WIDTH];
    static unsigned sample[32], count, cursor, previous_offline=~0u;
    static int previous_mode=-2;
    static double next_draw, next_sample;
    struct surface panel={.memory=(uint8_t *)canvas,.pitch=sizeof(canvas[0])};
    unsigned throughput=atomic_load(&ui_mbps_x100);
    if(timestamp>=next_sample) {
        sample[cursor]=throughput;
        cursor=(cursor+1)%32;
        if(count<32) count++;
        next_sample=timestamp+1;
    }
    if(timestamp>=next_draw || offline!=previous_offline || mode!=previous_mode) {
        box(&panel,0,68,WIDTH,944,ARMOUR_WHITE);
        armour_panel(&panel,16,123,150,857,ARMOUR_SILVER,ARMOUR_BLUE);
        rk_label(&panel,29,153,L"系统导航",ARMOUR_NAVY);
        const wchar_t *names[]={L"实时监看",L"设备控制",L"链路诊断",L"告警日志",L"驾驶感知",L"录像回放",L"AI 对话"};
        for(unsigned i=0;i<7;i++) {
            int y=MONITOR_NAV_Y+i*MONITOR_NAV_STEP;
            box(&panel,24,y,134,42,i?ARMOUR_PAPER:ARMOUR_BLUE);
            box(&panel,24,y,3,42,i?ARMOUR_EDGE:ARMOUR_RED);
            rk_label(&panel,34,y+28,names[i],i?ARMOUR_INK:ARMOUR_PAPER);
        }
        rk_label(&panel,28,951,L"RK3568",ARMOUR_NAVY);
        for(int i=0;i<5;i++) box(&panel,28+i*13,963,8,2,ARMOUR_EDGE);
        const wchar_t *ports[]={L"A01  前方感知",L"A02  驾驶员监测",L"B01  行人与边坡",L"B02  左侧路面"};
        for(unsigned ch=0;ch<4;ch++) {
            int x=MONITOR_X+(ch%2)*MONITOR_STEP_X;
            int y=MONITOR_Y+(ch/2)*MONITOR_STEP_Y;
            int lost=(offline>>ch)&1;
            armour_panel(&panel,x-2,y-36,MONITOR_W+4,MONITOR_H+39,ARMOUR_PAPER,ARMOUR_BLUE);
            rk_label(&panel,x+11,y-10,ports[ch],ARMOUR_NAVY);
            wchar_t rate[24];
            swprintf(rate,24,L"%u FPS",fps[ch]);
            rk_label(&panel,x+MONITOR_W-110,y-10,
                     mode<0?L"切换中":lost?L"无信号":rate,
                     mode<0?ARMOUR_MUTED:lost?ARMOUR_RED:ARMOUR_BLUE);
        }
        armour_panel(&panel,MONITOR_RAIL_X,123,MONITOR_RAIL_W,266,ARMOUR_PAPER,ARMOUR_BLUE);
        rk_label(&panel,1468,158,L"系统健康",ARMOUR_NAVY);
        const wchar_t *channels[]={L"A01",L"A02",L"B01",L"B02"};
        for(unsigned i=0;i<4;i++) {
            int y=179+i*44;
            int lost=(offline>>i)&1;
            box(&panel,1467,y,182,36,ARMOUR_SILVER);
            box(&panel,1476,y+12,9,9,mode<0?ARMOUR_YELLOW:lost?ARMOUR_RED:ARMOUR_GREEN);
            rk_label(&panel,1493,y+25,channels[i],ARMOUR_INK);
            rk_label(&panel,1561,y+25,mode<0?L"等待":lost?L"离线":L"在线",ARMOUR_INK);
        }
        armour_panel(&panel,MONITOR_RAIL_X,408,MONITOR_RAIL_W,245,ARMOUR_PAPER,ARMOUR_BLUE);
        rk_label(&panel,1468,443,L"PCIe 吞吐",ARMOUR_NAVY);
        wchar_t rate[40];
        swprintf(rate,40,L"%.2f MB/s",throughput/100.0);
        rk_label(&panel,1468,478,rate,ARMOUR_BLUE);
        unsigned ceiling=50000;
        for(unsigned i=0;i<count;i++) if(sample[i]>ceiling) ceiling=sample[i];
        for(int i=0;i<4;i++) box(&panel,1468,500+i*34,180,1,ARMOUR_SILVER);
        int previous=0;
        for(unsigned i=0;i<count;i++) {
            unsigned value=sample[(cursor+32-count+i)%32];
            int y=602-(int)(value*102ull/ceiling);
            int x=1468+(int)i*5;
            if(i) box(&panel,x,previous<y?previous:y,2,abs(y-previous)+2,ARMOUR_BLUE);
            box(&panel,x,y,5,2,ARMOUR_BLUE);
            previous=y;
        }
        rk_label(&panel,1468,635,L"最近 32 秒",ARMOUR_MUTED);
        armour_panel(&panel,MONITOR_RAIL_X,672,MONITOR_RAIL_W,308,ARMOUR_PAPER,ARMOUR_RED);
        rk_label(&panel,1468,707,L"实时告警",ARMOUR_NAVY);
        next_draw=timestamp+0.5;
        previous_offline=offline;
        previous_mode=mode;
    }
    for(int y=68;y<1012;y++) {
        int row=y>=MONITOR_Y+MONITOR_STEP_Y;
        int tile_y=y-MONITOR_Y-row*MONITOR_STEP_Y;
        uint32_t *output=(uint32_t *)(s->memory+y*s->pitch);
        if(tile_y<0 || tile_y>=MONITOR_H) {
            memcpy(output,canvas[y],sizeof(canvas[y]));
            continue;
        }
        memcpy(output,canvas[y],MONITOR_X*4);
        memcpy(output+MONITOR_X+MONITOR_W,canvas[y]+MONITOR_X+MONITOR_W,
               (MONITOR_STEP_X-MONITOR_W)*4);
        int end=MONITOR_X+MONITOR_STEP_X+MONITOR_W;
        memcpy(output+end,canvas[y]+end,(WIDTH-end)*4);
        unsigned source_y=tile_y*TILE_H/MONITOR_H;
        for(unsigned col=0;col<2;col++) {
            unsigned ch=row*2+col;
            uint32_t *image=output+MONITOR_X+col*MONITOR_STEP_X;
            if(mode<0 || ((offline>>ch)&1)) {
                for(int x=0;x<MONITOR_W;x++) image[x]=ARMOUR_SILVER;
            } else {
                const uint32_t *source=tiles[ch]+source_y*TILE_W;
                for(int x=0;x<MONITOR_W;x++) image[x]=source[x*TILE_W/MONITOR_W];
            }
        }
    }
    for(unsigned ch=0;ch<4;ch++) if(mode<0 || ((offline>>ch)&1))
        rk_label(s,MONITOR_X+(ch%2)*MONITOR_STEP_X+235,
                 MONITOR_Y+(ch/2)*MONITOR_STEP_Y+MONITOR_H/2,
                 mode<0?L"等待图像":L"摄像头无信号",ARMOUR_MUTED);
}
