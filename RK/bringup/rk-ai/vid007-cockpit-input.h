static unsigned cockpit_camera, cockpit_revision;
static char cockpit_draft[512], cockpit_messages[3][512];
static unsigned cockpit_message_count;
static char cockpit_gateway_notice[160];
static void cockpit_gateway_submit(void) {
    const char *request="/run/sentry-esp32/question.txt";
    if(access(request,F_OK)==0) {
        snprintf(cockpit_gateway_notice,sizeof(cockpit_gateway_notice),"上一个问题尚未完成，请稍候");
        return;
    }
    FILE *f=fopen("/run/sentry-esp32/question.tmp","w");
    if(!f) {
        snprintf(cockpit_gateway_notice,sizeof(cockpit_gateway_notice),"ESP32 对话服务未启动");
        return;
    }
    struct timespec stamp;
    clock_gettime(CLOCK_MONOTONIC,&stamp);
    int ok=fprintf(f,"hdmi-%ld-%ld-%ld\n%s",(long)getpid(),(long)stamp.tv_sec,stamp.tv_nsec,cockpit_draft)>0;
    if(fclose(f)) ok=0;
    if(!ok || rename("/run/sentry-esp32/question.tmp",request)) {
        snprintf(cockpit_gateway_notice,sizeof(cockpit_gateway_notice),"问题提交失败，请重试");
        return;
    }
    cockpit_gateway_notice[0]=0;
    memmove(cockpit_messages[0],cockpit_messages[1],2*sizeof(cockpit_messages[0]));
    strcpy(cockpit_messages[2],cockpit_draft);
    if(cockpit_message_count<3) cockpit_message_count++;
    cockpit_draft[0]=0;
}
static const char record_switch[]="/run/sentry-vid007-ai/record.enabled";
#include "vid007-playback-input.h"

