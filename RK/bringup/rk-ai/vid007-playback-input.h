enum { PLAY_X=530,PLAY_Y=154,PLAY_W=1040,PLAY_H=584,
       LIB_TOP=326,LIB_STEP=43,LIB_ROWS=12 };
static unsigned library_source, library_page, library_more;
static char library_ids[LIB_ROWS][17];

static void playback_command(const char *action,const char *value) {
    FILE *file=fopen("/run/sentry-vid007-ai/play.command.tmp","w");
    if(!file) return;
    fprintf(file,"%s %s\n",action,value);
    if(!fclose(file)) rename("/run/sentry-vid007-ai/play.command.tmp","/run/sentry-vid007-ai/play.command");
}

static void playback_click(int x,int y) {
    if(y>=248 && y<287 && x>=52 && x<489) {
        library_source=x>=269;
        library_page=0;
    } else if(x>=52 && x<489 && y>=LIB_TOP && y<LIB_TOP+LIB_STEP*LIB_ROWS) {
        unsigned i=(unsigned)(y-LIB_TOP)/LIB_STEP;
        if(library_ids[i][0]) playback_command("load",library_ids[i]);
    } else if(x>=52 && x<489 && y>=851 && y<890) {
        if(x>=270 && library_more) library_page++;
        else if(x<270 && library_page) library_page--;
    } else if(x>=PLAY_X && x<PLAY_X+PLAY_W && y>=744 && y<781) {
        char target[8];
        snprintf(target,sizeof(target),"%d",(x-PLAY_X)*1000/PLAY_W);
        playback_command("seek",target);
    } else if(y>=790 && y<829) {
        if(x>=530 && x<658) playback_command("pause","");
        if(x>=670 && x<798) playback_command("stop","");
        if(x>=1114 && x<1324) playback_command("mode","0");
        if(x>=1332 && x<1570) playback_command("mode","1");
    }
}
