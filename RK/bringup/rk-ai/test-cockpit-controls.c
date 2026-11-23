#define _DEFAULT_SOURCE
#include <fcntl.h>
#include <linux/uinput.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/ioctl.h>

static void send_event(int fd, unsigned type, unsigned code, int value) {
    struct input_event event={.type=type,.code=code,.value=value};
    if(write(fd,&event,sizeof(event))!=sizeof(event)) { perror("uinput"); exit(1); }
}

static void key(int fd,unsigned code) {
    send_event(fd,EV_KEY,code,1);
    send_event(fd,EV_SYN,SYN_REPORT,0);
    send_event(fd,EV_KEY,code,0);
    send_event(fd,EV_SYN,SYN_REPORT,0);
}

static void click(int fd,int x,int y) {
    send_event(fd,EV_REL,REL_X,-2000);
    send_event(fd,EV_REL,REL_Y,-2000);
    send_event(fd,EV_REL,REL_X,x);
    send_event(fd,EV_REL,REL_Y,y);
    send_event(fd,EV_SYN,SYN_REPORT,0);
    key(fd,BTN_LEFT);
}

int main(int argc,char **argv) {
    if(argc!=2) return 2;
    int fd=open("/dev/uinput",O_WRONLY|O_NONBLOCK);
    if(fd<0) { perror("open uinput"); return 1; }
    const unsigned keys[]={KEY_F1,KEY_F2,KEY_F3,KEY_F4,KEY_F5,KEY_F6,KEY_F7,KEY_J,KEY_H,KEY_I,KEY_ENTER,KEY_1,KEY_2,KEY_3,
                          KEY_5,KEY_6,KEY_7,KEY_8,KEY_LEFT,KEY_RIGHT,BTN_LEFT};
    ioctl(fd,UI_SET_EVBIT,EV_KEY);
    ioctl(fd,UI_SET_EVBIT,EV_REL);
    ioctl(fd,UI_SET_RELBIT,REL_X);
    ioctl(fd,UI_SET_RELBIT,REL_Y);
    for(unsigned i=0;i<sizeof(keys)/sizeof(*keys);i++) ioctl(fd,UI_SET_KEYBIT,keys[i]);
    struct uinput_setup setup={.name="VID007 FPGA controls validation",.id={.bustype=BUS_USB}};
    if(ioctl(fd,UI_DEV_SETUP,&setup)||ioctl(fd,UI_DEV_CREATE)) { perror("uinput create"); return 1; }
    sleep(4);
    for(const char *p=argv[1];*p;p++) {
        if(*p=='P') key(fd,KEY_F5);
        else if(*p=='Q') key(fd,KEY_F6);
        else if(*p=='V') key(fd,KEY_F7);
        else if(*p=='I') { key(fd,KEY_H); key(fd,KEY_I); key(fd,KEY_ENTER); }
        else if(*p=='+') click(fd,100,332);
        else if(*p=='-') click(fd,320,332);
        else if(*p>='a' && *p<='d') key(fd,KEY_F1+*p-'a');
        else if(*p>='1' && *p<='8') key(fd,KEY_1+*p-'1');
        else if(*p=='R') key(fd,KEY_RIGHT);
        else if(*p=='T') click(fd,120,610);
        else if(*p=='S'||*p=='s') click(fd,*p=='S'?385:52,800);
        else if(*p>='A' && *p<='D') click(fd,50+(*p-'A')*205,1034);
        else if(*p>='e' && *p<='m') {
            unsigned op=*p-'e';
            click(fd,100+(op%2)*210,574+(op/2)*45);
        } else if(*p=='J') key(fd,KEY_J);
        else if(*p>='L' && *p<='O') click(fd,1320,185+(*p-'L')*92);
        else if(*p>='u' && *p<='x') click(fd,1485,185+(*p-'u')*92);
        else if(*p>='n' && *p<='q') click(fd,1160,185+(*p-'n')*92);
        else if(*p>='W' && *p<='Z') click(fd,1240,230+(*p-'W')*92);
        else if(*p=='U') click(fd,1530,322);
        else if(*p=='H') click(fd,125,974);
        else return 2;
        usleep(400000);
    }
    ioctl(fd,UI_DEV_DESTROY);
    close(fd);
    return 0;
}
