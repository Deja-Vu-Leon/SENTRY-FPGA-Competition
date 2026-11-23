#include <math.h>

struct cockpit_object { int x1,y1,x2,y2,severity,confidence; float distance; char name[40]; };
struct cockpit_feed {
    double stamp;
    unsigned severity, count;
    unsigned stats[4];
    int stats_valid;
    int lane_valid, lane_held, lane_guide, lane[8];
    char status[92], alert[160];
    struct cockpit_object objects[12];
};
static struct cockpit_feed cockpit_feeds[4];
static const wchar_t *directions[]={L"A01  前方",L"A02  驾驶员",L"B01  右侧",L"B02  左侧"};
static const wchar_t *tasks[]={L"车辆 · 行人 · 信号灯 · 车道线",L"面部与持续闭眼监测",
                              L"行人检测 · 滑坡迹象",L"纵裂 · 横裂 · 龟裂"};

static void cockpit_label(struct surface *s,int x,int y,const char *line,uint32_t color) {
    wchar_t value[164];
    size_t n=mbstowcs(value,line,sizeof(value)/sizeof(value[0])-1);
    if(n==(size_t)-1) return;
    value[n]=0;
    rk_label(s,x,y,value,color);
}

static void cockpit_read(unsigned offline) {
    for(unsigned i=0;i<4;i++) {
        struct cockpit_feed feed={0};
        if(!(offline&(1u<<i))) {
            char path[96], line[256];
            snprintf(path,sizeof(path),"/run/sentry-vid007-ai/view%u",i);
            FILE *file=fopen(path,"r");
            if(file) {
                while(fgets(line,sizeof(line),file)) {
                    if(line[0]=='T') feed.stamp=strtod(line+2,NULL);
                    if(line[0]=='S') sscanf(line,"S %91[^\n]",feed.status);
                    if(line[0]=='A') sscanf(line,"A %u %159[^\n]",&feed.severity,feed.alert);
                    if(line[0]=='C')
                        feed.stats_valid=sscanf(line,"C %u %u %u %u",&feed.stats[0],
                                                &feed.stats[1],&feed.stats[2],&feed.stats[3])==4;
                    if(line[0]=='L') {
                        int *p=feed.lane;
                        if(sscanf(line,"L %d %d %d %d %d %d %d %d %d %d %d",&feed.lane_valid,
                            &feed.lane_held,&feed.lane_guide,p,p+1,p+2,p+3,p+4,p+5,p+6,p+7)!=11) feed.lane_valid=0;
                    }
                    if(line[0]=='O' && feed.count<12) {
                        struct cockpit_object *o=&feed.objects[feed.count];
                        if(sscanf(line,"O %d %d %d %d %f %d %d %39s",&o->x1,&o->y1,&o->x2,&o->y2,
                                  &o->distance,&o->severity,&o->confidence,o->name)==8) feed.count++;
                    }
                }
                fclose(file);
            }
        }
        cockpit_feeds[i]=(now()-feed.stamp<1.4)?feed:(struct cockpit_feed){0};
    }
}

static void cockpit_warning_banner(struct surface *s,unsigned offline) {
    static double next=0;
    static unsigned previous_offline=~0u;
    double t=now();
    if(t>=next || offline!=previous_offline) {
        cockpit_read(offline);
        next=t+.12;
        previous_offline=offline;
    }
    if(!ui_page) {
        unsigned row=0;
        for(unsigned i=0;i<4;i++) {
            const struct cockpit_feed *feed=&cockpit_feeds[i];
            if(!feed->severity || !feed->alert[0]) continue;
            int y=721+row++*59;
            box(s,1467,y,182,52,0xffe9ec);
            box(s,1467,y,3,52,feed->severity>1?ARMOUR_RED:ARMOUR_YELLOW);
            const wchar_t *port[]={L"A01",L"A02",L"B01",L"B02"};
            rk_label(s,1477,y+19,port[i],ARMOUR_RED);
            wchar_t message[120];
            size_t length=mbstowcs(message,feed->alert,119);
            if(length!=(size_t)-1) {
                message[length>8?8:length]=0;
                rk_label(s,1477,y+42,message,0x761d2e);
            }
        }
        if(!row) rk_label(s,1468,755,L"当前无告警",ARMOUR_MUTED);
        return;
    }
    for(unsigned i=0;i<4;i++) {
        struct cockpit_feed *f=&cockpit_feeds[i];
        if(!f->severity || !f->alert[0]) continue;
        int x=24+(int)i*412;
        box(s,x,74,398,43,0xffe9ec);
        box(s,x,74,4,43,f->severity>1?ARMOUR_RED:ARMOUR_YELLOW);
        if(ui_page==5) {
            char text[sizeof(f->alert)+16];
            snprintf(text,sizeof(text),"实时 · %s",f->alert);
            cockpit_label(s,x+15,102,text,0x761d2e);
        } else cockpit_label(s,x+15,102,f->alert,0x761d2e);
    }
}

