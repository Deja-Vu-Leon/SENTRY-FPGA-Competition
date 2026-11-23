#include <arm_neon.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <sys/ioctl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <sched.h>
#include <semaphore.h>
#include <sys/resource.h>

enum { WIDTH = 1680, HEIGHT = 1050, TILE_W = 840, TILE_H = 472, DEPTH = 8 };
struct display_frame { uint32_t id; unsigned scale; double received; uint8_t *data; };
static uint8_t *assembling[4];
static uint8_t pool[4][DEPTH+2][PIXELS];
static struct {
    pthread_mutex_t mutex;
    struct display_frame frames[DEPTH];
    unsigned head, queued;
    double last_frame;
    uint64_t overrun;
} queues[4];
static pthread_t screen_thread;
static atomic_int screen_running;
static atomic_int screen_ready;

static void present_packet(unsigned channel, unsigned offset, const uint8_t *pixels, unsigned length) {
    unsigned size = channel_payload(channel,receive_mode);
    if (offset >= size) return;
    if (length > size - offset) length = size - offset;
    memcpy(assembling[channel]+offset,pixels,length);
}
static void present_frame(unsigned channel, uint32_t id) {
    pthread_mutex_lock(&queues[channel].mutex);
    if (queues[channel].queued == DEPTH) {
        queues[channel].head = (queues[channel].head + 1) % DEPTH;
        queues[channel].queued--;
        queues[channel].overrun++;
    }
    unsigned position = (queues[channel].head + queues[channel].queued) % DEPTH;
    struct display_frame *frame=&queues[channel].frames[position];
    frame->scale=dimensions[channel];
    uint8_t *spare=frame->data;
    frame->data=assembling[channel];
    assembling[channel]=spare;
    queues[channel].frames[position].id = id;
    queues[channel].frames[position].received = now();
    queues[channel].queued++;
    queues[channel].last_frame = now();
    pthread_mutex_unlock(&queues[channel].mutex);
}

struct white_balance {
    unsigned red, blue;
    unsigned shadow_lift;
    unsigned hdr_mode;
    double next_sample;
};

static unsigned limit_gain(unsigned gain) {
    if (gain < 160) return 160;
    if (gain > 896) return 896;
    return gain;
}

static void update_white_balance(struct white_balance *wb, const uint8_t *raw,
                                 unsigned camera,double timestamp,unsigned width,unsigned height,unsigned hdr_mode) {
    if(wb->hdr_mode!=hdr_mode) *wb=(struct white_balance){.hdr_mode=hdr_mode};
    unsigned offset=hdr_mode?0:4;
    if (timestamp < wb->next_sample) return;
    wb->next_sample = timestamp + 0.5;
    unsigned red = 0, green = 0, blue = 0, count = 0;
    for (unsigned y = 8; y+8 < height; y += 16)
        for (unsigned x = 8; x+8 < width; x += 16) {
            const uint8_t *top = raw + y * width + x;
            const uint8_t *bottom = top + width;
            unsigned g = (top[0] + bottom[1] + 1) >> 1;
            unsigned min_green=hdr_mode?5:12;
            unsigned min_color=hdr_mode?2:4;
            if (g < min_green || g > 200 || top[1] < min_color || bottom[0] < min_color ||
                top[1] > 235 || bottom[0] > 235 ||
                abs((int)top[0] - bottom[1]) > 12) continue;
            if (bottom[0] <= offset || top[1] <= offset) continue;
            red += bottom[0] - offset;
            green += g - offset;
            blue += top[1] - offset;
            count++;
        }
    if (count >= 32 && red && blue) {
        if(camera!=0 && !hdr_mode) {
            const unsigned max_lift[]={0,24,34,32};
            unsigned mean=green/count;
            unsigned strength=mean<=16?32:mean>=48?0:48-mean;
            unsigned target=(max_lift[camera]*strength+16)/32;
            wb->shadow_lift=(wb->shadow_lift+target+1)/2;
        }
        unsigned target_r = limit_gain((green * 256 + red / 2) / red);
        unsigned target_b = limit_gain((green * 256 + blue / 2) / blue);
        if (!wb->red || abs((int)wb->red - (int)target_r) >= 4 ||
            abs((int)wb->blue - (int)target_b) >= 4) {
            wb->red = wb->red ? (3 * wb->red + target_r + 2) / 4 : target_r;
            wb->blue = wb->blue ? (3 * wb->blue + target_b + 2) / 4 : target_b;
            fprintf(stderr, "White balance camera=%u samples=%u RGB=%.2f/%.2f/%.2f gains=%.3f/1/%.3f\n",
                    camera, count, (double)red/count, (double)green/count, (double)blue/count,
                    wb->red/256.0, wb->blue/256.0);
        }
    }

}

