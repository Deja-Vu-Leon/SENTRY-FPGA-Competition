#include <arm_neon.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <sys/ioctl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <sched.h>

enum { WIDTH = 1680, HEIGHT = 1050, TILE_W = 840, TILE_H = 472, DEPTH = 8 };
static uint8_t incoming[4][PIXELS];
struct display_frame { uint32_t id; uint8_t data[PIXELS]; };
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
    unsigned size = payload_size(receive_mode);
    if (offset >= size) return;
    if (length > size - offset) length = size - offset;
    memcpy(incoming[channel] + offset, pixels, length);
}
static void present_frame(unsigned channel, uint32_t id) {
    pthread_mutex_lock(&queues[channel].mutex);
    if (queues[channel].queued == DEPTH) {
        queues[channel].head = (queues[channel].head + 1) % DEPTH;
        queues[channel].queued--;
        queues[channel].overrun++;
    }
    unsigned position = (queues[channel].head + queues[channel].queued) % DEPTH;
    memcpy(queues[channel].frames[position].data, incoming[channel], payload_size(receive_mode));
    queues[channel].frames[position].id = id;
    queues[channel].queued++;
    queues[channel].last_frame = now();
    pthread_mutex_unlock(&queues[channel].mutex);
}

struct white_balance {
    unsigned red, blue;
    double next_sample;
};

static unsigned limit_gain(unsigned gain) {
    if (gain < 160) return 160;
    if (gain > 640) return 640;
    return gain;
}

