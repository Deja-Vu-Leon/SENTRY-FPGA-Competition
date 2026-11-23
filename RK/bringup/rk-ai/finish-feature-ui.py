from pathlib import Path
r=Path(__file__).parent
p=r/"vid007-feature-pages.h"
s=p.read_text()
s=s.replace("172+row*34","172+row*30").replace("1604,33,row","1604,29,row").replace("L\"完整帧捕获 FPS\",L\"FPGA 交付 FPS（RK 完整接收）\"","L\"完整帧捕获 FPS（传感器端）\",L\"FPGA 交付 FPS（RK 校验通过）\"")
s=s.replace('L"相机源帧号（最近接收）"','L"最近接收帧号（Sobel 为输出序号）"')
s=s.replace('rk_label(s,40,991,L"— 表示当前数据通路未提供对应指标。现有队列为转换前的原始帧队列。",dim);',
'''rk_label(s,40,890,L"— 表示当前数据通路未提供对应指标。帧号跳跃含 FPGA 主动抽帧。",dim);
        rk_label(s,40,935,L"实时画面",mint);
        for(unsigned ch=0;ch<4;ch++) rk_label(s,280+335*ch,924,ports[ch],mint);''')
p.write_text(s,encoding="utf-8")
p=r/"make-feature-ui.py"
s=p.read_text()
s=s.replace("            if(ui_page) fresh=0;", """            if(ui_page==2) {
                for(unsigned ch=0;ch<4;ch++)
                    for(unsigned y=0;y<115;y++) {
                        uint32_t *line=(uint32_t *)(s->memory+(930+y)*s->pitch)+280+335*ch;
                        for(unsigned x=0;x<205;x++)
                            line[x]=tiles[ch][(y*TILE_H/115)*TILE_W+x*TILE_W/205];
                    }
            } else if(ui_page) fresh=0;""")
s=s.replace('atomic_store(&ui_rx_fps_x100[i],(unsigned)((cam->complete-totals[i])*100/elapsed));','atomic_store(&ui_rx_fps_x100[i],(unsigned)((cam->complete-totals[i])*100/elapsed));')
# Clear rate samples while a new packet format is starting.
s=s.replace('s=edit(s,"        cam->bad++;","        cam->bad++;") if False else s','')
p.write_text(s,encoding="utf-8")
