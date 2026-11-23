#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XShm.h>
#include <X11/extensions/Xpresent.h>
#include <pthread.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <stdatomic.h>
#include <sched.h>

enum { WIDTH = 1680, HEIGHT = 1050, TILE_W = 840, TILE_H = 472, DEPTH = 8 };
static uint8_t incoming[4][PIXELS];
struct display_frame { uint32_t id; uint8_t data[PIXELS]; };
static struct {
    pthread_mutex_t mutex;
    struct display_frame frames[DEPTH];
    unsigned head, queued;
    uint64_t overrun;
} queues[4];
static pthread_t screen_thread;
static atomic_int screen_running;
static atomic_int screen_ready;

static void present_packet(unsigned channel, unsigned offset, const uint8_t *pixels, unsigned length) {
    if (offset >= PIXELS) return;
    if (length > PIXELS - offset) length = PIXELS - offset;
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
    memcpy(queues[channel].frames[position].data, incoming[channel], PIXELS);
    queues[channel].frames[position].id = id;
    queues[channel].queued++;
    pthread_mutex_unlock(&queues[channel].mutex);
}

static void render_tile(uint32_t *tile, const uint8_t *raw) {
    // One complete Bayer cell per output pixel on the HDMI mosaic.
    // The independently validated DMA images remain 1920x1080.
    static unsigned map_x[TILE_W];
    if (!map_x[TILE_W-1])
        for (unsigned x = 0; x < TILE_W; x++) map_x[x] = 2 * (x * 960 / TILE_W);
    for (unsigned y = 0; y < TILE_H; y++) {
        const uint8_t *top = raw + (2 * (y * 540 / TILE_H)) * 1920;
        const uint8_t *bottom = top + 1920;
        for (unsigned x = 0; x < TILE_W; x++) {
            unsigned p = map_x[x];
            unsigned green = (top[p] + bottom[p + 1] + 1) >> 1;
            tile[y * TILE_W + x] = (bottom[p] << 16) | (green << 8) | top[p + 1];
        }
    }
}

