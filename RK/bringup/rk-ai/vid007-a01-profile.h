/* A01 display profile fitted to a registered camera capture of the supplied reference.
 * BGR curves map 8-bit values after black-level, white-balance and shadow lift.
 * These settings apply to ordinary A01 colour preview and preserve deep shadows.
 */
static const uint8_t a01_blue_base[16]={0, 16, 32, 46, 54, 54, 69, 94, 111, 122, 139, 164, 199, 220, 241, 252};
static const uint8_t a01_blue_delta[16]={16, 16, 14, 8, 0, 15, 25, 17, 11, 17, 25, 35, 21, 21, 11, 3};
static const uint8_t a01_green_base[16]={0, 16, 32, 46, 57, 63, 77, 98, 115, 123, 135, 142, 159, 190, 216, 237};
static const uint8_t a01_green_delta[16]={16, 16, 14, 11, 6, 14, 21, 17, 8, 12, 7, 17, 31, 26, 21, 18};
static const uint8_t a01_red_base[16]={0, 16, 32, 46, 56, 63, 84, 111, 130, 146, 158, 179, 214, 232, 242, 249};
static const uint8_t a01_red_delta[16]={16, 16, 14, 10, 7, 21, 27, 19, 16, 12, 21, 35, 18, 10, 7, 6};

static inline uint8x8_t a01_curve(uint8x8_t pixels,uint8x16_t base,uint8x16_t delta) {
    uint8x8_t index=vshr_n_u8(pixels,4);
    uint8x8_t fraction=vand_u8(pixels,vdup_n_u8(15));
    uint8x8_t increment=vrshrn_n_u16(vmull_u8(fraction,vqtbl1_u8(delta,index)),4);
    return vbsl_u8(vceq_u8(pixels,vdup_n_u8(255)),vdup_n_u8(255),
                   vadd_u8(vqtbl1_u8(base,index),increment));
}
