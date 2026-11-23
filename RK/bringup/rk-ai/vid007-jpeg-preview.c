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
static unsigned dimensions[4];
static unsigned resolution(unsigned config) {
    unsigned setting=((config&8u)>>2)|((config&128u)>>7);
    return setting<=2?setting:0;
}
static unsigned channel_payload(unsigned ch,unsigned mode) {
    return mode&4 ? PIXELS/8 : PIXELS>>(2*dimensions[ch]);
}

#if defined(HDMI) && !defined(KMS)
static unsigned payload_size(unsigned mode) {
    return channel_payload(0,mode);
}
#endif
static volatile sig_atomic_t stopped;
static void stop(int sig) { (void)sig; stopped = 1; }
static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}
#ifdef HDMI
#ifdef KMS
#include "vid007-jpeg-kms.h"
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
    const unsigned image_size = channel_payload(channel,receive_mode);
    unsigned codec=0;
#if defined(HDMI) && defined(KMS)
    codec=jpeg_board?atomic_load(&jpeg_live[channel])&3u:0;
#endif
    const unsigned limit=codec?PIXELS:image_size;
    const unsigned trailer_size = receive_mode & 4 ? 1 : 4;
    if ((flags & 1) && chunk == 0) {
        cam->bad += cam->active;
        cam->id = id;
        cam->next_chunk = cam->offset = 0;
        cam->active = 1;
    }
    if (!cam->active) return 0;
    if ((flags & 4) || cam->id != id || cam->next_chunk != chunk ||
        cam->offset + length > limit + trailer_size) {
        cam->bad++;
#if defined(HDMI) && defined(KMS)
            atomic_fetch_add(&ui_bad_total[channel],1);
#endif
        cam->active = 0;
        return 0;
    }
#ifdef HDMI
#ifdef KMS
    if(codec) jpeg_append(channel,cam->offset,p+16,length);
    else
#endif
        present_packet(channel,cam->offset,p+16,length);