struct cockpit_point { int x,y; };
static void cockpit_triangle(struct surface *s,struct cockpit_point a,struct cockpit_point b,
                             struct cockpit_point c,uint32_t color) {
    struct cockpit_point p[]={a,b,c};
    int ymin=a.y,ymax=a.y;
    for(unsigned i=1;i<3;i++) {
        if(p[i].y<ymin) ymin=p[i].y;
        if(p[i].y>ymax) ymax=p[i].y;
    }
    for(int y=ymin;y<ymax;y++) {
        if(y<226 || y>=730) continue;
        int x[2], n=0;
        for(unsigned i=0;i<3 && n<2;i++) {
            struct cockpit_point v=p[i],w=p[(i+1)%3];
            if(v.y>w.y) { struct cockpit_point tmp=v; v=w; w=tmp; }
            if(y>=v.y && y<w.y) x[n++]=v.x+(w.x-v.x)*(y-v.y)/(w.y-v.y);
        }
        if(n!=2) continue;
        int left=x[0]<x[1]?x[0]:x[1], right=x[0]>x[1]?x[0]:x[1];
        if(left<858) left=858;
        if(right>1623) right=1623;
        if(left<right) box(s,left,y,right-left,1,color);
    }
}

static void cockpit_quad(struct surface *s,struct cockpit_point a,struct cockpit_point b,
                         struct cockpit_point c,struct cockpit_point d,uint32_t color) {
    cockpit_triangle(s,a,b,c,color);
    cockpit_triangle(s,a,c,d,color);
}

#include "vid007-cockpit-hazards-3d.h"

