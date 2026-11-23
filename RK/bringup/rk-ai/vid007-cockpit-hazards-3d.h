/* The markers represent camera direction and detection class, not measured position. */
enum scene_hazard {
    SCENE_SLOPE_SOURCE, SCENE_SLOPE_DEBRIS, SCENE_SLOPE_GENERIC,
    SCENE_LONG_CRACK, SCENE_CROSS_CRACK, SCENE_ALLIGATOR_CRACK, SCENE_GENERIC_CRACK,
    SCENE_HAZARD_COUNT
};

static const char *const scene_hazard_words[SCENE_HAZARD_COUNT]={
    "滑坡源区","滑坡堆积区","土石扰动","纵向裂缝","横向裂缝","龟裂","道路裂缝"
};
static const wchar_t *const scene_hazard_labels[SCENE_HAZARD_COUNT]={
    L"滑坡源区",L"滑坡堆积区",L"疑似土石扰动",L"纵向裂缝",L"横向裂缝",L"龟裂",L"疑似道路裂缝"
};

static unsigned scene_hazard_mask(unsigned offline,double timestamp) {
    static double deadline[SCENE_HAZARD_COUNT];
    unsigned mask=0;
    for(unsigned type=0;type<SCENE_HAZARD_COUNT;type++) {
        unsigned channel=type<SCENE_LONG_CRACK?2:3;
        const struct cockpit_feed *feed=&cockpit_feeds[channel];
        if((offline&(1u<<channel)) || !feed->stamp || timestamp-feed->stamp>=1.4) {
            deadline[type]=0;
            continue;
        }
        const char *word=scene_hazard_words[type];
        int present=feed->severity && strstr(feed->alert,word);
        for(unsigned i=0;i<feed->count && !present;i++)
            present=feed->objects[i].severity && strstr(feed->objects[i].name,word);
        if(present) deadline[type]=timestamp+1.0;
        if(timestamp<deadline[type]) mask|=1u<<type;
    }
    return mask;
}

static void scene_segment(struct surface *s,int x,int y,int ex,int ey,int width,uint32_t color) {
    int dx=ex-x,dy=ey-y;
    int steps=abs(dx)>abs(dy)?abs(dx):abs(dy);
    if(!steps) return;
    for(int i=0;i<=steps;i++) {
        int px=x+i*dx/steps,py=y+i*dy/steps;
        if(px>=858 && px+width<=1623 && py>=226 && py+width<=730)
            box(s,px,py,width,width,color);
    }
}

static void scene_rock(struct surface *s,int x,int y,int radius,uint32_t color) {
    struct cockpit_point a={x-radius,y},b={x-2,y-radius};
    struct cockpit_point c={x+radius,y-radius/2},d={x+radius/2,y+radius/2};
    cockpit_quad(s,a,b,c,d,color);
}

static void scene_slope_hazard(struct surface *s,unsigned mask,unsigned tick) {
    unsigned kinds=mask&7u;
    if(!kinds) return;
    if(kinds!=1u<<SCENE_SLOPE_DEBRIS) {
        cockpit_triangle(s,(struct cockpit_point){1370,545},(struct cockpit_point){1525,362},
                         (struct cockpit_point){1623,560},0x76413b);
        cockpit_triangle(s,(struct cockpit_point){1525,362},(struct cockpit_point){1623,560},
                         (struct cockpit_point){1537,528},0x512c32);
        for(unsigned i=0;i<7;i++) {
            unsigned phase=(tick+i*6)%42;
            scene_rock(s,1526-(int)phase*3+(int)(i%3)*9,371+(int)phase*4,
                       4+(int)phase/8,(i%2)?ARMOUR_YELLOW:0xff9255);
        }
    }
    if(kinds&(1u<<SCENE_SLOPE_DEBRIS)) {
        for(unsigned i=0;i<10;i++) {
            int row=(int)i/4, col=(int)i%4;
            scene_rock(s,1400+col*22+row*10,552+row*12,10+row*3,
                       (i%3)?0xbc6b4c:0xf0a565);
        }
        int pulse=(int)(tick%16);
        scene_segment(s,1381-pulse,585+pulse,1508+pulse,585+pulse,2,ARMOUR_YELLOW);
    } else {
        scene_segment(s,1382,551,1502,551,2,ARMOUR_YELLOW);
    }
}

static void scene_road_hazards(struct surface *s,unsigned mask,unsigned tick) {
    /* Keep different crack classes at different depths so concurrent warnings stay visible. */
    int pulse=(int)(tick%24);
    if(mask&(1u<<SCENE_LONG_CRACK)) {
        const struct cockpit_point p[]={{1161,488},{1146,518},{1149,540},{1115,586},{1109,604}};
        for(unsigned i=1;i<sizeof(p)/sizeof(*p);i++)
            scene_segment(s,p[i-1].x,p[i-1].y,p[i].x,p[i].y,4,0x762c39);
        int y=490+pulse*4;
        scene_rock(s,1160-(y-490)*48/110,y,6,ARMOUR_YELLOW);
    }
    if(mask&(1u<<SCENE_CROSS_CRACK)) {
        const struct cockpit_point p[]={{995,626},{1033,613},{1080,622},{1123,610},{1195,615}};
        for(unsigned i=1;i<sizeof(p)/sizeof(*p);i++)
            scene_segment(s,p[i-1].x,p[i-1].y,p[i].x,p[i].y,4,0x762c39);
        scene_rock(s,999+pulse*8,617,6,ARMOUR_YELLOW);
    }
    if(mask&(1u<<SCENE_ALLIGATOR_CRACK)) {
        for(int i=0;i<3;i++) for(int j=0;j<4;j++) {
            int x=1007+j*31+(i%2)*15, y=670+i*12;
            uint32_t color=(unsigned)(i+j)==(tick/4)%6?ARMOUR_YELLOW:0x762c39;
            scene_segment(s,x,y,x+15,y-8,3,color);
            scene_segment(s,x+15,y-8,x+31,y,3,color);
            if(i<2) scene_segment(s,x+31,y,x+27,y+11,3,color);
        }
    }
    if(mask&(1u<<SCENE_GENERIC_CRACK)) {
        scene_segment(s,1192,652,1148,685,3,0x762c39);
        scene_segment(s,1148,685,1151,705,3,0x762c39);
        scene_rock(s,1190-pulse*2,652+pulse*2,5,ARMOUR_YELLOW);
    }
}

static void cockpit_scene_hazards(struct surface *s,unsigned offline,double timestamp) {
    unsigned mask=scene_hazard_mask(offline,timestamp);
    if(!mask) return;
    unsigned tick=(unsigned)fmod(timestamp*20,5040.0);
    scene_slope_hazard(s,mask,tick);
    scene_road_hazards(s,mask,tick);
    unsigned rows[2]={0,0};
    for(unsigned type=0;type<SCENE_HAZARD_COUNT;type++) {
        if(!(mask&(1u<<type))) continue;
        unsigned right=type<SCENE_LONG_CRACK;
        int x=right?1379:874, y=241+(int)rows[right]++*35;
        box(s,x,y,224,30,0xffe9ec);
        box(s,x,y,4,30,right?ARMOUR_RED:0xe49b30);
        rk_label(s,x+12,y+21,right?L"B01 右侧":L"B02 左侧",0x761d2e);
        rk_label(s,x+110,y+21,scene_hazard_labels[type],0x761d2e);
    }
}