#include "vid007-tone.h"
#include "vid007-a01-profile.h"
#include "vid007-b01-profile.h"

/* Shared RGB curve: lift the darker codes with a gentle highlight shoulder. */
static uint8x8_t lift_shadows(uint8x8_t sample,unsigned hdr_mode) {
    uint8x8_t twice=vqadd_u8(sample,sample);
    uint8x8_t rise=hdr_mode?twice:vqadd_u8(twice,sample);
    uint8x8_t headroom=vshr_n_u8(vmvn_u8(sample),1);
    rise=vmin_u8(rise,vdup_n_u8(hdr_mode?48:64));
    return vadd_u8(sample,vmin_u8(rise,headroom));
}

static unsigned colour_gain(const unsigned gain) {
    return ((gain?gain:256)+2)/4;
}

/* Correct weak green excess in shadows and lift RGB together to preserve hue. */
static inline void lowlight_colour(uint8x8x4_t *pixel,uint8x8_t cap,uint8x8_t tint_cap) {
    uint8x8_t blue=pixel->val[0],green=pixel->val[1],red=pixel->val[2];
    uint8x8_t rb_mid=vrhadd_u8(red,blue);
    uint8x8_t excess=vqsub_u8(green,rb_mid);
    uint8x8_t spread=vabd_u8(red,blue);
    uint8x8_t confidence=vqsub_u8(vdup_n_u8(32),vmax_u8(excess,spread));
    uint8x8_t peak=vmax_u8(vmax_u8(red,blue),green);
    uint8x8_t dark_limit=vshr_n_u8(vqsub_u8(vdup_n_u8(144),peak),2);
    uint8x8_t trim=vsub_u8(excess,vshr_n_u8(excess,2));
    green=vsub_u8(green,vmin_u8(trim,vmin_u8(confidence,vmin_u8(dark_limit,tint_cap))));
    uint8x8_t luminance=vrhadd_u8(rb_mid,green);
    uint8x8_t headroom=vshr_n_u8(vqsub_u8(vdup_n_u8(176),peak),2);
    uint8x8_t lift=vmin_u8(vshr_n_u8(luminance,1),vmin_u8(cap,headroom));
    pixel->val[0]=vadd_u8(blue,lift);
    pixel->val[1]=vadd_u8(green,lift);
    pixel->val[2]=vadd_u8(red,lift);
}