static void cockpit_scene(struct surface *s) {
    int cx=1240, horizon=404;
    const struct cockpit_feed *front=&cockpit_feeds[0];
    if(front->lane_valid==3) cx+=(front->lane[2]+front->lane[6]-420)/3;
    for(int y=226;y<730;y++) {
        unsigned shade=y<horizon?25+(unsigned)(y-226)/9:34+(unsigned)(y-horizon)/13;
        box(s,858,y,765,1,((shade/2)<<16)|(shade<<8)|(shade+8));
    }
    cockpit_quad(s,(struct cockpit_point){cx-21,horizon},(struct cockpit_point){cx+21,horizon},
                   (struct cockpit_point){1690,730},(struct cockpit_point){788,730},ARMOUR_EDGE);
    for(int j=-2;j<=2;j+=4)
        cockpit_quad(s,(struct cockpit_point){cx+j*10,horizon},(struct cockpit_point){cx+j*10+2,horizon},
                     (struct cockpit_point){cx+j*219+4,730},(struct cockpit_point){cx+j*219-4,730},0x779294);
    for(int z=64;z>=4;z-=4) {
        int yy=horizon+1090/(z+3), end=horizon+1090/(z+1);
        int w=2+25/z;
        for(int lane=-1;lane<=1;lane+=2) {
            int x=cx+lane*400/(z+3), x2=cx+lane*400/(z+1);
            cockpit_quad(s,(struct cockpit_point){x-w,yy},(struct cockpit_point){x+w,yy},
                         (struct cockpit_point){x2+w,end},(struct cockpit_point){x2-w,end},0x8c9b98);
        }
    }
    unsigned used=0;
    for(unsigned slot=0;slot<front->count;slot++) {
        float farthest=0;
        unsigned index=0;
        for(unsigned i=0;i<front->count;i++)
            if(!(used&(1u<<i)) && front->objects[i].distance>farthest) {
                index=i;
                farthest=front->objects[i].distance;
            }
        if(farthest<=0 || !isfinite(farthest)) break;
        used|=1u<<index;
        const struct cockpit_object *o=&front->objects[index];
        float z=fmaxf(2,fminf(80,farthest));
        int y=horizon+(int)(1300/(z+4));
        int x=cx+(o->x1+o->x2-420)*(int)(70+880/(z+4))/420;
        int w=(int)(9+270/(z+3)), h=w*3/4;
        int large=!strcmp(o->name,"货车") || !strcmp(o->name,"客车");
        if(large) h=w*6/5;
        uint32_t body=o->severity?0xbe554a:0x507d8d;
        cockpit_quad(s,(struct cockpit_point){x-w-8,y+3},(struct cockpit_point){x+w+8,y+3},
                     (struct cockpit_point){x+w+13,y-4},(struct cockpit_point){x-w-1,y-4},ARMOUR_SILVER);
        if(!strcmp(o->name,"行人")) {
            box(s,x-3,y-h-7,7,7,0xe2c7a4);
            box(s,x-5,y-h,11,h*2/3,body);
            box(s,x-4,y-h/3,3,h/3,0x112228);
            box(s,x+2,y-h/3,3,h/3,0x112228);
        } else {
            box(s,x-w+2,y-10,5,12,0x101a20);
            box(s,x+w-6,y-10,5,12,0x101a20);
            cockpit_quad(s,(struct cockpit_point){x-w,y-3},(struct cockpit_point){x+w,y-3},
                         (struct cockpit_point){x+w+5,y-h+3},(struct cockpit_point){x-w+5,y-h+3},body);
            cockpit_quad(s,(struct cockpit_point){x-w+5,y-h+3},(struct cockpit_point){x+w+5,y-h+3},
                         (struct cockpit_point){x+(large?w:w/2)+6,y-h-h/2},
                         (struct cockpit_point){x-(large?w:w/2)+5,y-h-h/2},0x243e4a);
            cockpit_quad(s,(struct cockpit_point){x-w+5,y-h+3},(struct cockpit_point){x+w+5,y-h+3},
                         (struct cockpit_point){x+w-1,y-h+7},(struct cockpit_point){x-w+2,y-h+7},0x87a3ab);
            box(s,x-w+3,y-10,5,4,0xff9785);
            box(s,x+w-8,y-10,5,4,0xff9785);
        }
        if(z<52) {
            wchar_t label[24];
            swprintf(label,24,L"%.1fm",farthest);
            rk_label(s,x+12,y-h-12,label,0xf0ebd8);
        }
    }
    if(!front->stamp) rk_label(s,1048,482,L"等待 A01 实时数据",panel_text);
}

static void cockpit_line(struct surface *s,int x,int y,int x2,int y2) {
    int dx=x2-x, dy=y2-y, n=abs(dx)>abs(dy)?abs(dx):abs(dy);
    for(int i=0;i<=n && n>0;i++) {
        int xx=x+dx*i/n, yy=y+dy*i/n;
        if(xx>55 && xx<801 && yy>227 && yy<666) box(s,xx,yy,3,3,0x89e5bd);
    }
}