extern int sentry_ime_init(void);
extern unsigned sentry_ime_search(const char *);
extern int sentry_ime_candidate(unsigned,char *,unsigned,unsigned *);
static char cockpit_preedit[81];
static unsigned cockpit_ime_count,cockpit_ime_page;
static int cockpit_chinese=1;
static char cockpit_candidates[5][256];
static unsigned cockpit_consumed[5];
static void cockpit_ime_refresh(void) {
    cockpit_ime_count=cockpit_preedit[0]?sentry_ime_search(cockpit_preedit):0;
    if(cockpit_ime_page*5>=cockpit_ime_count) cockpit_ime_page=0;
    for(unsigned i=0;i<5;i++) {
        cockpit_candidates[i][0]=0;cockpit_consumed[i]=0;
        if(cockpit_ime_page*5+i<cockpit_ime_count)
            sentry_ime_candidate(cockpit_ime_page*5+i,cockpit_candidates[i],256,&cockpit_consumed[i]);
    }
}
static void cockpit_append(const char *text) {
    if(strlen(cockpit_draft)+strlen(text)<sizeof(cockpit_draft)) strcat(cockpit_draft,text);
}
static void cockpit_choose(unsigned selected) {
    if(selected>=5 || !cockpit_candidates[selected][0] || !cockpit_consumed[selected]) return;
    if(strlen(cockpit_draft)+strlen(cockpit_candidates[selected])>=sizeof(cockpit_draft)) return;
    cockpit_append(cockpit_candidates[selected]);
    unsigned used=cockpit_consumed[selected];size_t n=strlen(cockpit_preedit);
    if(used>n) used=(unsigned)n;
    memmove(cockpit_preedit,cockpit_preedit+used,n-used+1);
    while(cockpit_preedit[0]=='\'') memmove(cockpit_preedit,cockpit_preedit+1,strlen(cockpit_preedit));
    cockpit_ime_page=0;cockpit_ime_refresh();
}
static void cockpit_type(unsigned code) {
    static const char keys[KEY_SPACE+1]={
        [KEY_A]='a',[KEY_B]='b',[KEY_C]='c',[KEY_D]='d',[KEY_E]='e',[KEY_F]='f',
        [KEY_G]='g',[KEY_H]='h',[KEY_I]='i',[KEY_J]='j',[KEY_K]='k',[KEY_L]='l',
        [KEY_M]='m',[KEY_N]='n',[KEY_O]='o',[KEY_P]='p',[KEY_Q]='q',[KEY_R]='r',
        [KEY_S]='s',[KEY_T]='t',[KEY_U]='u',[KEY_V]='v',[KEY_W]='w',[KEY_X]='x',
        [KEY_Y]='y',[KEY_Z]='z',[KEY_SPACE]=' ',[KEY_DOT]='.',[KEY_COMMA]=',',
        [KEY_1]='1',[KEY_2]='2',[KEY_3]='3',[KEY_4]='4',[KEY_5]='5',[KEY_6]='6',
        [KEY_7]='7',[KEY_8]='8',[KEY_9]='9',[KEY_0]='0',[KEY_APOSTROPHE]='\''
    };
    size_t length=strlen(cockpit_draft),compose=strlen(cockpit_preedit);
    char ch=code<=KEY_SPACE?keys[code]:0;
    if(code==KEY_TAB) {
        cockpit_chinese=!cockpit_chinese;
        if(!cockpit_chinese && compose) { cockpit_append(cockpit_preedit);cockpit_preedit[0]=0;cockpit_ime_refresh(); }
    } else if(code==KEY_ESC && compose) {
        cockpit_preedit[0]=0;cockpit_ime_refresh();
    } else if(compose && (code==KEY_PAGEUP || code==KEY_PAGEDOWN)) {
        if(code==KEY_PAGEUP && cockpit_ime_page) cockpit_ime_page--;
        if(code==KEY_PAGEDOWN && (cockpit_ime_page+1)*5<cockpit_ime_count) cockpit_ime_page++;
        cockpit_ime_refresh();
    } else if(compose && code>=KEY_1 && code<=KEY_5) {
        cockpit_choose(code-KEY_1);
    } else if(compose && (code==KEY_SPACE || code==KEY_ENTER)) {
        cockpit_choose(0);
    } else if(code==KEY_ENTER && length) {
        cockpit_gateway_submit();
    } else if(code==KEY_BACKSPACE) {
        if(compose) { cockpit_preedit[compose-1]=0;cockpit_ime_page=0;cockpit_ime_refresh(); }
        else if(length) {
            size_t start=length-1;
            while(start && ((unsigned char)cockpit_draft[start]&0xc0)==0x80) start--;
            cockpit_draft[start]=0;
        }
    } else if(cockpit_chinese && ((ch>='a' && ch<='z') || (ch=='\'' && compose))) {
        if(compose+1<sizeof(cockpit_preedit)) {
            cockpit_preedit[compose]=ch;cockpit_preedit[compose+1]=0;
            cockpit_ime_page=0;cockpit_ime_refresh();
        }
    } else if(ch && !compose) {
        if(cockpit_chinese && (ch=='.' || ch==',')) cockpit_append(ch=='.'?"。":"，");
        else { char value[2]={ch,0};cockpit_append(value); }
    }
    cockpit_revision++;
}

static void cockpit_click(int x,int y) {
    if(ui_page==6 && y>=935 && y<980 && x>=54 && x<1619) {
        cockpit_choose((unsigned)(x-54)/313);cockpit_revision++;return;
    }
    if(ui_page==4 && x>=32 && x<1648 && y>=881 && y<1001)
        cockpit_camera=(unsigned)(x-32)/404;
    if(ui_page==5 && y>=185 && y<224 && x<489) {
        if(x>=54 && x<236) {
            int fd=open(record_switch,O_CREAT|O_WRONLY|O_CLOEXEC,0600);
            if(fd>=0) close(fd);
        }
        if(x>=252 && x<434) {
            unlink(record_switch);
            library_source=0;
            library_page=0;
        }
    } else if(ui_page==5) playback_click(x,y);
    if(ui_page==6 && x>=1432 && x<1618 && y>=879 && y<918) cockpit_type(KEY_ENTER);
    cockpit_revision++;
}
