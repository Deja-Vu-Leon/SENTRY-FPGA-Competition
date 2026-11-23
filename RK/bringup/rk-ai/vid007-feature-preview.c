#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

enum { PIXELS = 1920 * 1080, PAGE = 4096, FRAME = PIXELS + 4 };
struct camera {
    uint32_t id, previous_id, next_chunk, offset;
    uint64_t complete, bad, gaps;
    int active, have_previous;
};
static struct camera cameras[4];
static unsigned receive_mode;

static unsigned payload_size(unsigned mode) {
    return mode & 4 ? PIXELS / 8 : PIXELS;
}
static volatile sig_atomic_t stopped;
static void stop(int sig) { (void)sig; stopped = 1; }
static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}
#ifdef HDMI
#ifdef KMS
#include "vid007-feature-kms.h"
#else
#include "vid007-present.h"
#endif
#endif
static uint32_t word(const uint8_t *src) {
    uint32_t n;
    memcpy(&n, src, sizeof(n));
    return n;
}

static int packet(const uint8_t *p, unsigned length) {
    const unsigned channel = p[4], flags = p[5];
    if (channel >= 4 || (flags & ~7u)) return 1;
    struct camera *cam = &cameras[channel];
    const unsigned chunk = p[6] | ((unsigned)p[7] << 8);
    const uint32_t id = word(p + (receive_mode & 4 ? 12 : 10));
    const unsigned image_size = payload_size(receive_mode);
    const unsigned trailer_size = receive_mode & 4 ? 1 : 4;
    if ((flags & 1) && chunk == 0) {
        cam->bad += cam->active;
        cam->id = id;
        cam->next_chunk = cam->offset = 0;
        cam->active = 1;
    }
    if (!cam->active) return 0;
    if ((flags & 4) || cam->id != id || cam->next_chunk != chunk ||
        cam->offset + length > image_size + trailer_size) {
        cam->bad++;
#if defined(HDMI) && defined(KMS)
            atomic_fetch_add(&ui_bad_total[channel],1);
#endif
        cam->active = 0;
        return 0;
    }
#ifdef HDMI
    present_packet(channel, cam->offset, p + 16, length);
#endif
    cam->next_chunk++;
    cam->offset += length;
    if (flags & 2) {
        cam->active = 0;
        const uint8_t *trailer = p + 16 + length;
        if (cam->offset != image_size + trailer_size || length < trailer_size ||
            (trailer_size == 4 ? word(trailer - 4) : trailer[-1]) != (0xa0u | receive_mode)) {
            cam->bad++;
#if defined(HDMI) && defined(KMS)
            atomic_fetch_add(&ui_bad_total[channel],1);
#endif
        } else {
            if (cam->have_previous) {
                unsigned delta = (uint16_t)(id - cam->previous_id);
                if (!delta || delta > (receive_mode & 4 ? 1 : 2)) cam->gaps++;
            }
            cam->previous_id = id;
            cam->have_previous = 1;
            cam->complete++;
#ifdef HDMI
#ifdef KMS
            atomic_store(&ui_source_id[channel],id);
            atomic_fetch_add(&ui_rx_total[channel],1);
#endif
            present_frame(channel, id);
#endif
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    const int seconds = argc > 1 ? atoi(argv[1]) : 60;
#ifdef HDMI
    if (argc > 2 && strcmp(argv[2], "display-test") == 0) {
        if (present_start()) { fputs("Cannot open HDMI Present window\n", stderr); return 1; }
        const double begin = now();
        struct timespec target;
        clock_gettime(CLOCK_MONOTONIC, &target);
        for (uint32_t id = 0; now() - begin < seconds; id++) {
            for (unsigned ch = 0; ch < 4; ch++) {
                memset(incoming[ch], 35 + ((id + ch*50) & 127), PIXELS);
                present_frame(ch, id);
            }
            target.tv_nsec += 20000000;
            if (target.tv_nsec >= 1000000000) { target.tv_nsec -= 1000000000; target.tv_sec++; }
            clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, NULL);
        }
        present_stop();
        return 0;
    }
#endif
    const int fd = open("/dev/ANLOGIC-PCI0_c2h_0", O_RDONLY | O_NONBLOCK);
    const int resource = open("/sys/bus/pci/devices/0000:21:00.0/resource0", O_RDWR | O_SYNC);
    if (fd < 0 || resource < 0) { perror("open DMA or BAR"); return 1; }
    volatile uint32_t *bar = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, resource, 0);
    if (bar == MAP_FAILED) { perror("mmap BAR"); return 1; }
    const uint32_t version = bar[0x40/4];
    if (version != 0x56070405) { fprintf(stderr, "Unexpected FPGA build %08x\n", version); return 1; }
    signal(SIGINT, stop);
    signal(SIGTERM, stop);
    bar[0x60/4] = 0;
    if (argc > 2) {
        char *end;
        unsigned long mode = strtoul(argv[2], &end, 10);
        if (*end || end == argv[2] || mode > 7) return 2;
        receive_mode = mode;
    }
    bar[0x64/4] = receive_mode;
    const struct timespec settle = {.tv_nsec=200000000}, nap = {.tv_nsec=50000};
    nanosleep(&settle, NULL);
#ifdef HDMI
    if (present_start()) return 1;
#ifdef KMS
    atomic_store(&requested_mode, receive_mode);
    publish_mode(receive_mode);
#endif
#endif
    bar[0x60/4] = 1;
    const double begin = now();
    double interval = begin;
    uint64_t bytes = 0, invalid = 0, totals[4] = {0};
    uint8_t buffer[65536] __attribute__((aligned(4096)));
    int error = 0;
    while (!stopped) {
#if defined(HDMI) && defined(KMS)
        unsigned desired = atomic_load(&requested_mode);
        if (desired != receive_mode) {
            bar[0x60/4] = 0;
            publish_mode(-1);
            const double drain_until = now() + 0.20;
            while (!stopped && now() < drain_until) {
                if (read(fd, buffer, sizeof(buffer)) <= 0) nanosleep(&nap, NULL);
            }
            if (stopped) break;
            receive_mode = atomic_load(&requested_mode);
            bar[0x64/4] = receive_mode;
            memset(cameras, 0, sizeof(cameras));
            memset(totals, 0, sizeof(totals));
            bytes = invalid = 0;
            interval = now();
            publish_mode(receive_mode);
            printf("FPGA mode %u\n", receive_mode);
            fflush(stdout);
            bar[0x60/4] = 1;
        }
#endif
        ssize_t n = read(fd, buffer, sizeof(buffer));
        if (n < 0 && errno != EINTR && errno != EAGAIN) { perror("DMA read"); error = 1; break; }
        if (n <= 0) nanosleep(&nap, NULL);
        else {
            bytes += (uint64_t)n;
            unsigned offset = 0;
            while ((unsigned)n - offset >= 16) {
                const uint8_t *p = buffer + offset;
                const unsigned length = receive_mode & 4 ? word(p + 8) :
                                        p[8] | ((unsigned)p[9] << 8);
                if (word(p) != 0x4b4e4843 || length > PAGE-16 ||
                    length + 16 > (unsigned)n - offset) break;
                invalid += packet(p, length);
                offset += length + 16;
            }
            if (offset != (unsigned)n && invalid < 20) {
                fprintf(stderr, "invalid read size=%zd offset=%u bytes:", n, offset);
                for (unsigned k=offset; k<(unsigned)n && k<offset+32; k++)
                    fprintf(stderr," %02x",buffer[k]);
                fputc('\n',stderr);
            }
            invalid += offset != (unsigned)n;
        }
        double elapsed = now() - interval;
        if (elapsed >= 5) {
#ifdef KMS
            atomic_store(&ui_mbps_x100,(unsigned)(bytes/elapsed/10000.));
#endif
            printf("DMA %.2f MB/s mode=%u bad_packets=%"PRIu64, bytes / elapsed / 1e6, receive_mode, invalid);
            for (unsigned i = 0; i < 4; i++) {
                struct camera *cam = &cameras[i];
                printf(" %s %.2f fps (frames=%"PRIu64" bad=%"PRIu64" gaps=%"PRIu64" id=%u)",
                       (const char *[]){"A0","A1","B0","B1"}[i],
                       (cam->complete - totals[i]) / elapsed, cam->complete, cam->bad,
                       cam->gaps, cam->previous_id);
#ifdef KMS
                atomic_store(&ui_rx_fps_x100[i],(unsigned)((cam->complete-totals[i])*100/elapsed));
#endif
                totals[i] = cam->complete;
            }
            puts("");
            fflush(stdout);
            interval += elapsed;
            bytes = 0;
        }
        if (seconds > 0 && now() - begin >= seconds) break;
    }
    bar[0x60/4] = 0;
    close(fd);
#ifdef HDMI
    present_stop();
#endif
    return error;
}
