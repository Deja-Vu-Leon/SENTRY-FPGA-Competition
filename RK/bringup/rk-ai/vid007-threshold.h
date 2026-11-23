/* Estimate a per-camera FPGA threshold from sampled luminance. */
enum { THRESHOLD_AUTO_X=44, THRESHOLD_AUTO_Y=904, THRESHOLD_AUTO_W=159, THRESHOLD_AUTO_H=36 };

struct threshold_feedback {
    int manual, manual_level, white, estimate, probing;
    unsigned applied, target, probe_config;
    double sample_after, estimated_at;
};
static struct threshold_feedback threshold_feedback[4];

static int threshold_active(unsigned config) {
    return (config&0x74u)==0x20u;
}

static unsigned threshold_value(unsigned config,int value) {
    return (config&255u)|((unsigned)value<<8);
}

static unsigned threshold_probe(unsigned ch,unsigned target) {
    struct threshold_feedback *state=&threshold_feedback[ch];
    state->probing=1;
    state->white=-1;
    state->target=target;
    state->probe_config=(target&~0x77u)|1u|(target&2u);
    return state->probe_config;
}

static unsigned threshold_select(unsigned ch,unsigned target) {
    struct threshold_feedback *state=&threshold_feedback[ch];
    state->white=-1;
    state->probing=0;
    if(state->manual) return threshold_value(target,state->manual_level);
    if(!(target&2u) && state->estimated_at>0 && now()-state->estimated_at<4.)
        return threshold_value(target,state->estimate);
    return threshold_probe(ch,target);
}

static void threshold_use_auto(unsigned ch) {
    threshold_feedback[ch].manual=0;
    unsigned target=atomic_load(&requested_config[ch]);
    atomic_store(&requested_config[ch],threshold_probe(ch,target));
}

static void threshold_update(unsigned ch,const uint8_t *pixels,unsigned scale,
                             unsigned config,double timestamp) {
    struct threshold_feedback *state=&threshold_feedback[ch];
    unsigned requested=atomic_load(&requested_config[ch]);
    if(state->probing && requested!=state->probe_config) state->probing=0;
    if(config!=requested) return;
    if(state->applied!=config) {
        state->applied=config;
        state->white=-1;
        state->sample_after=timestamp+.18;
        return;
    }
    if(timestamp<state->sample_after) return;
    state->sample_after=timestamp+.40;
    const unsigned width=1920u>>scale,height=1080u>>scale;
    const unsigned processing=config&0x77u;
    const int mask=threshold_active(config), bayer=processing==0;
    if(!mask && !bayer && processing!=1 && !state->probing) {
        state->estimated_at=0;
        return;
    }
    unsigned histogram[256]={0},bright=0,count=0;
    for(unsigned y=12;y+13<height;y+=19)
        for(unsigned x=12;x+13<width;x+=17) {
            const uint8_t *p=pixels+y*width+x;
            unsigned luma=bayer?(p[0]+p[1]+p[width]+p[width+1])/4:p[0];
            if(mask) bright+=luma>=128;
            else histogram[luma]++;
            count++;
        }
    if(mask) {
        state->white=(int)((1000*bright+count/2)/count);
        return;
    }
    int best=1,best_error=2001;
    unsigned white=count;
    for(int level=1;level<=255;level++) {
        white-=histogram[level-1];
        int error=abs((int)((1000*white+count/2)/count)-400);
        if(!white || white==count) error+=1000;
        if(error<best_error) { best=level; best_error=error; }
    }
    state->estimate=best;
    state->estimated_at=timestamp;
    if(state->probing) {
        state->probing=0;
        atomic_store(&requested_config[ch],threshold_value(state->target,best));
    }
}
