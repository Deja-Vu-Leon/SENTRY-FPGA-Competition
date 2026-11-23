#include <linux/uinput.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <sys/ioctl.h>
static int send_key(int fd,int key,int value) {
    struct input_event e[2]={{.type=EV_KEY,.code=key,.value=value},{.type=EV_SYN,.code=SYN_REPORT}};
    return write(fd,e,sizeof(e))!=sizeof(e);
}
int main(int argc,char **argv) {
    if(argc!=2||argv[1][0]<'1'||argv[1][0]>'7') return 2;
    int index=argv[1][0]-'1', key=index<4?KEY_F1+index:KEY_1+index-4;
    int fd=open("/dev/uinput",O_WRONLY);
    if(fd<0) return 1;
    if(ioctl(fd,UI_SET_EVBIT,EV_KEY)||ioctl(fd,UI_SET_KEYBIT,key)) return 1;
    struct uinput_setup setup={.name="VID007 page verification",.id={.bustype=BUS_USB}};
    if(ioctl(fd,UI_DEV_SETUP,&setup)||ioctl(fd,UI_DEV_CREATE)) return 1;
    sleep(4);
    int result=send_key(fd,key,1)||send_key(fd,key,0);
    usleep(160000);
    ioctl(fd,UI_DEV_DESTROY);
    close(fd);
    return result;
}
