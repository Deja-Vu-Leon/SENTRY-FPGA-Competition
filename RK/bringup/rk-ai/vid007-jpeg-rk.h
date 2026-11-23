#include <libavcodec/avcodec.h>
#include <libavutil/error.h>
#include "vid007-jpeg-scan.h"

enum { JPEG_DEPTH=3, JPEG_LIMIT=PIXELS, JPEG_HEADER=55, JPEG_POOL=JPEG_DEPTH+2 };
struct jpeg_input {
    uint8_t bytes[JPEG_LIMIT+AV_INPUT_BUFFER_PADDING_SIZE];
    unsigned length,id,scale;
    double submitted;
};
struct jpeg_channel {
    pthread_mutex_t mutex;
    pthread_cond_t ready;
    pthread_t thread;
    struct jpeg_input storage[JPEG_POOL];
    struct jpeg_input *queued[JPEG_DEPTH], *input, *decode;
    unsigned head,count;
    int alive,running;
    AVCodecContext *context;
    AVFrame *picture;
    uint8_t token_buffer[JPEG_LIMIT];
    struct ui_times elapsed, waiting;
    atomic_uint decoded,rejected,discarded,depth,decode_p95,wait_p95;
};
static struct jpeg_channel jpeg[4];

static unsigned write_jpeg_header(uint8_t *dest,unsigned width,unsigned height,unsigned pt) {
    const uint8_t header[]={
        0xff,0xd8,0xff,0xc3,0,11,8,height>>8,height,width>>8,width,1,1,0x11,0,
        0xff,0xc4,0,28,0,
        1,0,0,7,1,0,0,0,0,0,0,0,0,0,0,0,
        0,1,2,3,4,5,6,7,8,
        0xff,0xda,0,8,1,1,0,1,0,pt
    };
    _Static_assert(sizeof(header)==JPEG_HEADER,"SOF3 header length");
    memcpy(dest,header,sizeof(header));
    return sizeof(header);
}

static int jpeg_decode_frame(struct jpeg_channel *channel,unsigned number,const struct jpeg_input *input) {
    unsigned width=1920u>>input->scale,height=1080u>>input->scale;
    unsigned point=input->bytes[JPEG_HEADER-1];
    if(!getenv("VID007_FFMPEG_REFERENCE"))
        return vid007_decode_scan(input->bytes+JPEG_HEADER,input->length-JPEG_HEADER-2,
                                  channel->token_buffer,assembling[number],width,height,point);
    AVPacket packet={.data=(uint8_t *)input->bytes,.size=(int)input->length};
    av_frame_unref(channel->picture);
    int rc=avcodec_send_packet(channel->context,&packet);
    if(rc>=0) rc=avcodec_receive_frame(channel->context,channel->picture);
    AVFrame *picture=channel->picture;
    if(rc<0 || picture->width!=(int)width || picture->height!=(int)height ||
       picture->format!=AV_PIX_FMT_GRAY8 || picture->linesize[0]<(int)width ||
       (picture->flags&AV_FRAME_FLAG_CORRUPT) || picture->decode_error_flags) {
        avcodec_flush_buffers(channel->context);
        return -1;
    }
    for(unsigned row=0;row<height;row++)
        memcpy(assembling[number]+row*width,picture->data[0]+row*picture->linesize[0],width);
    return 0;
}

static unsigned jpeg_worker_cpu(unsigned number) {
    unsigned rank=0;
    for(unsigned ch=0;ch<4;ch++) {
        unsigned codec=atomic_load(&jpeg_live[ch])&3u;
        unsigned config=atomic_load(&live_config[ch]);
        if(codec!=1 || resolution(config)!=0) continue;
        if(ch==number && rank<2) return 4+rank;
        rank++;
    }
    return number;
}

static void *jpeg_worker(void *data) {
    struct jpeg_channel *channel=data;
    unsigned number=channel-jpeg;
    cpu_set_t cpus;
    CPU_ZERO(&cpus);
    CPU_SET(number,&cpus);
    pthread_setaffinity_np(pthread_self(),sizeof(cpus),&cpus);
    unsigned cpu=number;
    double next_summary=0;
    pthread_mutex_lock(&channel->mutex);
    while(channel->alive) {
        if(!channel->count) {
            pthread_cond_wait(&channel->ready,&channel->mutex);
            continue;
        }
        unsigned head=channel->head;
        struct jpeg_input *input=channel->queued[head];
        channel->queued[head]=channel->decode;
        channel->decode=input;
        channel->head=(head+1)%JPEG_DEPTH;
        channel->count--;
        channel->running=1;
        atomic_store(&channel->depth,channel->count);
        pthread_mutex_unlock(&channel->mutex);

        unsigned target_cpu=jpeg_worker_cpu(number);
        if(cpu!=target_cpu) {
            CPU_ZERO(&cpus);
            CPU_SET(target_cpu,&cpus);
            if(!pthread_setaffinity_np(pthread_self(),sizeof(cpus),&cpus)) cpu=target_cpu;
        }
        double start=now();
        int ok=jpeg_decode_frame(channel,number,input)==0;
        double finish=now();

        pthread_mutex_lock(&channel->mutex);
        if(ok) {
            atomic_fetch_add(&channel->decoded,1);
            present_frame(number,input->id);
        } else atomic_fetch_add(&channel->rejected,1);
        ui_sample(&channel->elapsed,1000*(finish-start));
        ui_sample(&channel->waiting,1000*(start-input->submitted));
        if(finish>=next_summary) {
            atomic_store(&channel->decode_p95,(unsigned)(100*ui_percentile(&channel->elapsed,95)));
            atomic_store(&channel->wait_p95,(unsigned)(100*ui_percentile(&channel->waiting,95)));
            next_summary=finish+1;
        }
        channel->running=0;
        pthread_cond_broadcast(&channel->ready);
    }
    pthread_mutex_unlock(&channel->mutex);
    return NULL;
}

