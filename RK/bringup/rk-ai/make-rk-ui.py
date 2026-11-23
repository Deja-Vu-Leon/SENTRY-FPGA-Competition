from pathlib import Path

root = Path(__file__).resolve().parent
source = (root / "vid007-ai-kms.h").read_text(encoding="utf-8-sig")
controls = (root.parent / "vid007-kms-controls.h").read_text(encoding="utf-8-sig")

def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unexpected source: {old!r}")
    return text.replace(old, new)

controls = controls[:controls.index("static void draw_toolbar(")]
controls = change(controls, "enum { BUTTON_W = 192, BUTTON_STEP = 208, TOOLBAR = 68 };",
                  "enum { BUTTON_W = 150, BUTTON_STEP = 162, BUTTON_X = 390, BUTTON_Y = 19 };")
controls = change(controls, "ui->x >= 16 && ui->y >= 12 && ui->y < 54",
                  "ui->x >= BUTTON_X && ui->y >= BUTTON_Y && ui->y < BUTTON_Y + 32")
controls = controls.replace("(ui->x - 16)", "(ui->x - BUTTON_X)")
(root / "vid007-rk-controls.h").write_text(controls, encoding="utf-8")
source = change(source, '#include "vid007-kms-controls.h"',
                '#include "vid007-rk-controls.h"\n#include "vid007-rk-chrome.h"')
source = change(source, "        FT_Set_Pixel_Sizes(font, 0, 21);",
                "        FT_Set_Pixel_Sizes(font, 0, 21);\n    rk_font_init();")
source = change(source, "            draw_toolbar(s, fps, active);",
                "            rk_chrome(s, fps, active, offline);")
source = change(source, 'text_at(s, 24 + (ch % 2) * TILE_W, 103 + (ch / 2) * TILE_H,\n                            "No camera signal");',
                'rk_label(s, 340 + (ch % 2) * TILE_W, 310 + (ch / 2) * TILE_H,\n                             L"摄像头无信号", 0xf6ad76);')
source = change(source, "    if (font) FT_Done_Face(font);",
                "    if (cjk_font) FT_Done_Face(cjk_font);\n    if (font) FT_Done_Face(font);")
(root / "vid007-rk-kms.h").write_text(source, encoding="utf-8")
preview = (root / "vid007-ai-preview.c").read_text(encoding="utf-8-sig")
(root / "vid007-rk-preview.c").write_text(change(preview, '#include "vid007-ai-kms.h"',
                                                           '#include "vid007-rk-kms.h"'), encoding="utf-8")