static void cockpit_perception(struct surface *s,unsigned offline) {
    panel_title(s,54,161,L"驾驶感知");
    rk_label(s,56,209,directions[cockpit_camera],panel_mint);
    rk_label(s,185,209,tasks[cockpit_camera],panel_text);
    rk_label(s,858,209,L"实时3D",panel_mint);
    cockpit_scene(s);
    const struct cockpit_feed *f=&cockpit_feeds[cockpit_camera];
    if(offline&(1u<<cockpit_camera)) rk_label(s,278,492,L"摄像头无信号",panel_amber);
    else if(f->status[0]) cockpit_label(s,56,707,f->status,panel_mint);
    if(cockpit_camera==0 && f->lane_valid)
        rk_label(s,238,707,f->lane_guide?L"车道线 · 录像标记":
                 f->lane_held?L"车道线 · 保持上一帧":L"车道线 · 路面提取",panel_dim);
    box(s,54,739,756,132,panel_surface);
    box(s,858,739,765,132,panel_surface);
    if(cockpit_camera==0) {
        const wchar_t *const labels[]={L"车辆总数",L"危险次数",L"障碍物",L"行人"};
        rk_label(s,72,769,L"A01  实时识别统计",panel_mint);
        for(unsigned i=0;i<4;i++) {
            int x=72+(int)i*184;
            wchar_t value[24]=L"—";
            if(f->stats_valid) swprintf(value,24,L"%u",f->stats[i]);
            box(s,x,784,174,72,panel_alt);
            rk_label(s,x+12,808,labels[i],panel_dim);
            rk_label(s,x+12,840,value,i==1 && f->stats[1]?ARMOUR_RED:panel_text);
            rk_label(s,x+74,840,i==1?L"本次运行":L"当前画面",panel_dim);
        }
    } else {
        rk_label(s,72,775,directions[cockpit_camera],panel_mint);
        rk_label(s,72,830,tasks[cockpit_camera],panel_dim);
    }
    rk_label(s,879,775,L"车辆与行人距离为单目估算",panel_text);
    rk_label(s,879,830,L"左侧道路裂缝 · 右侧滑坡 · 方向示意",panel_dim);
    for(unsigned i=0;i<4;i++) {
        int x=32+(int)i*404;
        box(s,x,881,392,120,i==cockpit_camera?ARMOUR_LIGHT_BLUE:panel_surface);
        box(s,x,999,392,2,i==cockpit_camera?panel_mint:panel_edge);
        rk_label(s,x+184,926,directions[i],panel_text);
    }
}