static void *screen_main(void *unused) {
    (void)unused;
    cpu_set_t cpus;
    CPU_ZERO(&cpus);
    CPU_SET(6, &cpus);
    pthread_setaffinity_np(pthread_self(), sizeof(cpus), &cpus);
    Display *dpy = XOpenDisplay(NULL);
    if (!dpy) goto fail;
    int opcode, event_base, error_base;
    if (!XPresentQueryExtension(dpy, &opcode, &event_base, &error_base) ||
        !XShmQueryExtension(dpy)) goto fail;
    int screen = DefaultScreen(dpy);
    int depth = DefaultDepth(dpy, screen);
    Visual *visual = DefaultVisual(dpy, screen);
    XSetWindowAttributes attributes = {.override_redirect = True, .background_pixel = 0};
    Window win = XCreateWindow(dpy, RootWindow(dpy, screen), 0, 0, WIDTH, HEIGHT, 0,
                               depth, InputOutput, visual, CWOverrideRedirect | CWBackPixel, &attributes);
    XStoreName(dpy, win, "SENTRY VID007 - 1080p DMA verification");
    XMapRaised(dpy, win);
    XPresentSelectInput(dpy, win, PresentCompleteNotifyMask | PresentIdleNotifyMask);
    GC gc = XCreateGC(dpy, win, 0, NULL);
    XSetForeground(dpy, gc, 0xffffff);
    struct surface { XShmSegmentInfo shm; Pixmap pixmap; uint32_t serial; unsigned fresh; int busy; } surfaces[3] = {0};
    for (int i = 0; i < 3; i++) {
        struct surface *s = &surfaces[i];
        s->shm.shmid = shmget(IPC_PRIVATE, WIDTH * HEIGHT * 4, IPC_CREAT | 0600);
        if (s->shm.shmid < 0) goto fail;
        s->shm.shmaddr = shmat(s->shm.shmid, NULL, 0);
        shmctl(s->shm.shmid, IPC_RMID, NULL);
        if (s->shm.shmaddr == (void *)-1 || !XShmAttach(dpy, &s->shm)) goto fail;
        s->pixmap = XShmCreatePixmap(dpy, win, s->shm.shmaddr, &s->shm, WIDTH, HEIGHT, depth);
    }
    XSync(dpy, False);
    static uint32_t tiles[4][TILE_W*TILE_H];
    static uint8_t raw[PIXELS];
    uint32_t serial = 0;
    uint64_t target_msc = 0, current_msc = 0;
    uint64_t shown[4] = {0}, skipped = 0, flips = 0;
    unsigned label_fps[4] = {0};
    double begin = now();
    int pending = 0, primed = 0;
    atomic_store(&screen_ready, 1);
    while (atomic_load(&screen_running)) {
        while (XPending(dpy)) {
            XEvent event;
            XNextEvent(dpy, &event);
            if (event.type != GenericEvent || event.xcookie.extension != opcode ||
                !XGetEventData(dpy, &event.xcookie)) continue;
            if (event.xcookie.evtype == PresentCompleteNotify) {
                XPresentCompleteNotifyEvent *done = event.xcookie.data;
                if (done->kind == PresentCompleteKindPixmap) {
                    current_msc = done->msc;
                    pending--;
                    for (int i = 0; i < 3; i++)
                        if (surfaces[i].serial == done->serial_number) {
                            if (done->mode == PresentCompleteModeSkip) skipped++;
                            else {
                                flips++;
                                for (unsigned ch = 0; ch < 4; ch++)
                                    shown[ch] += (surfaces[i].fresh >> ch) & 1;
                            }
                        }
                }
            } else if (event.xcookie.evtype == PresentIdleNotify) {
                XPresentIdleNotifyEvent *idle = event.xcookie.data;
                for (int i = 0; i < 3; i++)
                    if (surfaces[i].pixmap == idle->pixmap) surfaces[i].busy = 0;
            }
            XFreeEventData(dpy, &event.xcookie);
        }
        double elapsed = now() - begin;
        if (elapsed >= 5) {
            printf("HDMI Presents %.2f/s skip=%"PRIu64, flips/elapsed, skipped);
            for (unsigned ch = 0; ch < 4; ch++) {
                pthread_mutex_lock(&queues[ch].mutex);
                printf(" %s %.2f fps (queue=%u overrun=%"PRIu64")", (const char *[]){"A0","A1","B0","B1"}[ch],
                       shown[ch]/elapsed, queues[ch].queued, queues[ch].overrun);
                pthread_mutex_unlock(&queues[ch].mutex);
                label_fps[ch] = (unsigned)(shown[ch]/elapsed + 0.5);
                shown[ch] = 0;
            }
            puts("");
            fflush(stdout);
            begin += elapsed;
            flips = 0;
        }
        struct surface *available = NULL;
        for (int i = 0; i < 3 && !available; i++) if (!surfaces[i].busy) available = &surfaces[i];
        if (pending < (current_msc ? 2 : 1) && available) {
            if (!primed) {
                unsigned ready = 0;
                for (unsigned ch = 0; ch < 4; ch++) {
                    pthread_mutex_lock(&queues[ch].mutex);
                    ready += queues[ch].queued >= 3;
                    pthread_mutex_unlock(&queues[ch].mutex);
                }
                primed = ready == 4;
            }
            unsigned fresh = 0;
            uint32_t *canvas = (uint32_t *)available->shm.shmaddr;
            if (primed) for (unsigned ch = 0; ch < 4; ch++) {
                pthread_mutex_lock(&queues[ch].mutex);
                int new_image = queues[ch].queued != 0;
                if (new_image) {
                    memcpy(raw, queues[ch].frames[queues[ch].head].data, PIXELS);
                    queues[ch].head = (queues[ch].head + 1) % DEPTH;
                    queues[ch].queued--;
                }
                pthread_mutex_unlock(&queues[ch].mutex);
                if (new_image) {
                    render_tile(tiles[ch], raw);
                    fresh |= 1u << ch;
                }
            }
            memset(canvas, 0, WIDTH * 68 * 4);
            for (unsigned ch = 0; ch < 4; ch++) {
                uint32_t *target = canvas + (68 + (ch/2)*TILE_H)*WIDTH + (ch%2)*TILE_W;
                for (unsigned y = 0; y < TILE_H; y++)
                    memcpy(target + y*WIDTH, tiles[ch] + y*TILE_W, TILE_W*4);
                char label[64];
                int length = snprintf(label, sizeof(label), "%s 1080p %u fps",
                                      (const char *[]){"A0","A1","B0","B1"}[ch], label_fps[ch]);
                XDrawString(dpy, available->pixmap, gc, 15 + (ch%2)*TILE_W,
                            22 + (ch/2)*21, label, length);
            }
            available->serial = ++serial;
            available->fresh = fresh;
            available->busy = 1;
            if (current_msc) {
                if (target_msc < current_msc) target_msc = current_msc;
                target_msc++;
            }
            XPresentPixmap(dpy, win, available->pixmap, serial, 0, 0, 0, 0, 0, 0, 0,
                           0, target_msc, 0, 0, NULL, 0);
            XFlush(dpy);
            pending++;
        }
        struct pollfd event = {.fd = ConnectionNumber(dpy), .events = POLLIN};
        poll(&event, 1, 2);
    }
    XDestroyWindow(dpy, win);
    XCloseDisplay(dpy);
    for (int i = 0; i < 3; i++) shmdt(surfaces[i].shm.shmaddr);
    return NULL;
fail:
    atomic_store(&screen_ready, -1);
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
