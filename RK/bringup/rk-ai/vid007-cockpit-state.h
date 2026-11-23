/* Native HDMI pages. Metrics are measured at their named RK pipeline stages. */
enum { PAGE_X=282, PAGE_STEP=156, PAGE_W=148, PAGE_Y=12, PAGE_H=44 };
static unsigned ui_page, ui_event, ui_log_count;
static double ui_started;
static _Atomic unsigned ui_mbps_x100;
static _Atomic unsigned ui_rx_fps_x100[4];
static _Atomic uint32_t ui_source_id[4];
static _Atomic uint64_t ui_rx_total[4], ui_bad_total[4];

struct ui_channel {
    uint64_t submitted, drops, skips;
    unsigned depth;
    double submit_fps, hdmi_fps, interval95, latency50, latency95, wait95;
};
static struct ui_channel ui_stats[4];

enum { UI_SAMPLES=320 };
struct ui_times {
    double values[UI_SAMPLES];
    unsigned next,count;
};
static void ui_sample(struct ui_times *s,double value) {
    s->values[s->next++ % UI_SAMPLES]=value;
    if(s->count<UI_SAMPLES) s->count++;
}
static int ui_compare(const void *a,const void *b) {
    double x=*(const double *)a,y=*(const double *)b;
    return (x>y)-(x<y);
}
static double ui_percentile(const struct ui_times *s,unsigned p) {
    if(!s->count) return -1;
    double sorted[UI_SAMPLES];
    memcpy(sorted,s->values,s->count*sizeof(*sorted));
    qsort(sorted,s->count,sizeof(*sorted),ui_compare);
    return sorted[(s->count*p+99)/100-1];
}