static void jpeg_reset(void) {
    for(unsigned ch=0;ch<4;ch++) {
        struct jpeg_channel *channel=&jpeg[ch];
        pthread_mutex_lock(&channel->mutex);
        channel->head=channel->count=0;
        atomic_store(&channel->depth,0);
        while(channel->running) pthread_cond_wait(&channel->ready,&channel->mutex);
        pthread_mutex_unlock(&channel->mutex);
    }
}

static int jpeg_open(void) {
    const AVCodec *codec=avcodec_find_decoder(AV_CODEC_ID_MJPEG);
    if(!codec) return -1;
    for(unsigned ch=0;ch<4;ch++) {
        struct jpeg_channel *channel=&jpeg[ch];
        channel->context=avcodec_alloc_context3(codec);
        channel->picture=av_frame_alloc();
        if(!channel->context || !channel->picture) return -1;
        channel->context->err_recognition=AV_EF_EXPLODE|AV_EF_CAREFUL|AV_EF_BITSTREAM;
        channel->context->max_pixels=PIXELS;
        channel->context->thread_count=1;
        if(avcodec_open2(channel->context,codec,NULL)<0) return -1;
        pthread_mutex_init(&channel->mutex,NULL);
        pthread_cond_init(&channel->ready,NULL);
        for(unsigned idx=0;idx<JPEG_DEPTH;idx++) channel->queued[idx]=&channel->storage[idx];
        channel->input=&channel->storage[JPEG_DEPTH];
        channel->decode=&channel->storage[JPEG_DEPTH+1];
        channel->alive=1;
        if(pthread_create(&channel->thread,NULL,jpeg_worker,channel)) return -1;
    }
    return 0;
}

static void jpeg_close(void) {
    for(unsigned ch=0;ch<4;ch++) {
        struct jpeg_channel *channel=&jpeg[ch];
        pthread_mutex_lock(&channel->mutex);
        channel->alive=0;
        pthread_cond_signal(&channel->ready);
        pthread_mutex_unlock(&channel->mutex);
        pthread_join(channel->thread,NULL);
        avcodec_free_context(&channel->context);
        av_frame_free(&channel->picture);
        pthread_mutex_destroy(&channel->mutex);
        pthread_cond_destroy(&channel->ready);
    }
}

static void jpeg_append(unsigned ch,unsigned offset,const uint8_t *bytes,unsigned length) {
    if(offset+length<=JPEG_LIMIT-JPEG_HEADER-2)
        memcpy(jpeg[ch].input->bytes+JPEG_HEADER+offset,bytes,length);
}

static int jpeg_publish(unsigned ch,unsigned id,unsigned payload_bytes,unsigned meta,unsigned codec) {
    struct jpeg_channel *channel=&jpeg[ch];
    unsigned bytes=meta&0x3fffffu,pt=(meta>>22)&7u;
    if((meta>>25)!=0x55 || !bytes || bytes>JPEG_LIMIT-JPEG_HEADER-2 ||
       bytes>payload_bytes || payload_bytes-bytes>15 || (codec==1 && pt!=0) || (codec==2 && pt==0)) {
        atomic_fetch_add(&channel->rejected,1);
        return -1;
    }
    struct jpeg_input *input=channel->input;
    unsigned scale=dimensions[ch];
    write_jpeg_header(input->bytes,1920u>>scale,1080u>>scale,pt);
    input->bytes[JPEG_HEADER+bytes]=0xff;
    input->bytes[JPEG_HEADER+bytes+1]=0xd9;
    input->length=JPEG_HEADER+bytes+2;
    input->scale=scale;
    input->id=id;
    input->submitted=now();
    memset(input->bytes+input->length,0,AV_INPUT_BUFFER_PADDING_SIZE);
    atomic_store(&jpeg_actual[ch],pt);
    atomic_store(&jpeg_bytes[ch],bytes);
    pthread_mutex_lock(&channel->mutex);
    if(channel->count==JPEG_DEPTH) {
        channel->head=(channel->head+1)%JPEG_DEPTH;
        channel->count--;
        atomic_fetch_add(&channel->discarded,1);
    }
    unsigned slot=(channel->head+channel->count)%JPEG_DEPTH;
    channel->input=channel->queued[slot];
    channel->queued[slot]=input;
    channel->count++;
    atomic_store(&channel->depth,channel->count);
    pthread_cond_signal(&channel->ready);
    pthread_mutex_unlock(&channel->mutex);
    return 0;
}
