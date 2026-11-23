/* Shared-memory interface to the independent RK inference process. */
#include <sys/stat.h>

enum { AI_W=420, AI_H=236, AI_PIXELS=AI_W*AI_H, AI_MAX_BOXES=12 };
struct ai_input {
    _Atomic uint32_t seq;
    uint32_t xrgb[AI_PIXELS];
};
struct ai_box {
    int32_t x1, y1, x2, y2;
    uint32_t color;
    char label[44];
};
struct ai_output {
    _Atomic uint32_t seq;
    uint32_t count;
    uint64_t valid_until_ns;
    struct ai_box boxes[AI_MAX_BOXES];
    char status[32];
};
struct ai_exchange {
    struct ai_input inputs[4];
    struct ai_output outputs[4];
};
_Static_assert(sizeof(struct ai_input)==396484 && sizeof(struct ai_output)==816,
               "RK detection exchange layout");
static struct ai_exchange *ai;
static struct ai_input *record_inputs;
#ifdef VID007_HAZARD_DETAIL
struct ai_detail_frame {
    _Atomic uint32_t seq;
    uint32_t xrgb[TILE_W*TILE_H];
};
_Static_assert(sizeof(struct ai_detail_frame)==1585924,"RK hazard frame layout");
static struct ai_detail_frame *ai_detail;
#endif

static void *ai_map(const char *path,size_t size) {
    int fd=open(path,O_RDWR|O_CLOEXEC|O_NOFOLLOW);
    if (fd<0) return NULL;
    struct stat info;
    void *mem=MAP_FAILED;
    if (!fstat(fd,&info) && info.st_size==(off_t)size)
        mem=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    close(fd);
    return mem==MAP_FAILED?NULL:mem;
}

static void ai_open(void) {
    ai=ai_map("/run/sentry-vid007-ai/exchange",sizeof(*ai));
    record_inputs=ai_map("/run/sentry-vid007-ai/record.frames",4*sizeof(*record_inputs));
#ifdef VID007_HAZARD_DETAIL
    ai_detail=ai_map("/run/sentry-vid007-ai/hazard-detail",2*sizeof(*ai_detail));
#endif
}

static void publish_thumbnail(struct ai_input *in,const uint32_t *tile) {
    uint32_t next=(atomic_load_explicit(&in->seq,memory_order_relaxed)+2)&~1u;
    atomic_store_explicit(&in->seq,next-1,memory_order_relaxed);
    atomic_thread_fence(memory_order_seq_cst);
    for (unsigned y=0; y<AI_H; y++) {
        const uint32_t *row=tile+2*y*TILE_W;
        uint32_t *dest=in->xrgb+y*AI_W;
        for (unsigned x=0; x<AI_W; x+=4)
            vst1q_u32(dest+x,vld2q_u32(row+2*x).val[0]);
    }
    atomic_store_explicit(&in->seq,next,memory_order_release);
}

static void ai_publish(unsigned channel,const uint32_t *tile) {
    publish_thumbnail(&ai->inputs[channel],tile);
}

#ifdef VID007_HAZARD_DETAIL
static void ai_publish_detail(unsigned channel,const uint32_t *tile,double stamp) {
    static double next_detail[2];
    if(!ai_detail || channel<2 || stamp<next_detail[channel-2]) return;
    next_detail[channel-2]=stamp+.46;
    struct ai_detail_frame *in=&ai_detail[channel-2];
    uint32_t seq=(atomic_load_explicit(&in->seq,memory_order_relaxed)+2)&~1u;
    atomic_store_explicit(&in->seq,seq-1,memory_order_relaxed);
    atomic_thread_fence(memory_order_seq_cst);
    memcpy(in->xrgb,tile,sizeof(in->xrgb));
    atomic_store_explicit(&in->seq,seq,memory_order_release);
}
#endif

static void ai_draw(struct surface *s,unsigned ch,double timestamp) {
    if (!ai) return;
    const int x=MONITOR_X+(ch%2)*MONITOR_STEP_X, y=MONITOR_Y+(ch/2)*MONITOR_STEP_Y;
    const struct ai_output *out=&ai->outputs[ch];
    uint32_t first=atomic_load_explicit(&out->seq,memory_order_acquire);
    struct ai_output snapshot;
    memcpy(&snapshot,out,sizeof(snapshot));
    atomic_thread_fence(memory_order_acquire);
    const char *status = ch < 2 ? "Vehicles" : "Pedestrians";
    if (!(first&1) && first==atomic_load_explicit(&out->seq,memory_order_acquire) &&
        snapshot.valid_until_ns > (uint64_t)(timestamp*1e9)) {
        snapshot.status[sizeof(snapshot.status)-1]=0;
        status=snapshot.status;
        for (unsigned i=0;i<snapshot.count && i<AI_MAX_BOXES;i++) {
            struct ai_box *b=&snapshot.boxes[i];
            if(b->x1<0 || b->y1<0 || b->x2>=AI_W || b->y2>=AI_H ||
               b->x2<=b->x1 || b->y2<=b->y1) continue;
            int x1=x+b->x1*MONITOR_W/AI_W, y1=y+b->y1*MONITOR_H/AI_H;
            int width=x+b->x2*MONITOR_W/AI_W-x1;
            int height=y+b->y2*MONITOR_H/AI_H-y1;
            if(width<2 || height<2) continue;
            box(s,x1,y1,width,2,b->color);
            box(s,x1,y1+height-2,width,2,b->color);
            box(s,x1,y1,2,height,b->color);
            box(s,x1+width-2,y1,2,height,b->color);
            b->label[sizeof(b->label)-1]=0;
            int text_width=(int)strlen(b->label)*12+12;
            if(text_width>MONITOR_W) text_width=MONITOR_W;
            int left=x1;
            if(left+text_width>x+MONITOR_W) left=x+MONITOR_W-text_width;
            int top=y1>=y+27 ? y1-27 : y1;
            if(top+27>y+MONITOR_H) top=y+MONITOR_H-27;
            box(s,left,top,text_width,27,0x172031);
            text_at(s,left+4,top+22,b->label);
        }
    }
    if (status == snapshot.status && snapshot.count == 0) return;
    if (status != snapshot.status) return;
    box(s,x+8,y+7,260,27,0x172031);
    text_at(s,x+14,y+29,status);
}
