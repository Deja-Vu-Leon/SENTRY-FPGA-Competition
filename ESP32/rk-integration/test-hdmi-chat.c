#include <linux/uinput.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <sys/ioctl.h>
static int tap(int fd,int key) {
    struct input_event e[4]={{.type=EV_KEY,.code=key,.value=1},{.type=EV_SYN,.code=SYN_REPORT},
        {.type=EV_KEY,.code=key,.value=0},{.type=EV_SYN,.code=SYN_REPORT}};
    return write(fd,e,sizeof(e))!=sizeof(e);
}
int main(void) {
    int keys[]={KEY_F7,KEY_H,KEY_E,KEY_L,KEY_L,KEY_O,KEY_ENTER};
    int fd=open("/dev/uinput",O_WRONLY);
    if(fd<0 || ioctl(fd,UI_SET_EVBIT,EV_KEY)) return 1;
    for(unsigned i=0;i<sizeof(keys)/sizeof(keys[0]);i++) if(ioctl(fd,UI_SET_KEYBIT,keys[i])) return 2;
    struct uinput_setup setup={.name="SENTRY ESP32 F7 verification",.id={.bustype=BUS_USB}};
    if(ioctl(fd,UI_DEV_SETUP,&setup)||ioctl(fd,UI_DEV_CREATE)) return 3;
    sleep(4);
    for(unsigned i=0;i<sizeof(keys)/sizeof(keys[0]);i++) { if(tap(fd,keys[i])) return 4; usleep(250000); }
    ioctl(fd,UI_DEV_DESTROY);close(fd);return 0;
}