static unsigned play_show;
static void cockpit_record(struct surface *s) {
    panel_title(s,54,151,L"录像与回放");
    box(s,40,164,453,742,panel_surface);
    panel_button(s,54,185,182,L"开始录像",1);
    panel_button(s,252,185,182,L"停止录像",1);
    char status[128]="等待录像服务";
    FILE *file=fopen("/run/sentry-vid007-ai/record.status","r");
    if(file) {
        if(!fgets(status,sizeof(status),file)) status[0]=0;
        fclose(file);
    }
    cockpit_label(s,55,241,status,panel_dim);

    box(s,54,251,207,37,library_source==0?ARMOUR_LIGHT_BLUE:panel_alt);
    box(s,269,251,207,37,library_source==1?ARMOUR_LIGHT_BLUE:panel_alt);
    rk_label(s,71,277,L"TF 卡历史",library_source==0?panel_mint:panel_dim);
    rk_label(s,286,277,L"本地视频",library_source==1?panel_mint:panel_dim);

    char selected[17]="-";
    unsigned mode=0,state=0,w=0,h=0;
    double position=0,duration=0,rate=0;
    file=fopen("/run/sentry-vid007-ai/play.status","r");
    if(file) {
        if(fscanf(file,"%16s %u %u %lf %lf %lf %u %u",selected,&mode,&state,&position,&duration,&rate,&w,&h)!=8)
            state=0;
        fclose(file);
    }
    play_show=state>=1 && state<=3;
    memset(library_ids,0,sizeof(library_ids));
    library_more=0;
    file=fopen("/run/sentry-vid007-ai/play.catalog","r");
    unsigned seen=0,count=0;
    char line[320];
    if(file) {
        while(fgets(line,sizeof(line),file)) {
            char id[17],name[256];
            unsigned type;
            if(sscanf(line,"%u %16s %255[^\n]",&type,id,name)!=3 || type!=library_source) continue;
            if(seen++<library_page*LIB_ROWS) continue;
            if(count==LIB_ROWS) { library_more=1; break; }
            int y=LIB_TOP+(int)count*LIB_STEP;
            int active=!strcmp(selected,id);
            box(s,54,y,422,39,active?ARMOUR_LIGHT_BLUE:panel_alt);
            wchar_t title[256];
            size_t length=mbstowcs(title,name,255);
            if(length!=(size_t)-1) {
                if(length>26) { title[25]=L'…'; length=26; }
                title[length]=0;
                rk_label(s,69,y+26,title,active?panel_mint:panel_text);
            }
            memcpy(library_ids[count++],id,17);
        }
        fclose(file);
    }
    if(!count) rk_label(s,70,362,library_source?L"本地视频目录为空":L"暂无已完成的录像段",panel_dim);
    panel_button(s,54,851,201,L"上一页",library_page>0);
    panel_button(s,269,851,207,L"下一页",library_more);
    if(library_source) rk_label(s,55,925,L"/home/linaro/Videos",panel_dim);
    else rk_label(s,55,925,L"H.264 · 840×472 · 8 fps",panel_dim);
    box(s,PLAY_X,PLAY_Y,PLAY_W,PLAY_H,0x0d1418);
    if(!play_show) rk_label(s,866,451,state==4?L"无法读取视频":L"从列表选择录像或本地视频",state==4?panel_amber:panel_dim);
    box(s,PLAY_X,751,PLAY_W,4,panel_edge);
    if(duration>0 && position>=0) {
        int value=(int)(PLAY_W*fmin(1,position/duration));
        if(value>0) box(s,PLAY_X,751,value,4,panel_mint);
    }
    wchar_t timing[85];
    unsigned elapsed=position>=0 && position<360000?(unsigned)position:0;
    unsigned total=duration>=0 && duration<360000?(unsigned)duration:0;
    if(w && h && play_show) {
        swprintf(timing,85,L"%02u:%02u / %02u:%02u",elapsed/60,elapsed%60,total/60,total%60);
        rk_label(s,531,779,timing,panel_dim);
        swprintf(timing,85,L"%u×%u · %.2f fps",w,h,rate);
        rk_label(s,1333,779,timing,panel_dim);
    }
    panel_button(s,530,790,128,state==2?L"继续":L"暂停",state==1||state==2);
    panel_button(s,670,790,128,L"停止",play_show);
    box(s,1114,790,210,39,mode==0?ARMOUR_LIGHT_BLUE:panel_alt);
    box(s,1332,790,238,39,mode==1?ARMOUR_LIGHT_BLUE:panel_alt);
    rk_label(s,1130,817,L"原始画面",mode==0?panel_mint:panel_dim);
    rk_label(s,1349,817,L"YOLO 识别",mode==1?panel_mint:panel_dim);
}

static int playback_blit(struct surface *s) {
    static struct { _Atomic uint32_t seq; uint32_t pixels[PLAY_H][PLAY_W]; } *frames;
    static uint32_t local[2][PLAY_H][PLAY_W], last;
    static unsigned visible;
    if(!play_show) return 0;
    if(!frames) frames=ai_map("/run/sentry-vid007-ai/play.frames",sizeof(*frames));
    if(!frames) return 0;
    uint32_t seq=atomic_load_explicit(&frames->seq,memory_order_acquire);
    if(seq && !(seq&1) && seq!=last) {
        memcpy(local[visible^1],frames->pixels,sizeof(local[0]));
        atomic_thread_fence(memory_order_acquire);
        if(seq==atomic_load_explicit(&frames->seq,memory_order_acquire)) {
            visible^=1;
            last=seq;
        }
    }
    if(last && (s->page!=ui_page || s->play_sequence!=last)) {
        for(int y=0;y<PLAY_H;y++)
            memcpy(s->memory+(PLAY_Y+y)*s->pitch+PLAY_X*4,local[visible][y],sizeof(local[0][y]));
        s->play_sequence=last;
    }
    return last!=0;
}