static void render_tile(uint32_t *tile, const uint8_t *raw, unsigned mode,
                        const struct white_balance *wb,unsigned scale,unsigned hdr_mode,
                        unsigned channel) {
    unsigned offset=hdr_mode?0:4;
    const unsigned width=1920u>>scale, height=1080u>>scale;
    if (mode & 5) {
        unsigned shift = !!(mode & 4) + ((mode & 2) ? ((mode & 1) ? 1 : 2) : 0);
        for (unsigned y = 0; y < TILE_H; y++)
            for (unsigned x = 0; x < TILE_W; x++) {
                unsigned iy = y * height / TILE_H + shift;
                unsigned ix = x * width / TILE_W + shift;
                unsigned offset = iy * width + ix;
                unsigned level = 0;
                if (ix < width && iy < height)
                    level = mode & 4 ? 255 * ((raw[offset / 8] >> (offset % 8)) & 1) : raw[offset];
                tile[y * TILE_W + x] = 0x010101 * level;
            }
        return;
    }
    // The VID007 reference uses GBRG. Convert eight Bayer cells at once.
    static unsigned maps[3][TILE_W];
    unsigned *map_x=maps[scale];
    if (!map_x[TILE_W-1])
        for (unsigned x = 0; x < TILE_W; x++) map_x[x] = x * (width/2) / TILE_W;
    unsigned shift = (mode & 2) ? 2 : 0;
    const uint8x8_t red_gain=vdup_n_u8(colour_gain(wb->red));
    const uint8x8_t blue_gain=vdup_n_u8(colour_gain(wb->blue));
    const uint8x8_t pedestal=vdup_n_u8(offset);
    const int profile=channel==0 && mode==0 && !hdr_mode;
    const int b01_profile=channel==2 && mode==0 && !hdr_mode;
    const unsigned lift=channel!=0 && mode==0 && !hdr_mode?wb->shadow_lift:0;
    const uint8x8_t lift_cap=vdup_n_u8(lift);
    const uint8x8_t tint_cap=vdup_n_u8((lift+1)/2);
    const uint8x16_t base_b=vld1q_u8(b01_profile?b01_blue_base:a01_blue_base);
    const uint8x16_t delta_b=vld1q_u8(b01_profile?b01_blue_delta:a01_blue_delta);
    const uint8x16_t base_g=vld1q_u8(b01_profile?b01_green_base:a01_green_base);
    const uint8x16_t delta_g=vld1q_u8(b01_profile?b01_green_delta:a01_green_delta);
    const uint8x16_t base_r=vld1q_u8(b01_profile?b01_red_base:a01_red_base);
    const uint8x16_t delta_r=vld1q_u8(b01_profile?b01_red_delta:a01_red_delta);
    uint32_t row[960];
    for (unsigned y = 0; y < TILE_H; y++) {
        unsigned source_y=2*(y*(height/2)/TILE_H)+shift;
        if(source_y+1>=height) source_y=height-2;
        const uint8_t *top=raw+source_y*width;
        const uint8_t *bottom = top + width;
        for (unsigned x = 0; x+7 < width/2; x += 8) {
            uint8x8x2_t t = vld2_u8(top + 2*x);
            uint8x8x2_t b = vld2_u8(bottom + 2*x);
            uint8x8_t red=vqsub_u8(b.val[0],pedestal);
            uint8x8_t green=vqsub_u8(vrhadd_u8(t.val[0],b.val[1]),pedestal);
            uint8x8_t blue=vqsub_u8(t.val[1],pedestal);
            uint8x8x4_t pixel = {{
                lift_shadows(vqmovn_u16(vrshrq_n_u16(vmull_u8(blue,blue_gain),6)),hdr_mode),
                lift_shadows(green,hdr_mode),
                lift_shadows(vqmovn_u16(vrshrq_n_u16(vmull_u8(red,red_gain),6)),hdr_mode),
                vdup_n_u8(0)
            }};
            if(lift) lowlight_colour(&pixel,lift_cap,tint_cap);
            if(profile || b01_profile) {
                pixel.val[0]=a01_curve(pixel.val[0],base_b,delta_b);
                pixel.val[1]=a01_curve(pixel.val[1],base_g,delta_g);
                pixel.val[2]=a01_curve(pixel.val[2],base_r,delta_r);
            }
            vst4_u8((uint8_t *)(row+x),pixel);
        }
        /* All supported source widths (1920 / 960 / 480) hold whole SIMD groups. */
        for (unsigned x = 0; x < TILE_W; x++) {
            unsigned col = map_x[x] + shift / 2;
            tile[y * TILE_W + x] = row[col < width/2 ? col : width/2-1];
        }
    }
}

struct surface {
    uint32_t fb, handle, pitch;
    size_t bytes;
    uint8_t *memory;
    unsigned page,background,play_sequence;
    int cursor_x,cursor_y,cursor_saved;
    uint32_t behind_cursor[14][9];
};

static void copy_cursor_background(struct surface *s,int save) {
    for(int y=0;y<14;y++) {
        uint8_t *row=s->memory+(s->cursor_y+y)*s->pitch+s->cursor_x*4;
        if(save) memcpy(s->behind_cursor[y],row,sizeof(s->behind_cursor[y]));
        else memcpy(row,s->behind_cursor[y],sizeof(s->behind_cursor[y]));
    }
}
static int create_surface(int fd, struct surface *s) {
    struct drm_mode_create_dumb create = {.width=WIDTH, .height=HEIGHT, .bpp=32};
    if (ioctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &create)) return -1;
    s->handle=create.handle;
    s->pitch=create.pitch;
    s->bytes=create.size;
    if (drmModeAddFB(fd, WIDTH, HEIGHT, 24, 32, s->pitch, s->handle, &s->fb)) return -1;
    struct drm_mode_map_dumb map = {.handle=s->handle};
    if (ioctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map)) return -1;
    s->memory=mmap(NULL, s->bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map.offset);
    return s->memory == MAP_FAILED ? -1 : 0;
}
#include "vid007-cockpit-state.h"
#include "vid007-cockpit-controls.h"

