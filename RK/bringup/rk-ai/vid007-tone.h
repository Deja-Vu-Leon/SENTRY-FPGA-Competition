#include <math.h>

enum { TONE_X=521,TONE_STEP=221,TONE_W=190,TONE_SLIDER_Y=959,TONE_FIELDS=5 };
static const int tone_min[TONE_FIELDS]={-100,0,0,-180,25};
static const int tone_max[TONE_FIELDS]={100,200,200,180,300};
static const int tone_default[TONE_FIELDS]={0,100,100,0,100};
static int tone_values[4][TONE_FIELDS]={
    {0,100,100,0,100},{0,100,100,0,100},{0,100,100,0,100},{0,100,100,0,100}
};
static unsigned tone_revision;
static int parameter_focus=-1, parameter_drag=-1, parameter_draft;
static char parameter_text[8];

static unsigned tone_byte(float value) {
    return value<=0?0:value>=255?255:(unsigned)(value+.5f);
}

struct tone_transform {
    int last[TONE_FIELDS], bias;
    int16_t matrix[3][3];
    uint8x16_t base,delta;
};

static void tone_prepare(struct tone_transform *t,const int *v) {
    memcpy(t->last,v,sizeof(t->last));
    const float luma[]={.114f,.587f,.299f}, i[]={-.321f,-.275f,.596f}, q[]={.311f,-.523f,.212f};
    const float decode_i[]={-1.106f,-.272f,.956f}, decode_q[]={1.703f,-.647f,.621f};
    const float angle=v[3]*.01745329252f;
    const float a=cosf(angle)*v[2]/100.f,b=sinf(angle)*v[2]/100.f;
    const float contrast=v[1]/100.f;
    t->bias=lroundf(256.f*(127.5f*(1.f-contrast)+1.275f*v[0]));
    for(int out=0;out<3;out++) for(int in=0;in<3;in++) {
        float weight=i[in]*(a*decode_i[out]+b*decode_q[out])+
                     q[in]*(a*decode_q[out]-b*decode_i[out]);
        t->matrix[out][in]=lroundf(256.f*(luma[in]*contrast+weight));
    }
    uint8_t base[16],delta[16];
    for(unsigned k=0;k<16;k++) {
        base[k]=tone_byte(255.f*powf(16.f*k/255.f,100.f/v[4]));
        unsigned end=tone_byte(255.f*powf(fminf(255.f,16.f*(k+1))/255.f,100.f/v[4]));
        delta[k]=end-base[k];
    }
    t->base=vld1q_u8(base);
    t->delta=vld1q_u8(delta);
}

static uint8x8_t tone_curve(uint8x8_t pixels,const struct tone_transform *t) {
    uint8x8_t index=vshr_n_u8(pixels,4);
    uint8x8_t fraction=vand_u8(pixels,vdup_n_u8(15));
    uint8x8_t offset=vrshrn_n_u16(vmull_u8(fraction,vqtbl1_u8(t->delta,index)),4);
    return vbsl_u8(vceq_u8(pixels,vdup_n_u8(255)),vdup_n_u8(255),
                   vadd_u8(vqtbl1_u8(t->base,index),offset));
}

static void tone_apply(uint32_t *tile,unsigned ch) {
    static struct tone_transform transforms[4];
    const int *v=tone_values[ch];
    if(!memcmp(v,tone_default,sizeof(tone_default))) return;
    struct tone_transform *t=&transforms[ch];
    if(memcmp(t->last,v,sizeof(t->last))) tone_prepare(t,v);
    const int per_component=v[2]==100 && v[3]==0 && v[1]==100;
    const int shift=(int)lroundf(1.275f*v[0]);
    if(per_component && v[4]==100) {
        unsigned step=(unsigned)abs(shift);
        uint8x16_t offset=vreinterpretq_u8_u32(vdupq_n_u32(step*0x010101u));
        uint8_t *row=(uint8_t *)tile;
        for(unsigned i=0;i<TILE_W*TILE_H*4;i+=16) {
            uint8x16_t p=vld1q_u8(row+i);
            vst1q_u8(row+i,shift>=0?vqaddq_u8(p,offset):vqsubq_u8(p,offset));
        }
        return;
    }
    const uint8x8_t amount=vdup_n_u8((uint8_t)abs(shift));
    for(unsigned px=0;px<TILE_W*TILE_H;px+=8) {
        uint8_t *row=(uint8_t *)(tile+px);
        uint8x8x4_t color=vld4_u8(row), output=color;
        if(per_component) {
            for(unsigned k=0;k<3;k++)
                output.val[k]=shift>=0?vqadd_u8(color.val[k],amount):vqsub_u8(color.val[k],amount);
        } else {
            int16x8_t input[3];
            for(unsigned j=0;j<3;j++) input[j]=vreinterpretq_s16_u16(vmovl_u8(color.val[j]));
            for(unsigned k=0;k<3;k++) {
                int32x4_t low=vdupq_n_s32(t->bias),high=low;
                for(unsigned j=0;j<3;j++) {
                    int16x8_t a=input[j];
                    low=vmlal_n_s16(low,vget_low_s16(a),t->matrix[k][j]);
                    high=vmlal_n_s16(high,vget_high_s16(a),t->matrix[k][j]);
                }
                output.val[k]=vqmovun_s16(vcombine_s16(vqrshrn_n_s32(low,8),vqrshrn_n_s32(high,8)));
            }
        }
        if(v[4]!=100)
            for(unsigned k=0;k<3;k++) output.val[k]=tone_curve(output.val[k],t);
        vst4_u8(row,output);
    }
}