static void cockpit_chat(struct surface *s) {
    panel_title(s,54,161,L"AI 对话");
    rk_label(s,54,215,L"RK → Ethernet → ESP32 → Wi-Fi → DeepSeek",panel_mint);
    box(s,54,242,1569,576,panel_surface);
    if(cockpit_message_count) {
        rk_label(s,80,281,L"最近提问",panel_dim);
        cockpit_label(s,80,315,cockpit_messages[2],panel_text);
    }
    char answer[16385]={0};
    FILE *reply=fopen("/run/sentry-esp32/answer.txt","r");
    if(reply) { size_t n=fread(answer,1,sizeof(answer)-1,reply);answer[n]=0;fclose(reply); }
    if(access("/run/sentry-esp32/question.txt",F_OK)==0)
        snprintf(answer,sizeof(answer),"正在通过 ESP32 请求 DeepSeek，请稍候……");
    if(!answer[0]) snprintf(answer,sizeof(answer),"输入问题后按 Enter，回答会显示在这里。");
    wchar_t wide[16385];
    size_t total=mbstowcs(wide,answer,16384);
    if(total==(size_t)-1) { wcscpy(wide,L"回答编码无效，请重新提交");total=wcslen(wide); }
    wide[total]=0;
    unsigned row=0,col=0;wchar_t line[160];size_t used=0;
    for(size_t i=0;i<=total && row<14;i++) {
        wchar_t ch=wide[i];
        if(ch==L'\n' || !ch || col+(ch>127?2:1)>136) {
            line[used]=0;rk_label(s,80,360+(int)row*29,line,panel_text);
            row++;used=0;col=0;
            if(!ch) break;
            if(ch==L'\n') continue;
        }
        if(ch>=32) { line[used++]=ch;col+=ch>127?2:1; }
    }
    if(cockpit_gateway_notice[0]) cockpit_label(s,80,803,cockpit_gateway_notice,panel_amber);
    wchar_t mode[180];
    swprintf(mode,180,L"%ls · Tab 切换中英文 · 空格确认 · 1–5 选词 · PgUp/PgDn 翻页 · Enter 发送",cockpit_chinese?L"中文拼音":L"英文输入");
    rk_label(s,54,850,mode,panel_mint);
    box(s,54,879,1362,39,panel_alt);
    if(cockpit_draft[0]) cockpit_label(s,66,906,cockpit_draft,panel_text);
    else rk_label(s,66,906,L"输入拼音，例如 nihao，空格确认后按 Enter 发送",panel_dim);
    if(cockpit_preedit[0]) {
        box(s,54,929,1565,88,panel_alt);
        for(unsigned i=0;i<5;i++) if(cockpit_candidates[i][0]) {
            wchar_t choice[128],candidate[160];
            size_t length=mbstowcs(choice,cockpit_candidates[i],127);
            if(length==(size_t)-1) continue;
            choice[length]=0;swprintf(candidate,160,L"%u  %.12ls%ls",i+1,choice,length>12?L"…":L"");
            rk_label(s,66+(int)i*313,961,candidate,i?panel_text:panel_mint);
        }
        char composition[180];snprintf(composition,sizeof(composition),"%s    [%u/%u]",cockpit_preedit,cockpit_ime_page+1,(cockpit_ime_count+4)/5);
        cockpit_label(s,66,999,composition,panel_dim);
    }
    panel_button(s,1432,879,186,L"提交  Enter",1);
}

static void cockpit_thumbnail(struct surface *s,const uint32_t *tile,int x0,int y0,int width,int height) {
    for(int y=0;y<height;y++) {
        uint32_t *row=(uint32_t *)(s->memory+(y0+y)*s->pitch)+x0;
        const uint32_t *src=tile+(y*TILE_H/height)*TILE_W;
        for(int x=0;x<width;x++) row[x]=src[x*TILE_W/width];
    }
}