static void update_white_balance(struct white_balance *wb, const uint8_t *raw,
                                 unsigned camera, double timestamp) {
    if (timestamp < wb->next_sample) return;
    wb->next_sample = timestamp + 0.5;
    unsigned red = 0, green = 0, blue = 0, count = 0;
    for (unsigned y = 8; y < 1072; y += 16)
        for (unsigned x = 8; x < 1912; x += 16) {
            const uint8_t *top = raw + y * 1920 + x;
            const uint8_t *bottom = top + 1920;
            unsigned g = (top[0] + bottom[1] + 1) >> 1;
            if (g < 12 || g > 200 || top[1] < 4 || bottom[0] < 4 ||
                top[1] > 235 || bottom[0] > 235 ||
                abs((int)top[0] - bottom[1]) > 12) continue;
            red += bottom[0];
            green += g;
            blue += top[1];
            count++;
        }
    if (count >= 200 && red && blue) {
        unsigned target_r = limit_gain(((green + count * 4) * 256 + red / 2) / red);
        unsigned target_b = limit_gain(((green + count * 4) * 256 + blue / 2) / blue);
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

static uint8x8_t lift_shadows(uint8x8_t sample) {
    return vqadd_u8(sample, vmin_u8(sample, vdup_n_u8(32)));
}

static void render_tile(uint32_t *tile, const uint8_t *raw, unsigned mode,
                        const struct white_balance *wb) {
    if (mode & 5) {
        unsigned shift = !!(mode & 4) + ((mode & 2) ? ((mode & 1) ? 1 : 2) : 0);
        for (unsigned y = 0; y < TILE_H; y++)
            for (unsigned x = 0; x < TILE_W; x++) {
                unsigned iy = y * 1080 / TILE_H + shift;
                unsigned ix = x * 1920 / TILE_W + shift;
                unsigned offset = iy * 1920 + ix;
                unsigned level = 0;
                if (ix < 1920 && iy < 1080)
                    level = mode & 4 ? 255 * ((raw[offset / 8] >> (offset % 8)) & 1) : raw[offset];
                tile[y * TILE_W + x] = 0x010101 * level;
            }
        return;
    }
    // The VID007 reference uses GBRG. Convert eight Bayer cells at once.
    static unsigned map_x[TILE_W];
    if (!map_x[TILE_W-1])
        for (unsigned x = 0; x < TILE_W; x++) map_x[x] = x * 960 / TILE_W;
    unsigned shift = (mode & 2) ? 2 : 0;
    uint8x8_t red_gain = vdup_n_u8(((wb->red ? wb->red : 256) + 2) / 4);
    uint8x8_t blue_gain = vdup_n_u8(((wb->blue ? wb->blue : 256) + 2) / 4);
    uint32_t row[960];
    for (unsigned y = 0; y < TILE_H; y++) {
        const uint8_t *top = raw + (2 * (y * 540 / TILE_H) + shift) * 1920;
        const uint8_t *bottom = top + 1920;
        for (unsigned x = 0; x < 960; x += 8) {
            uint8x8x2_t t = vld2_u8(top + 2*x);
            uint8x8x2_t b = vld2_u8(bottom + 2*x);
            uint8x8x4_t pixel = {{
                lift_shadows(vqsub_u8(vqmovn_u16(vrshrq_n_u16(vmull_u8(t.val[1], blue_gain), 6)), vdup_n_u8(4))),
                lift_shadows(vrhadd_u8(t.val[0], b.val[1])),
                lift_shadows(vqsub_u8(vqmovn_u16(vrshrq_n_u16(vmull_u8(b.val[0], red_gain), 6)), vdup_n_u8(4))),
                vdup_n_u8(0)
            }};
            vst4_u8((uint8_t *)(row + x), pixel);
        }
        for (unsigned x = 0; x < TILE_W; x++) {
            unsigned col = map_x[x] + shift / 2;
            tile[y * TILE_W + x] = row[col < 960 ? col : 959];
        }
    }
}

struct surface {
    uint32_t fb, handle, pitch;
    size_t bytes;
    uint8_t *memory;
};
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
#include "vid007-rk-controls.h"
#include "vid007-rk-chrome.h"
#include "vid007-ai-overlay.h"

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
    uint64_t flips, shown[4];
};
static void page_flipped(int fd, unsigned seq, unsigned sec, unsigned usec, void *data) {
    (void)fd; (void)seq; (void)sec; (void)usec;
    struct flip_state *flip = data;
    flip->pending = 0;
    flip->front = flip->queued;
    flip->flips++;
    for (unsigned i=0; i<4; i++) flip->shown[i] += (flip->fresh >> i) & 1;
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
    static uint8_t raw[PIXELS];
    struct white_balance balance[4] = {0};
    double start=now();
    int old_mode=-2;
    int primed[4] = {0};
    double next_ai[4] = {0};
    ai_open();
    unsigned fps[4] = {0};
    struct controls ui = {.x=20, .y=20};
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
                memset(primed, 0, sizeof(primed));
            }
            const unsigned index=1-flip.front;
            struct surface *s=&surfaces[index];
            unsigned fresh=0;
            unsigned offline = 0;
            const double frame_time = now();
            if (active >= 0) for (unsigned ch=0; ch<4; ch++) {
                pthread_mutex_lock(&queues[ch].mutex);
                if (frame_time - queues[ch].last_frame > 1.0) {
                    offline |= 1u << ch;
                    primed[ch] = 0;
                }
                if (queues[ch].queued >= 3) primed[ch] = 1;
                int new_image = primed[ch] && queues[ch].queued != 0 &&
                                atomic_load(&published_mode) == active;
                if (new_image) {
                    memcpy(raw,queues[ch].frames[queues[ch].head].data,payload_size(active));
                    queues[ch].head=(queues[ch].head+1)%DEPTH;
                    queues[ch].queued--;
                }
                pthread_mutex_unlock(&queues[ch].mutex);
                if (offline & (1u << ch)) {
                    memset(tiles[ch], 0, sizeof(tiles[ch]));
                    fps[ch] = 0;
                }
                if (new_image) {
                    if (!(active & 5))
                        update_white_balance(&balance[ch], raw, ch, now());
                    render_tile(tiles[ch], raw, active, &balance[ch]);
                    if (ai && active == 0 && frame_time >= next_ai[ch]) {
                        ai_publish(ch, tiles[ch]);
                        next_ai[ch] = frame_time + 0.15;
                    }
                    fresh |= 1u<<ch;
                }
            }
            for (unsigned ch=0; ch<4; ch++) {
                const unsigned x=(ch%2)*TILE_W, y0=68+(ch/2)*TILE_H;
                for (unsigned y=0; y<TILE_H; y++)
                    memcpy(s->memory+(y0+y)*s->pitch+x*4,tiles[ch]+y*TILE_W,TILE_W*4);
            }
            if (active == 0) for (unsigned ch=0; ch<4; ch++)
                if (!(offline & (1u<<ch))) ai_draw(s,ch,frame_time);
            rk_chrome(s, fps, active, offline);
            for (unsigned ch = 0; ch < 4; ch++)
                if (offline & (1u << ch))
                    rk_label(s, 340 + (ch % 2) * TILE_W, 310 + (ch / 2) * TILE_H,
                             L"摄像头无信号", 0xf6ad76);
            if (ui.mouse) {
                box(s, ui.x, ui.y, 3, 14, 0xffffff);
                box(s, ui.x, ui.y, 9, 3, 0xffffff);
            }
            flip.queued=index;
            flip.fresh=fresh;
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
                pthread_mutex_unlock(&queues[ch].mutex);
                fps[ch] = (unsigned)(flip.shown[ch] / elapsed + 0.5);
                flip.shown[ch]=0;
            }
            puts("");
            fflush(stdout);
            flip.flips=0;
            start+=elapsed;
        }
    }
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
    for (unsigned ch = 0; ch < 4; ch++) pthread_mutex_init(&queues[ch].mutex, NULL);
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
