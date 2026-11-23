#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>
int main(int argc,char **argv) {
    if(argc!=2) return 1;
    int fd=open("/dev/dri/card0",O_RDWR);
    if(fd<0) return 2;
    drmModeRes *r=drmModeGetResources(fd);
    if(!r) return 3;
    drmModeFB2 *fb=NULL;
    for(int i=0;i<r->count_crtcs && !fb;i++) {
        drmModeCrtc *c=drmModeGetCrtc(fd,r->crtcs[i]);
        if(c && c->mode_valid && c->buffer_id) fb=drmModeGetFB2(fd,c->buffer_id);
        if(c) drmModeFreeCrtc(c);
    }
    if(!fb || (fb->pixel_format!=DRM_FORMAT_XRGB8888 && fb->pixel_format!=DRM_FORMAT_ARGB8888)) return 4;
    struct drm_mode_map_dumb map={.handle=fb->handles[0]};
    if(ioctl(fd,DRM_IOCTL_MODE_MAP_DUMB,&map)) return 5;
    size_t size=(size_t)fb->pitches[0]*fb->height;
    uint8_t *data=mmap(NULL,size,PROT_READ,MAP_SHARED,fd,map.offset);
    if(data==MAP_FAILED) return 6;
    FILE *out=fopen(argv[1],"wb");if(!out) return 7;
    fprintf(out,"P6\n%u %u\n255\n",fb->width,fb->height);
    for(unsigned y=0;y<fb->height;y++) for(unsigned x=0;x<fb->width;x++) {
        uint8_t *p=data+fb->offsets[0]+y*fb->pitches[0]+x*4;
        uint8_t rgb[]={p[2],p[1],p[0]};fwrite(rgb,1,3,out);
    }
    fclose(out);munmap(data,size);drmModeFreeFB2(fb);drmModeFreeResources(r);close(fd);return 0;
}
