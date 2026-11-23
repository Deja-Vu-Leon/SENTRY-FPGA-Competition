// Offline Google Pinyin adapter. Engine source is distributed alongside this file.
#include <googlepinyin/pinyinime.h>
#include <cstdio>
#include <cstring>
#include <cstdint>
using namespace ime_pinyin;
static bool ready;
extern "C" int sentry_ime_init(void) {
    if(!ready) ready=im_open_decoder("/home/linaro/sentry-esp32/ime/dict_pinyin.dat",
                                   "/home/linaro/sentry-esp32/ime/user.dat");
    if(ready) im_set_max_lens(80,40);
    return ready;
}
extern "C" unsigned sentry_ime_search(const char *spelling) {
    if(!sentry_ime_init()) return 0;
    im_reset_search();
    return (unsigned)im_search(spelling,std::strlen(spelling));
}
extern "C" int sentry_ime_candidate(unsigned index,char *out,unsigned capacity,unsigned *consumed) {
    if(!ready || capacity<4) return 0;
    char16 text[128]={0};
    if(!im_get_candidate(index,text,128)) return 0;
    unsigned count=0,offset=0;
    for(unsigned i=0;text[i] && i<127;i++) {
        uint32_t cp=text[i];
        if(cp>=0xd800 && cp<=0xdbff && text[i+1]>=0xdc00 && text[i+1]<=0xdfff)
            cp=0x10000+((cp-0xd800)<<10)+(text[++i]-0xdc00);
        unsigned bytes=cp<0x80?1:cp<0x800?2:cp<0x10000?3:4;
        if(offset+bytes>=capacity) return 0;
        if(bytes==1) out[offset++]=(char)cp;
        else {
            out[offset++]=(char)((bytes==2?0xc0:bytes==3?0xe0:0xf0)|(cp>>(6*(bytes-1))));
            for(int shift=6*(bytes-2);shift>=0;shift-=6) out[offset++]=(char)(0x80|((cp>>shift)&63));
        }
        count++;
    }
    out[offset]=0;
    const uint16 *starts=nullptr;
    size_t syllables=im_get_spl_start_pos(starts);
    if(consumed) *consumed=starts?starts[count<syllables?count:syllables]:0;
    return offset>0;
}
