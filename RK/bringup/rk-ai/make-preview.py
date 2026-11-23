from pathlib import Path
p = Path(__file__).parent
s = (p.parent / "vid007-kms.h").read_text()
s = s.replace('#include "vid007-kms-controls.h"', '#include "vid007-kms-controls.h"\n#include "vid007-ai-overlay.h"')
s = s.replace("    int primed[4] = {0};", "    int primed[4] = {0};\n    double next_ai[4] = {0};\n    ai_open();")
s = s.replace("                    fresh |= 1u<<ch;", """                    if (ai && active == 0 && frame_time >= next_ai[ch]) {
                        ai_publish(ch, tiles[ch]);
                        next_ai[ch] = frame_time + 0.15;
                    }
                    fresh |= 1u<<ch;""")
s = s.replace("            draw_toolbar(s, fps, active);", """            if (active == 0) for (unsigned ch=0; ch<4; ch++)
                if (!(offline & (1u<<ch))) ai_draw(s,ch,frame_time);
            draw_toolbar(s, fps, active);""")
(p / "vid007-ai-kms.h").write_text(s)
s = (p.parent / "vid007-ddr-rx.c").read_text()
s = s.replace('#include "vid007-kms.h"', '#include "vid007-ai-kms.h"')
(p / "vid007-ai-preview.c").write_text(s)