#include "vid007-cockpit-chrome.h"
#include "vid007-jpeg-rk.h"
#include "vid007-cockpit-panel.h"

static void text_at(struct surface *s,int x,int baseline,const char *label) {
    wchar_t wide[44];
    mbstate_t state={0};
    size_t used=0, remaining=strlen(label);
    while(remaining && used+1<sizeof(wide)/sizeof(*wide)) {
        size_t bytes=mbrtowc(&wide[used],label,remaining,&state);
        if(bytes==(size_t)-1 || bytes==(size_t)-2) break;
        label+=bytes;
        remaining-=bytes;
        used++;
    }
    wide[used]=0;
    rk_label(s,x,baseline,wide,0xf1f5f9);
}

#define VID007_HAZARD_DETAIL
#include "vid007-armour-overlay.h"
struct tile_job {
    uint32_t *tile;
    const uint8_t *raw;
    struct white_balance *balance;
    double frame_time;
    unsigned channel,mode,scale,hdr;
    int inference,record;
};

static void convert_tile(const struct tile_job *job) {
    if(!job->tile) return;
    if(!(job->mode&5))
        update_white_balance(job->balance,job->raw,job->channel,job->frame_time,
                             1920u>>job->scale,1080u>>job->scale,job->hdr);
    render_tile(job->tile,job->raw,job->mode,job->balance,job->scale,job->hdr,job->channel);
    if(job->inference) {
        ai_publish(job->channel,job->tile);
        ai_publish_detail(job->channel,job->tile,job->frame_time);
    }
    tone_apply(job->tile,job->channel);
    if(job->record) publish_thumbnail(&record_inputs[job->channel],job->tile);
}

struct tile_converter {
    sem_t ready,done;
    pthread_t thread;
    const struct tile_job *jobs;
    int stopping;
};

static void wait_converter(sem_t *event) {
    while(sem_wait(event)<0 && errno==EINTR) {}
}

static void *convert_pair(void *arg) {
    struct tile_converter *worker=arg;
    cpu_set_t cpus;
    CPU_ZERO(&cpus);
    CPU_SET(5,&cpus);
    pthread_setaffinity_np(pthread_self(),sizeof(cpus),&cpus);
    setpriority(PRIO_PROCESS,0,-5);
    for(;;) {
        wait_converter(&worker->ready);
        if(worker->stopping) break;
        convert_tile(worker->jobs);
        convert_tile(worker->jobs+1);
        sem_post(&worker->done);
    }
    return NULL;
}

static int converter_start(struct tile_converter *worker) {
    if(sem_init(&worker->ready,0,0)) return 0;
    if(sem_init(&worker->done,0,0)) {
        sem_destroy(&worker->ready);
        return 0;
    }
    if(!pthread_create(&worker->thread,NULL,convert_pair,worker)) return 1;
    sem_destroy(&worker->ready);
    sem_destroy(&worker->done);
    return 0;
}

static void converter_stop(struct tile_converter *worker) {
    worker->stopping=1;
    sem_post(&worker->ready);
    pthread_join(worker->thread,NULL);
    sem_destroy(&worker->ready);
    sem_destroy(&worker->done);
}
#include "vid007-cockpit-pages.h"
#include "vid007-armour-dashboard.h"

static void publish_mode(int mode) {
    for (unsigned ch = 0; ch < 4; ch++) pthread_mutex_lock(&queues[ch].mutex);
    for (unsigned ch = 0; ch < 4; ch++) {
        queues[ch].head = queues[ch].queued = 0;
        queues[ch].last_frame = 0;
    }
    atomic_store(&published_mode, mode);
    for (unsigned ch = 0; ch < 4; ch++) pthread_mutex_unlock(&queues[ch].mutex);
}

