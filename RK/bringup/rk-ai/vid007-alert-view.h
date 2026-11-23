/* Snapshot index is written atomically by the RK inference process. */
struct ui_alert { char file[48], port[8], when[32]; unsigned confidence; int reason; };
static struct ui_alert ui_alerts[24];
static unsigned ui_alert_count;
static uint32_t ui_photo[420*236];
static int ui_photo_ready;
static void ui_load_alerts(void) {
    FILE *file=fopen("rk-ai/alerts/index.tsv","r");
    ui_alert_count=0;
    ui_photo_ready=0;
    if(!file) return;
    char line[160];
    while(ui_alert_count<24 && fgets(line,sizeof(line),file)) {
        struct ui_alert *a=&ui_alerts[ui_alert_count];
        if(sscanf(line,"%47s %7s %31s %u %d",a->file,a->port,a->when,&a->confidence,&a->reason)==5 &&
           strspn(a->file,"0123456789abcdef")==32 && !strcmp(a->file+32,".xrgb"))
            ui_alert_count++;
    }
    fclose(file);
    if(!ui_alert_count) return;
    if(ui_event>=ui_alert_count) ui_event=ui_alert_count-1;
    char path[96];
    snprintf(path,sizeof(path),"rk-ai/alerts/%s",ui_alerts[ui_event].file);
    file=fopen(path,"rb");
    if(file) {
        ui_photo_ready=fread(ui_photo,sizeof(*ui_photo),420*236,file)==420*236;
        fclose(file);
    }
}