#endif
    cam->next_chunk++;
    cam->offset += length;
    if (flags & 2) {
        cam->active = 0;
        const uint8_t *trailer = p + 16 + length;
        if ((!codec && cam->offset!=image_size+trailer_size) ||
            (codec && (length<20 || cam->offset<20)) || length < trailer_size ||
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
#if defined(HDMI) && defined(KMS)
            if(codec && jpeg_publish(channel,id,cam->offset-20,word(trailer-20),codec)) return 0;
#endif
            cam->previous_id = id;
            cam->have_previous = 1;
            cam->complete++;
#ifdef HDMI
#ifdef KMS
            atomic_store(&ui_source_id[channel],id);
            atomic_fetch_add(&ui_rx_total[channel],1);
#endif
            if(!codec) present_frame(channel,id);
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
#ifdef KMS
                memset(assembling[ch],35+((id+ch*50)&127),PIXELS);
#else
                memset(incoming[ch],35+((id+ch*50)&127),PIXELS);
#endif
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
    int fd = open("/dev/ANLOGIC-PCI0_c2h_0", O_RDONLY | O_NONBLOCK);
    const int resource = open("/sys/bus/pci/devices/0000:21:00.0/resource0", O_RDWR | O_SYNC);
    if (fd < 0 || resource < 0) { perror("open DMA or BAR"); return 1; }
    volatile uint32_t *bar = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, resource, 0);
    if (bar == MAP_FAILED) { perror("mmap BAR"); return 1; }
    const uint32_t version = bar[0x40/4];
    if (version != 0x56070405 && version != 0x56070406 && version != 0x56070407 && version != 0x56070408 && version != 0x56070409) { fprintf(stderr, "Unexpected FPGA build %08x\n", version); return 1; }
    signal(SIGINT, stop);
    signal(SIGTERM, stop);
    bar[0x60/4] = 0;
    if (argc > 2) {
        char *end;
        unsigned long mode = strtoul(argv[2], &end, 10);
        if (*end || end == argv[2] || mode > 7) return 2;
        receive_mode = mode;
    }
#if defined(HDMI) && defined(KMS)
    advanced_board=(version>=0x56070406 && version<=0x56070409) && argc<=2;
    resolution_board=version>=0x56070407 && advanced_board;
    measurement_board=version>=0x56070408 && advanced_board;
    jpeg_board=version>=0x56070409 && advanced_board;
    unsigned old_capture[4]={0};
    if(version>=0x56070406) {
        bar[0xa0/4]=advanced_board;
        for(unsigned ch=0;ch<4;ch++) {
            bar[0xb0/4+ch]=0x5000;
            atomic_store(&requested_config[ch],0x5000);
            atomic_store(&live_config[ch],0x5000);
            if(jpeg_board) {
                bar[0x100/4+ch]=128;
                atomic_store(&jpeg_request[ch],128);
                atomic_store(&jpeg_live[ch],128);
            }
        }
    }
#endif
    bar[0x64/4] = receive_mode;
    const struct timespec settle = {.tv_nsec=200000000}, nap = {.tv_nsec=50000};
    nanosleep(&settle, NULL);
#ifdef HDMI
    if (present_start()) return 1;
#ifdef KMS
    atomic_store(&requested_mode, receive_mode);
    publish_mode(receive_mode);
    if(jpeg_board && jpeg_open()) { fputs("JPEG decoder initialization failed\n",stderr); return 1; }
#endif
#endif
    bar[0x60/4] = 1;
    const double begin = now();
    double interval = begin;
#if defined(HDMI) && defined(KMS)
    double feature_sample=begin;
#endif
    uint64_t bytes = 0, invalid = 0, totals[4] = {0};
    uint8_t buffer[65536] __attribute__((aligned(4096)));
    int error = 0;
#if defined(HDMI) && defined(KMS)
    double dma_watch=0;
    unsigned dma_retries=0;
#endif
    while (!stopped) {
#if defined(HDMI) && defined(KMS)
        unsigned desired = atomic_load(&requested_mode);
        unsigned config[4],codec_target[4];
        int changed=0;
        if(advanced_board) for(unsigned ch=0;ch<4;ch++) {
            config[ch]=atomic_load(&requested_config[ch]);
            changed |= config[ch]!=atomic_load(&live_config[ch]);
            codec_target[ch]=atomic_load(&jpeg_request[ch]);
            if(jpeg_board) changed|=codec_target[ch]!=atomic_load(&jpeg_live[ch]);
        }
        if (desired != receive_mode || changed) {
            bar[0x60/4] = 0;
            if(jpeg_board) jpeg_reset();
            publish_mode(-1);
            const double drain_until = now() + 0.20;
            while (!stopped && now() < drain_until) {
                if (read(fd, buffer, sizeof(buffer)) <= 0) nanosleep(&nap, NULL);
            }
            if (stopped) break;
            receive_mode = atomic_load(&requested_mode);
            bar[0x64/4] = receive_mode;
            if(advanced_board) for(unsigned ch=0;ch<4;ch++) {
                dimensions[ch]=resolution_board?resolution(config[ch]):0;
                if(jpeg_board) {
                    bar[0x100/4+ch]=codec_target[ch];
                    atomic_store(&jpeg_live[ch],codec_target[ch]);
                }
                bar[0xb0/4+ch]=config[ch];
                atomic_store(&live_config[ch],config[ch]);
                old_capture[ch]=0;
                atomic_store(&capture_fps[ch],0);
            }
            memset(cameras, 0, sizeof(cameras));
            memset(totals, 0, sizeof(totals));
            bytes = invalid = 0;
            interval = now();
            publish_mode(receive_mode);
            if(advanced_board)
                printf("FPGA config %04x %04x %04x %04x\n",config[0],config[1],config[2],config[3]);
            else printf("FPGA mode %u\n",receive_mode);
            if(jpeg_board) printf("FPGA JPEG cfg %u %u %u %u\n",codec_target[0],codec_target[1],codec_target[2],codec_target[3]);
            fflush(stdout);
            if(jpeg_board) {
                dma_retries=0;
                dma_watch=now()+2.0;
            }
            bar[0x60/4] = 1;
        }
#endif
#if defined(HDMI) && defined(KMS)
        if(dma_watch && now()>=dma_watch) {
            dma_watch=0;
            unsigned frames=0;
            for(unsigned ch=0;ch<4;ch++) frames|=cameras[ch].have_previous;
            if(!frames) {
                if(dma_retries==2) {
                    fputs("C2H DMA is still stalled; restarting the preview service\n",stderr);
                    error=1;
                    break;
                }
                dma_retries++;
                fputs("Restarting C2H DMA after an incomplete mode transition\n",stderr);
                bar[0x60/4]=0;
                close(fd);
                fd=-1;
                const struct timespec rearm={.tv_sec=1};
                nanosleep(&rearm,NULL);
                if(system("rmmod anlogic_pci_ring && insmod ./pcie-ring-batch/anlogic_pci_ring.ko "
                          "poll_mode=1 enable_st_c2h_credit=1 c2h_batch=1")!=0) { error=1; break; }
                fd=open("/dev/ANLOGIC-PCI0_c2h_0",O_RDONLY|O_NONBLOCK);
                if(fd<0) { perror("reopen DMA"); error=1; break; }
                dma_watch=now()+4.0;
                bar[0x60/4]=1;
            }
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
#if defined(HDMI) && defined(KMS)
        if(measurement_board && now()>=feature_sample) {
            for(unsigned ch=0;ch<4;ch++) {
                unsigned config=atomic_load(&live_config[ch]);
                unsigned value=(config&0x8070u)==0x8070u ? bar[0xf0/4+ch]:0;
                atomic_store(&subpixel_result[ch],value);
            }
            feature_sample=now()+0.20;
        }
#endif
        double elapsed = now() - interval;
        if (elapsed >= 5) {
#ifdef KMS
            atomic_store(&ui_mbps_x100,(unsigned)(bytes/elapsed/10000.));
#endif
#if defined(HDMI) && defined(KMS)
            if(advanced_board) {
                fputs("FPGA counters",stdout);
                for(unsigned ch=0;ch<4;ch++) {
                    uint32_t current=bar[0xc0/4+ch], rejected=bar[0xd0/4+ch], axi=bar[0xe0/4+ch];
                    double fps=(uint32_t)(current-old_capture[ch])/elapsed;
                    old_capture[ch]=current;
                    atomic_store(&capture_fps[ch],(unsigned)(fps*100+0.5));
                    atomic_store(&capture_bad[ch],rejected);
                    atomic_store(&axi_write_errors[ch],axi);
                    printf(" ch%u %.2f fps bad=%u axi=%u",ch,fps,rejected,axi);
                }
                putchar('\n');
            }
#endif
#if defined(HDMI) && defined(KMS)
            if(jpeg_board) {
                fputs("JPEG decode",stdout);
                for(unsigned ch=0;ch<4;ch++)
                    printf(" ch%u mode=%u pt=%u bytes=%u decoded=%u rejected=%u queue=%u drops=%u p95=%.2fms",ch,
                           atomic_load(&jpeg_live[ch])&3u,atomic_load(&jpeg_actual[ch]),atomic_load(&jpeg_bytes[ch]),
                           atomic_load(&jpeg[ch].decoded),atomic_load(&jpeg[ch].rejected),atomic_load(&jpeg[ch].depth),
                           atomic_load(&jpeg[ch].discarded),atomic_load(&jpeg[ch].decode_p95)/100.);
                putchar('\n');
            }
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
#ifdef KMS
    if(jpeg_board) jpeg_close();
#endif
    present_stop();
#endif
    return error;
}
