#ifndef VID007_ARMOUR_THEME_H
#define VID007_ARMOUR_THEME_H

#define ARMOUR_WHITE 0xf4f6fa
#define ARMOUR_SILVER 0xe8edf4
#define ARMOUR_BLUE 0x1646a0
#define ARMOUR_NAVY 0x112a55
#define ARMOUR_RED 0xd82732
#define ARMOUR_YELLOW 0xf5c542
#define ARMOUR_INK 0x18243a
#define ARMOUR_EDGE 0xaab6c8
#define ARMOUR_GREEN 0x24965a
#define ARMOUR_MUTED 0x4e6079
#define ARMOUR_LIGHT_BLUE 0xd6e3f8
#define ARMOUR_PAPER 0xffffff

enum {
    MONITOR_X = 182, MONITOR_STEP_X = 637, MONITOR_W = 620,
    MONITOR_Y = 155, MONITOR_STEP_Y = 425, MONITOR_H = 349,
    MONITOR_NAV_Y = 172, MONITOR_NAV_STEP = 52,
    MONITOR_RAIL_X = 1454, MONITOR_RAIL_W = 208
};

static void armour_panel(struct surface *s, int x, int y, int w, int h,
                         uint32_t fill, uint32_t accent) {
    box(s,x,y,w,h,ARMOUR_EDGE);
    box(s,x+1,y+1,w-2,h-2,fill);
    box(s,x,y,w-8,3,accent);
    for(int row=0;row<8;row++)
        box(s,x+w-8+row,y+row,8-row,1,ARMOUR_WHITE);
}

#endif
