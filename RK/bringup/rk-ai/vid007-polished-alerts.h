/* Snapshot index is written atomically by the RK inference process. */
struct ui_alert { char file[48], port[8], when[32]; unsigned confidence; int reason; };
static struct ui_alert ui_alerts[24];
static uint32_t ui_photo[420*236];
static int ui_photo_ready;
static void ui_load_alerts(int preserve) {
    char selected[48]={0};
    if(preserve && ui_event<ui_log_count)
        memcpy(selected,ui_alerts[ui_event].file,sizeof(selected));
    FILE *file=fopen("rk-ai/alerts/index.tsv","r");
    ui_log_count=0;
    ui_photo_ready=0;
    if(!file) return;
    char line[160];
    while(ui_log_count<24 && fgets(line,sizeof(line),file)) {
        struct ui_alert *a=&ui_alerts[ui_log_count];
        if(sscanf(line,"%47s %7s %31s %u %d",a->file,a->port,a->when,&a->confidence,&a->reason)==5 &&
           strspn(a->file,"0123456789abcdef")==32 && !strcmp(a->file+32,".xrgb"))
            ui_log_count++;
    }
    fclose(file);
    if(!ui_log_count) return;
    if(selected[0]) for(unsigned i=0;i<ui_log_count;i++)
        if(!strcmp(selected,ui_alerts[i].file)) { ui_event=i; break; }
    if(ui_event>=ui_log_count) ui_event=ui_log_count-1;
    char path[96];
    snprintf(path,sizeof(path),"rk-ai/alerts/%s",ui_alerts[ui_event].file);
    file=fopen(path,"rb");
    if(file) {
        ui_photo_ready=fread(ui_photo,sizeof(*ui_photo),420*236,file)==420*236;
        fclose(file);
    }
}