struct flip_state {
    int pending;
    unsigned front, queued, fresh;
    uint64_t flips, shown[4], submitted_count[4], skipped[4];
    uint32_t source_id[4], previous_id[4];
    unsigned have_id[4], mode;
    double submitted_at, last[4];
    struct ui_times intervals[4], latency[4], waits[4];
};
static void page_flipped(int fd, unsigned seq, unsigned sec, unsigned usec, void *data) {
    (void)fd; (void)seq; (void)sec; (void)usec;
    struct flip_state *flip = data;
    flip->pending = 0;
    flip->front = flip->queued;
    flip->flips++;
    const double displayed=now();
    for (unsigned i=0; i<4; i++) if((flip->fresh>>i)&1) {
        flip->shown[i]++;
        if(flip->last[i]) ui_sample(&flip->intervals[i],1000*(displayed-flip->last[i]));
        flip->last[i]=displayed;
        ui_sample(&flip->latency[i],1000*(displayed-flip->submitted_at));
        if(flip->have_id[i]) {
            unsigned delta=flip->mode&4 ? flip->source_id[i]-flip->previous_id[i] :
                                         (uint16_t)(flip->source_id[i]-flip->previous_id[i]);
            if(delta>0 && delta<4096) flip->skipped[i]+=delta-1;
        }
        flip->previous_id[i]=flip->source_id[i];
        flip->have_id[i]=1;
    }
}
static void *screen_main(void *unused) {
    (void)unused;
    cpu_set_t cpus;
    CPU_ZERO(&cpus);
    CPU_SET(6, &cpus);
    pthread_setaffinity_np(pthread_self(), sizeof(cpus), &cpus);
    int fd = drmOpen("rockchip", NULL);
    if (fd < 0) goto fail;
    if (drmSetMaster(fd)) goto fail_fd;
    drmModeRes *resources = drmModeGetResources(fd);
    if (!resources) goto fail_fd;
    drmModeConnector *connector = NULL;
    for (int i=0; i<resources->count_connectors; i++) {
        connector=drmModeGetConnector(fd, resources->connectors[i]);
        if (connector && connector->connector_type == DRM_MODE_CONNECTOR_HDMIA &&
            connector->connection == DRM_MODE_CONNECTED) break;
        drmModeFreeConnector(connector);
        connector=NULL;
    }
    if (!connector) goto fail_fd;
    int mode=0;
    while (mode < connector->count_modes &&
           (connector->modes[mode].hdisplay != WIDTH || connector->modes[mode].vdisplay != HEIGHT)) mode++;
    if (mode == connector->count_modes) { errno=ENODEV; goto fail_fd; }
    drmModeEncoder *encoder = drmModeGetEncoder(fd, connector->encoder_id);
    if (!encoder && connector->count_encoders) encoder=drmModeGetEncoder(fd, connector->encoders[0]);
    if (!encoder) goto fail_fd;
    uint32_t crtc=encoder->crtc_id;
    if (!crtc) for (int i=0; i<resources->count_crtcs; i++) {
        if (encoder->possible_crtcs & (1u<<i)) { crtc=resources->crtcs[i]; break; }
    }
    if (!crtc) { errno=ENODEV; goto fail_fd; }
    struct surface surfaces[2]={0};
    if (create_surface(fd,&surfaces[0]) || create_surface(fd,&surfaces[1])) goto fail_fd;
    uint32_t output=connector->connector_id;
    if (drmModeSetCrtc(fd,crtc,surfaces[0].fb,0,0,&output,1,&connector->modes[mode])) goto fail_fd;
    drmModeFreeEncoder(encoder);
    drmModeFreeConnector(connector);
    drmModeFreeResources(resources);
    drmEventContext events = {.version=DRM_EVENT_CONTEXT_VERSION, .page_flip_handler=page_flipped};
    struct flip_state flip={0};
    static uint32_t tiles[4][TILE_W*TILE_H];
    uint8_t *raw[4];
    for(unsigned ch=0;ch<4;ch++) raw[ch]=pool[ch][DEPTH+1];
    struct white_balance balance[4] = {0};
    double start=now();
    ui_started=start;
    for(unsigned ch=0;ch<4;ch++)
        ui_stats[ch].interval95=ui_stats[ch].latency50=ui_stats[ch].latency95=ui_stats[ch].wait95=-1;
    double alert_refresh=0;
    unsigned previous_event=~0u;
    int old_mode=-2;
    int primed[4] = {0};
    double next_ai[4] = {0};
    double record_poll=0,next_record[4]={0};
    int recording=0;
    ai_open();
    unsigned fps[4] = {0};
    struct controls ui = {.x=20, .y=20};
    struct tile_converter converter={0};
    const int threaded=converter_start(&converter);
    if (!FT_Init_FreeType(&font_library) &&
        !FT_New_Face(font_library, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0, &font))
        FT_Set_Pixel_Sizes(font, 0, 21);
    rk_font_init();
    atomic_store(&screen_ready,1);
    while (atomic_load(&screen_running)) {
        handle_input(&ui);
        if (!flip.pending) {
            int active = atomic_load(&published_mode);
            if (active != old_mode) {
                memset(tiles, 0, sizeof(tiles));
                memset(fps, 0, sizeof(fps));
                old_mode = active;
                memset(flip.have_id,0,sizeof(flip.have_id));
                memset(flip.last,0,sizeof(flip.last));
                memset(primed, 0, sizeof(primed));
            }
            const unsigned index=1-flip.front;
            struct surface *s=&surfaces[index];
            if(s->cursor_saved) {
                copy_cursor_background(s,0);
                s->cursor_saved=0;
            }
            unsigned fresh=0;
            unsigned offline = 0;
            struct tile_job jobs[4]={0};
            const double frame_time = now();
            if(frame_time>=record_poll) {
                recording=record_inputs && access("/run/sentry-vid007-ai/record.enabled",F_OK)==0;
                record_poll=frame_time+.2;
            }
            if (active >= 0) for (unsigned ch=0; ch<4; ch++) {
                pthread_mutex_lock(&queues[ch].mutex);
                if (frame_time - queues[ch].last_frame > 1.0) {
                    offline |= 1u << ch;
                    primed[ch] = 0;
                }
                if (queues[ch].queued >= 3) primed[ch] = 1;
                int new_image = primed[ch] && queues[ch].queued != 0 &&
                                atomic_load(&published_mode) == active;
                unsigned scale=0;
                if (new_image) {
                    struct display_frame *frame=&queues[ch].frames[queues[ch].head];
                    flip.source_id[ch]=frame->id;
                    ui_sample(&flip.waits[ch],1000*(frame_time-frame->received));
                    scale=frame->scale;
                    uint8_t *spare=raw[ch];
                    raw[ch]=frame->data;
                    frame->data=spare;
                    queues[ch].head=(queues[ch].head+1)%DEPTH;
                    queues[ch].queued--;
                }
                pthread_mutex_unlock(&queues[ch].mutex);
                if (offline & (1u << ch)) {
                    memset(tiles[ch], 0, sizeof(tiles[ch]));
                    fps[ch] = 0;
                }
                if (new_image) {
                    unsigned config=advanced_board?atomic_load(&live_config[ch]):0;
                    if(advanced_board) threshold_update(ch,raw[ch],scale,config,frame_time);
                    unsigned processing=advanced_board?config&0x77u:(unsigned)active;
                    unsigned render_mode=advanced_board?
                        (processing&0x74u ? (config&2u)|1u : config&3u):(unsigned)active;
                    if(scale) render_mode &= ~2u;
                    unsigned hdr_mode=(atomic_load(&hdr_live)>>ch)&1u;
                    int inference=ai && !processing && frame_time>=next_ai[ch];
                    int record=recording && frame_time>=next_record[ch];
                    jobs[ch]=(struct tile_job){tiles[ch],raw[ch],&balance[ch],frame_time,
                        ch,render_mode,scale,hdr_mode,inference,record};
                    if(inference) next_ai[ch]=frame_time+.15;
                    if(record) next_record[ch]=frame_time+.085;
                    fresh |= 1u<<ch;
                }
            }
            if(fresh&12u && threaded) {
                converter.jobs=jobs+2;
                sem_post(&converter.ready);
            }
            for(unsigned ch=0;ch<(threaded?2u:4u);ch++) convert_tile(&jobs[ch]);
            if(fresh&12u && threaded) wait_converter(&converter.done);
            if(!ui_page) armour_monitor(s,tiles,fps,active,offline,frame_time);
            if(!ui_page && active==0) for(unsigned ch=0;ch<4;ch++)
                if(!(offline&(1u<<ch)) && (!advanced_board || !(atomic_load(&live_config[ch])&0x77u)))
                    ai_draw(s,ch,frame_time);
            if(ui_page==3 && (frame_time>=alert_refresh || previous_event!=ui_event)) {
                ui_load_alerts(previous_event==ui_event);
                previous_event=ui_event;
                alert_refresh=frame_time+2;
            }
            rk_chrome(s,active,offline);
            if(!ui_page) cockpit_warning_banner(s,offline);
            if(ui_page<4) ui_panel(s,active,tiles,offline);
            else cockpit_page(s,tiles,fps,offline);
            if(ui_page) cockpit_warning_banner(s,offline);
            if(ui_page==3 || ui_page==6) fresh=0;
            if (ui.mouse) {
                if(ui_page==1 || ui_page==5) {
                    s->cursor_x=ui.x;
                    s->cursor_y=ui.y;
                    s->cursor_saved=1;
                    copy_cursor_background(s,1);
                }
                box(s,ui.x,ui.y,4,15,ARMOUR_PAPER);
                box(s,ui.x,ui.y,10,4,ARMOUR_PAPER);
                box(s,ui.x,ui.y,2,13,ARMOUR_NAVY);
                box(s,ui.x,ui.y,8,2,ARMOUR_NAVY);
            }
            s->page=ui_page;
            flip.queued=index;
            flip.fresh=fresh;
            if(active>=0) flip.mode=active;
            flip.submitted_at=now();
            for(unsigned ch=0;ch<4;ch++) flip.submitted_count[ch]+=(fresh>>ch)&1;
            if (drmModePageFlip(fd,crtc,s->fb,DRM_MODE_PAGE_FLIP_EVENT,&flip)) {
                perror("HDMI page flip");
                stopped=1;
                break;
            }
            flip.pending=1;
        }
        struct pollfd p={.fd=fd,.events=POLLIN};
        if (poll(&p,1,50)>0 && (p.revents & POLLIN)) drmHandleEvent(fd,&events);
        const double elapsed=now()-start;
        if (elapsed>=5) {
            printf("HDMI KMS flips %.2f/s mode=%d",flip.flips/elapsed,old_mode);
            for (unsigned ch=0; ch<4; ch++) {
                pthread_mutex_lock(&queues[ch].mutex);
                printf(" %s %.2f fps (queue=%u overrun=%"PRIu64")", (const char *[]){"A0","A1","B0","B1"}[ch],
                       flip.shown[ch]/elapsed,queues[ch].queued,queues[ch].overrun);
                struct ui_channel *a=&ui_stats[ch];
                a->depth=queues[ch].queued;
                a->drops=queues[ch].overrun;
                pthread_mutex_unlock(&queues[ch].mutex);
                a->submit_fps=flip.submitted_count[ch]/elapsed;
                a->hdmi_fps=flip.shown[ch]/elapsed;
                a->skips=flip.skipped[ch];
                a->interval95=ui_percentile(&flip.intervals[ch],95);
                a->latency50=ui_percentile(&flip.latency[ch],50);
                a->latency95=ui_percentile(&flip.latency[ch],95);
                a->wait95=ui_percentile(&flip.waits[ch],95);
                flip.intervals[ch].count=flip.intervals[ch].next=0;
                flip.latency[ch].count=flip.latency[ch].next=0;
                flip.waits[ch].count=flip.waits[ch].next=0;
                flip.submitted_count[ch]=flip.skipped[ch]=0;
                fps[ch] = (unsigned)(flip.shown[ch] / elapsed + 0.5);
                flip.shown[ch]=0;
            }
            puts("");
            fflush(stdout);
            flip.flips=0;
            start+=elapsed;
        }
    }
    if(threaded) converter_stop(&converter);
    close_inputs(&ui);
    if (cjk_font) FT_Done_Face(cjk_font);
    if (font) FT_Done_Face(font);
    if (font_library) FT_Done_FreeType(font_library);
    for (unsigned i=0; i<2; i++) munmap(surfaces[i].memory,surfaces[i].bytes);
    close(fd);
    return NULL;
fail_fd:
    perror("Rockchip HDMI KMS setup");
    close(fd);
fail:
    atomic_store(&screen_ready,-1);
    return NULL;
}

static int present_start(void) {
    for(unsigned ch=0;ch<4;ch++) {
        pthread_mutex_init(&queues[ch].mutex,NULL);
        assembling[ch]=pool[ch][DEPTH];
        for(unsigned slot=0;slot<DEPTH;slot++) queues[ch].frames[slot].data=pool[ch][slot];
    }
    atomic_store(&screen_running, 1);
    if (pthread_create(&screen_thread, NULL, screen_main, NULL)) return 1;
    const struct timespec nap = {.tv_nsec = 10000000};
    while (!atomic_load(&screen_ready)) nanosleep(&nap, NULL);
    return atomic_load(&screen_ready) < 0;
}
static void present_stop(void) {
    atomic_store(&screen_running, 0);
    pthread_join(screen_thread, NULL);
}