static void cockpit_page(struct surface *s,uint32_t tiles[4][TILE_W*TILE_H],const unsigned fps[4],
                         unsigned offline) {
    static uint32_t cache[HEIGHT][WIDTH];
    static double refresh;
    static unsigned last_page,last_revision,last_offline;
    static unsigned generation;
    double t=now();
    if(t>=refresh || last_page!=ui_page || last_revision!=cockpit_revision || last_offline!=offline) {
        struct surface buffer={.memory=(uint8_t *)cache,.pitch=sizeof(cache[0])};
        box(&buffer,0,68,WIDTH,HEIGHT-68,panel_bg);
        if(ui_page==4) cockpit_perception(&buffer,offline);
        if(ui_page==5) {
            cockpit_record(&buffer);
            for(unsigned i=0;i<4;i++) {
                int x=530+(int)i*263;
                box(&buffer,x,864,248,160,panel_surface);
                rk_label(&buffer,x+10,889,directions[i],panel_text);
                wchar_t rate[24];
                swprintf(rate,24,L"%u FPS",fps[i]);
                rk_label(&buffer,x+155,889,rate,panel_mint);
                if(offline&(1u<<i)) rk_label(&buffer,x+44,956,L"摄像头无信号",panel_amber);
            }
        }
        if(ui_page==6) cockpit_chat(&buffer);
        refresh=t+(ui_page==5?.25:.17);
        last_page=ui_page;
        last_revision=cockpit_revision;
        last_offline=offline;
        generation++;
    }
    int playing=ui_page==5 && playback_blit(s);
    if(!playing) s->play_sequence=0;
    int redraw=ui_page!=5 || s->page!=ui_page || s->background!=generation;
    s->background=generation;
    for(int y=68;y<(redraw?HEIGHT:117);y++) {
        uint8_t *row=s->memory+y*s->pitch;
        if(playing && y>=PLAY_Y && y<PLAY_Y+PLAY_H) {
            memcpy(row,cache[y],PLAY_X*4);
            memcpy(row+(PLAY_X+PLAY_W)*4,cache[y]+PLAY_X+PLAY_W,(WIDTH-PLAY_X-PLAY_W)*4);
        } else memcpy(row,cache[y],sizeof(cache[0]));
    }
    if(ui_page==5) {
        for(unsigned i=0;i<4;i++) {
            int x=530+(int)i*263;
            if(!(offline&(1u<<i))) cockpit_thumbnail(s,tiles[i],x+9,897,230,127);
        }
        return;
    }
    if(ui_page!=4) return;
    cockpit_scene_hazards(s,offline,t);
    unsigned selected=cockpit_camera;
    if(!(offline&(1u<<selected))) {
        cockpit_thumbnail(s,tiles[selected],54,226,756,425);
        const struct cockpit_feed *f=&cockpit_feeds[selected];
        if(selected==0 && f->lane_valid)
            for(unsigned i=0;i<8;i+=4)
                if(f->lane_valid&(1<<(i/4)))
                    cockpit_line(s,54+f->lane[i]*756/420,226+f->lane[i+1]*425/236,
                                 54+f->lane[i+2]*756/420,226+f->lane[i+3]*425/236);
        for(unsigned i=0;i<f->count;i++) {
            const struct cockpit_object *o=&f->objects[i];
            int l=54+o->x1*756/420,r=54+o->x2*756/420,u=226+o->y1*425/236,b=226+o->y2*425/236;
            if(l<54 || r>809 || u<226 || b>650 || l>=r || u>=b) continue;
            uint32_t color=o->severity?0xf89076:0x91e3c7;
            box(s,l,u,r-l,2,color);
            box(s,l,b,r-l,2,color);
            box(s,l,u,2,b-u,color);
            box(s,r,u,2,b-u,color);
            char label[72];
            if(o->distance>=0) snprintf(label,sizeof(label),"%s %.1fm · %d%%",o->name,o->distance,o->confidence);
            else if(o->confidence>=0) snprintf(label,sizeof(label),"%s · %d%%",o->name,o->confidence);
            else snprintf(label,sizeof(label),"%s",o->name);
            int lx=l>640?640:l;
            int ly=u<258?u+21:u-4;
            box(s,lx,ly-18,164,22,ARMOUR_SILVER);
            cockpit_label(s,lx+4,ly,label,color);
        }
    }
    for(unsigned i=0;i<4;i++) {
        int x0=45+(int)i*404;
        if(!(offline&(1u<<i))) cockpit_thumbnail(s,tiles[i],x0,895,160,90);
        wchar_t rate[24];
        swprintf(rate,24,L"%u FPS",fps[i]);
        rk_label(s,x0+171,970,(offline&(1u<<i))?L"无信号":rate,panel_dim);
    }
}
