# -*- coding: utf-8 -*-
"""
סקריפט הרכבה חד-פעמי לאתר ההדרכה (לא נדרש כדי לצפות באתר - האתר הסופי הוא
HTML/CSS/JS סטטי טהור, בלי build step). הסקריפט קורא את hebrew_translation.md
(פלט התרגום המלא) ומרכיב ממנו את כל דפי הפרקים, המילון ודף המקורות, בשילוב
תוספות הדרכה (תקצירים, תובנות מרכזיות, מבחני ידע, כרטיסי case study ותרשימים)
שנכתבו ידנית עבור כל פרק.

הרצה: python generate_site.py
"""
import re
import html
import json
import markdown
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "hebrew_translation.md"
CHAPTERS_DIR = ROOT / "chapters"
CHAPTERS_DIR.mkdir(exist_ok=True)

MD_EXT = ["extra", "sane_lists"]

# ---------------------------------------------------------------------------
# 1. פרסור קובץ התרגום
# ---------------------------------------------------------------------------

def split_top_sections(text):
    """מפצל את המסמך לפי כותרות רמה 2 (## ), מחזיר רשימת (title, body)."""
    parts = re.split(r"(?m)^##\s+(.*)$", text)
    # parts[0] = כל מה שלפני הכותרת הראשונה (בד"כ ריק / כותרת המסמך)
    sections = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((title, body.strip("\n")))
    return sections


def classify(sections, max_chapter=8):
    front = {}
    chapters = {}
    glossary_body = None
    refs_body = None
    about_body = None

    for title, body in sections:
        m = re.match(r"^(\d+)\.\s*(.*)$", title)
        if m:
            num = int(m.group(1))
            if 1 <= num <= max_chapter:
                chapters[num] = {"title": m.group(2).strip(), "body": body}
                continue
        if "מילון" in title:
            glossary_body = body
        elif "הערות שוליים" in title or ("מקורות" in title and "הערות" not in title and glossary_body is None and refs_body is None):
            refs_body = body
        elif "אודות" in title and "אינטרפול" in title:
            about_body = body
        elif "פתיחה" in title:
            front["foreword"] = body
        elif "תודות" in title:
            front["ack"] = body
        elif "הבהרה" in title:
            front["disclaimer"] = body
        elif "תקציר" in title:
            front["exec_summary"] = body
        else:
            # נופל בין הכיסאות - נשמור ליתר ביטחון תחת front matter כללי
            front[title] = body

    return front, chapters, glossary_body, refs_body, about_body


def extract_subsections(body_md):
    """מחזיר רשימת (number, title) לכל כותרת ### בגוף הפרק (לתפריט הצד)."""
    subs = []
    for m in re.finditer(r"(?m)^###\s+(\d+(?:\.\d+)*)\s+(.*)$", body_md):
        subs.append((m.group(1), m.group(2).strip()))
    return subs


def slug(num):
    return "sec-" + num.replace(".", "-")


def render_md(body_md, footnote_href=None):
    """ממיר Markdown ל-HTML. אם footnote_href סופק (למשל '../references.html#fn-'
    או '#rfn-'), כל סימון [N] בטקסט הופך לקישור-על (superscript) לעוגן המתאים
    בפרק המקורות; אחרת הוא רק מעוצב כ-superscript בלי קישור."""
    html_out = markdown.markdown(body_md, extensions=MD_EXT)
    # הוספת id לכל h3 לפי הקידומת המספרית שלו, לצורך עיגון מהתפריט הצדדי
    def add_id(m):
        tag_open, inner, tag_close = m.group(1), m.group(2), m.group(3)
        num_m = re.match(r"^(\d+(?:\.\d+)*)\s+(.*)$", inner.strip())
        if num_m:
            return f'<h3 id="{slug(num_m.group(1))}">{inner}</h3>'
        return m.group(0)
    html_out = re.sub(r"(<h3>)(.*?)(</h3>)", add_id, html_out, flags=re.DOTALL)
    # הפניות [N]: קישור-על לעוגן המקור בפרק המקורות, אם סופקה כתובת בסיס
    if footnote_href:
        html_out = re.sub(
            r"\[(\d+)\]",
            lambda m: f'<sup><a class="fn-ref" href="{footnote_href}{m.group(1)}">[{m.group(1)}]</a></sup>',
            html_out,
        )
    else:
        html_out = re.sub(r"\[(\d+)\]", r"<sup>[\1]</sup>", html_out)
    return html_out


def linkify_urls(html_out):
    """הופך כתובות URL חשופות בטקסט (לא בתוך תגיות/מאפיינים) לקישורים לחיצים -
    משמש בפרק המקורות כדי שאפשר יהיה לפתוח כל ציטוט ישירות."""
    pattern = re.compile(r"https?://\S+")

    def repl(m):
        url = m.group(0)
        trail = ""
        while url and url[-1] in '.,;:)]"”’':
            trail = url[-1] + trail
            url = url[:-1]
        return f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{url}</a>{trail}'

    segments = re.split(r"(<[^>]+>)", html_out)
    for i, seg in enumerate(segments):
        if not seg.startswith("<"):
            segments[i] = pattern.sub(repl, seg)
    return "".join(segments)


def add_footnote_anchor_ids(html_out, prefix):
    """מוסיף id="{prefix}N" לכל פסקת מקור בפרק ההערות/המקורות, כך שקישורי [N]
    בגוף הפרקים יוכלו לקפוץ ישירות לציטוט המדויק."""
    return re.sub(
        r"<p><sup>\[(\d+)\]</sup>",
        lambda m: f'<p id="{prefix}{m.group(1)}"><sup>[{m.group(1)}]</sup>',
        html_out,
    )


def wrap_as_accordion(html_body):
    """עבור פרק 4: עוטף כל h3 (עם התוכן שאחריו עד ה-h3 הבא) ב-<details class=tech-item>."""
    spans = list(re.finditer(r"<h3 id=\"([^\"]+)\">(.*?)</h3>", html_body))
    if not spans:
        return html_body
    intro = html_body[: spans[0].start()]
    out = [intro, '<div class="tech-ref">']
    for i, m in enumerate(spans):
        start_body = m.end()
        end_body = spans[i + 1].start() if i + 1 < len(spans) else len(html_body)
        item_body = html_body[start_body:end_body]
        summary_text = re.sub(r"<[^>]+>", "", m.group(2))
        num_m = re.match(r"^(\d+(?:\.\d+)*)\s+(.*)$", summary_text)
        if num_m:
            summary_inner = (
                f'<span class="tech-num">{num_m.group(1)}</span>'
                f'<span class="tech-title">{num_m.group(2)}</span>'
            )
        else:
            summary_inner = f'<span class="tech-title">{summary_text}</span>'
        summary_inner = f'<span class="tech-plusminus" aria-hidden="true"></span>{summary_inner}'
        out.append(
            f'<details class="tech-item" id="{m.group(1)}">'
            f'<summary>{summary_inner}</summary>'
            f'<div class="tech-body">{item_body}</div>'
            f'</details>'
        )
    out.append('</div>')
    return "".join(out)


# ---------------------------------------------------------------------------
# 2. תבניות עיצוב (chrome) משותפות
# ---------------------------------------------------------------------------

NAV_ITEMS = [
    ("בית", "index.html", ""),
    ("פרקי המדריך", "chapters/ch1.html", "chapters/"),
    ("מחקר: Forged Realities", "research.html", ""),
    ("מילון מונחים", "glossary.html", ""),
    ("מבחן מסכם", "final-quiz.html", ""),
    ("דף סיכום", "cheat-sheet.html", ""),
    ("מסמך המקור", "source.html", ""),
    ("מקורות והערות שוליים", "references.html", ""),
    ("אודות המדריך", "about.html", ""),
]

def top_nav(rel, active_href):
    lis = []
    for label, href, active_prefix in NAV_ITEMS:
        full_href = rel + href
        is_active = (href == active_href) or (active_prefix and active_href.startswith(active_prefix))
        cls = "nav-link active" if is_active else "nav-link"
        lis.append(f'<li><a class="{cls}" href="{full_href}">{label}</a></li>')
    return "\n      ".join(lis)


def page_head(title, rel, extra_head=""):
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<link rel="stylesheet" href="{rel}assets/css/style.css">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🛡️</text></svg>">
{extra_head}</head>
<body data-rel="{rel}">
"""


def header_html(rel, active_href):
    return f"""<header class="site-header">
  <nav class="site-nav">
    <a class="brand" href="{rel}index.html">🛡️ SynthWave <span>מדריך הדרכה</span></a>
    <ul>
      {top_nav(rel, active_href)}
    </ul>
    <div class="nav-utils">
      <button class="search-toggle" type="button" aria-label="חיפוש באתר" aria-expanded="false">🔍</button>
      <button class="menu-toggle" type="button" aria-label="פתיחת תפריט">☰</button>
    </div>
  </nav>
  <div class="site-search" hidden>
    <input type="search" id="site-search-input" placeholder="חיפוש בפרקים ובמילון המונחים...">
    <div class="site-search-results" hidden></div>
  </div>
</header>
"""


FOOTER_HTML_TEMPLATE = """<footer class="site-footer">
  <div class="wrap">
    <p class="citation">
      מבוסס על: INTERPOL (2026). <em>[Project SynthWave] Global Guideline &ndash; False Facades</em>.
      מדריך הדרכה פנימי בנושא זיהוי ואימות מדיה סינתטית (דיפייקים וזיופים רדודים) עבור גורמי אכיפת חוק.
    </p>
    <div class="footer-credit">
      <div class="logos">
        <span class="logo-chip"><img src="{rel}assets/img/logo-mazap.jpg" alt="לוגו מז&quot;פ — החטיבה לזיהוי פלילי" onerror="this.setAttribute('data-missing','')"></span>
        <span class="logo-chip"><img src="{rel}assets/img/logo-mop.jpg" alt="לוגו מו&quot;פ — מדור מחקר ופיתוח" onerror="this.setAttribute('data-missing','')"></span>
      </div>
      <p class="credit-text">תרגום, עיצוב הדרכה ופיתוח האתר: <strong>מדור מחקר ופיתוח (מו״פ)</strong>, החטיבה לזיהוי פלילי (מז״פ), משטרת ישראל.</p>
    </div>
  </div>
</footer>
"""

def footer_html(rel):
    return FOOTER_HTML_TEMPLATE.format(rel=rel)


SCRIPTS_TEMPLATE = '<script src="{rel}assets/js/main.js"></script>\n</body>\n</html>\n'

def scripts_html(rel):
    return SCRIPTS_TEMPLATE.format(rel=rel)


RESTRICTED_BANNER = """<div class="banner danger">
  <strong>🔒 שימוש פנימי בלבד — מותנה בהגבלות הפצה של אינטרפול</strong>
  מסמך המקור מוגדר על ידי אינטרפול כחומר רגיש למטרות אכיפת חוק בלבד, ואינו מיועד להפצה פומבית ללא אישור בכתב מאינטרפול. אתר זה אינו מקודם, אינו מקושר מבחוץ ואינו מיועד לפרסום — ללמידה פנימית של הצוות בלבד.
</div>
"""


# ---------------------------------------------------------------------------
# 3. תוכן הדרכה שנכתב ידנית: תובנות, מבחנים, מקרים, תרשימים
# ---------------------------------------------------------------------------

def takeaway_box(items):
    lis = "\n".join(f"<li>{i}</li>" for i in items)
    return f"""<div class="takeaway-box reveal">
  <span class="callout-label">🎯 עיקרי הפרק</span>
  <ul>{lis}</ul>
</div>"""


def quiz_block(chapter_num, questions):
    cards = []
    for qi, (question, options, correct_i, explain) in enumerate(questions):
        opts_html = []
        for oi, opt in enumerate(options):
            is_correct = "true" if oi == correct_i else "false"
            opts_html.append(
                f'<label class="quiz-opt"><input type="radio" name="q{chapter_num}-{qi}" '
                f'data-correct="{is_correct}" data-explain="{html.escape(explain)}"> <span>{opt}</span></label>'
            )
        cards.append(f"""<div class="quiz-card">
  <p class="quiz-q">{qi + 1}. {question}</p>
  <div class="quiz-opts">{''.join(opts_html)}</div>
  <button class="quiz-check" type="button">בדיקת תשובה</button>
  <div class="quiz-feedback"></div>
</div>""")
    return f"""<div class="quiz-block reveal">
  <p class="kicker">בדיקת ידע עצמית</p>
  <h2>מוכנים לבדוק את עצמכם?</h2>
  {''.join(cards)}
  <p class="quiz-score"></p>
</div>"""


CASE_STUDIES_HTML = """
<div class="case-grid">
  <div class="case-card reveal">
    <span class="case-tag">זיוף רדוד · 2019</span>
    <h3>ננסי פלוסי — וידאו מוקצן</h3>
    <p>סרטון של יו״ר בית הנבחרים האמריקאי הואט ועבר שינוי גובה-קול כדי ליצור רושם שווא שהיא שיכורה. עריכה גסה יחסית, אך הופצה נרחב לפני שרשתות חברתיות התערבו.</p>
    <p class="case-src">דוגמה קלאסית לכך שגם עריכה פשוטה, ללא בינה מלאכותית, יכולה להטעות המונים.</p>
  </div>
  <div class="case-card reveal">
    <span class="case-tag">זיוף עמוק היברידי · 2025</span>
    <h3>מנהל בית הספר בבולטימור</h3>
    <p>אריק אייסוורט, מנהל תיכון פייקסוויל, הושעה בעקבות הקלטת אודיו גזענית שיוחסה לו. ניתוח פורנזי (בשיתוף מומחה מטעם ה-FBI) קבע שההקלטה נוצרה כולה באמצעות AI, עם עריכות אנושיות שהוספו לאחר מכן (רעש רקע) כדי לדמות אותנטיות.</p>
    <p class="case-src">דוגמה למדיה סינתטית שמובילה לפגיעה תדמיתית ומשפטית חמורה, גם כשמעורבים אלמנטים אנושיים לאחר היצירה.</p>
  </div>
  <div class="case-card reveal">
    <span class="case-tag">התחזות לדמות ציבורית · 2025</span>
    <h3>פרשת ההונאה בשם לורנס וונג</h3>
    <p>סרטוני וידאו וקלוני קול מבוססי-AI הציגו כוזב את ראש ממשלת סינגפור כמקדם תוכניות הונאה. למרות תגובה רשמית מאומתת של ראש הממשלה, ערוצי תקשורת רשמיים מתקשים להתחרות בתפוצה של תוכן מזויף.</p>
    <p class="case-src">מקרים דומים תועדו גם נגד הסנטור האמריקאי מרקו רוביו ונגד ראש משטרת סולט לייק סיטי — כל בעל תפקיד סמכותי הוא יעד פוטנציאלי.</p>
  </div>
  <div class="case-card reveal">
    <span class="case-tag">ראיה משפטית · 2021</span>
    <h3>"אמא המעודדות" מפנסילבניה</h3>
    <p>רפאלה ספון הואשמה בהטרדה לאחר שנחשדה ביצירת תמונות וסרטוני דיפייק כדי להכפיש יריבות של בתה בענף העידוד. התביעה נסוגה מהאישומים הקשורים לדיפייק לאחר שהתברר שהמסקנות התבססו על בדיקה חזותית "בעין בלתי מזוינת" בלבד — ללא ניתוח פורנזי או אימות מומחה.</p>
    <p class="case-src">מדגים את הסיכון הכפול: להיות מרומה ע״י זיוף, או להאשים בטעות תוכן אמיתי כמזויף.</p>
  </div>
  <div class="case-card reveal">
    <span class="case-tag">הונאה פיננסית · 2024</span>
    <h3>שיחת הווידאו המזויפת בהונג קונג</h3>
    <p>עובד כספים בחברה בין־לאומית שוכנע להעביר כ-25.6 מיליון דולר לאחר שהשתתף בשיחת ועידה בווידאו שבה כל המשתתפים — כולל חיקוי משכנע של סמנכ״ל הכספים — היו דמויות דיפייק. המקרה נחשף רק לאחר שהעובד פנה לאימות ישיר מול המטה.</p>
    <p class="case-src">חלק מדפוס רחב יותר שכלל זהויות גנובות ולמעלה מ-50 חשבונות בנק מזויפים.</p>
  </div>
</div>
"""

FIG1_SVG = """<div class="diagram-wrap reveal">
<svg viewBox="0 0 640 170" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="סולם החומרה של מדיה סינתטית">
  <defs>
    <linearGradient id="sevGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="var(--accent)"/>
      <stop offset="55%" stop-color="var(--amber)"/>
      <stop offset="100%" stop-color="var(--red)"/>
    </linearGradient>
  </defs>
  <rect x="20" y="70" width="600" height="16" rx="8" fill="url(#sevGrad)" transform="scale(-1,1) translate(-640,0)"/>
  <g font-size="13" font-weight="700" text-anchor="middle">
    <circle cx="560" cy="78" r="7" fill="var(--paper-raised)" stroke="var(--accent)" stroke-width="3"/>
    <text x="560" y="55">זיוף רדוד</text>
    <text x="560" y="112" font-weight="400" font-size="11" fill="var(--ink-soft)">עריכה ידנית, ללא AI</text>

    <circle cx="330" cy="78" r="7" fill="var(--paper-raised)" stroke="var(--amber)" stroke-width="3"/>
    <text x="330" y="55">זיוף עמוק</text>
    <text x="330" y="112" font-weight="400" font-size="11" fill="var(--ink-soft)">GAN / מודל דיפוזיה</text>

    <circle cx="90" cy="78" r="8" fill="var(--paper-raised)" stroke="var(--red)" stroke-width="3.5"/>
    <text x="90" y="55" fill="var(--red)">זיוף ליינסטר</text>
    <text x="90" y="112" font-weight="400" font-size="11" fill="var(--ink-soft)">זיוף עמוק + פגמים מדומים</text>
    <text x="90" y="128" font-weight="400" font-size="11" fill="var(--ink-soft)">= הכי קשה לזיהוי</text>
  </g>
  <text x="320" y="152" text-anchor="middle" font-size="11" fill="var(--ink-soft)">← עולה רמת התחכום וקושי הזיהוי</text>
</svg>
<p class="fig-legend"><b>איור 1 (שחזור).</b> סולם החומרה של מדיה סינתטית: מזיוף רדוד פשוט (עריכה אנושית בלבד), דרך זיוף עמוק מבוסס בינה מלאכותית, ועד "זיוף ליינסטר" — זיוף עמוק שעבר שכבת עריכה נוספת המדמה פגמים טבעיים, ולכן הקשה ביותר לחשיפה.</p>
</div>"""

def three_col_diagram(fig_label, title, cols):
    # cols: list of (icon, label, items[])
    parts = []
    for icon, label, items in cols:
        lis = "".join(f"<li>{i}</li>" for i in items)
        parts.append(f"""<div class="roadmap-col">
      <h3>{icon} {label}</h3>
      <ul style="list-style:disc;padding-inline-start:18px;">{lis}</ul>
    </div>""")
    return f"""<div class="diagram-wrap reveal">
  <p class="fig-legend" style="margin-bottom:16px;"><b>{fig_label}.</b> {title}</p>
  <div class="roadmap">{''.join(parts)}</div>
</div>"""

FIG2_HTML = three_col_diagram(
    "איור 2 (שחזור)",
    "מאפייני זיוף רדוד לפי סוג מדיה — עריכה בסיסית ללא בינה מלאכותית, המשנה הקשר ולא תוכן.",
    [
        ("🔊", "אודיו", ["שינוי מהירות/גובה צליל", "חיתוך והדבקה של דיבור", "שינוי סדר מילים"]),
        ("🎬", "וידאו", ["האטה/האצה של קטע", "חיתוך סצנות (Cropping)", "שינוי סדר אירועים", "השמטת רכיבים חזותיים"]),
        ("🖼️", "תמונה", ["הוספה/הסרה של אובייקטים", "שינוי תאורה וצללים", "חיתוך רכיבים מזהים"]),
    ],
)

FIG3_HTML = three_col_diagram(
    "איור 3 (שחזור)",
    "מאפייני זיוף רדוד היברידי לפי סוג מדיה — שילוב עריכה ידנית עם רכיבי AI מוגבלים.",
    [
        ("🔊", "אודיו היברידי", ["המרת קול (Voice Conversion)", "הדבקת מילה/משפט משוכפל-AI לתוך הקלטה אמיתית", "קשה לזיהוי — משלב דיבור אמיתי וסינתטי"]),
        ("🎬", "וידאו היברידי", ["ייצוב תמונה מבוסס-AI", "כלי סנכרון שפתיים (Lip-sync)", "פילטרים לשילוב פנים (Facial Blending)"]),
        ("🖼️", "תמונה היברידית", ["שינוי הבעות פנים ב-AI", "החלפת רקע גנרטיבית", "רטוש עדין (Generative Fill)"]),
    ],
)

FIG4_SVG = """<div class="diagram-wrap reveal">
<svg viewBox="0 0 500 400" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="שלושה תחומי איום מרכזיים">
  <g transform="translate(250,200)">
    <circle r="170" fill="none" stroke="var(--line)" stroke-width="1"/>
    <circle r="115" fill="none" stroke="var(--line)" stroke-width="1"/>
    <circle r="60" fill="var(--accent-soft)" stroke="var(--accent)" stroke-width="1.5"/>
    <text y="-6" text-anchor="middle" font-size="13" font-weight="700">איום</text>
    <text y="14" text-anchor="middle" font-size="13" font-weight="700">מיידי</text>

    <g text-anchor="middle" font-size="13" font-weight="700">
      <circle cx="0" cy="-140" r="26" fill="var(--paper-raised)" stroke="var(--accent)" stroke-width="2.5"/>
      <text x="0" y="-136">👤</text>
      <text x="0" y="-185">אישי (Personnel)</text>
      <text x="0" y="-168" font-size="10.5" font-weight="400" fill="var(--ink-soft)">התחזות, סחיטה</text>

      <circle cx="121" cy="70" r="26" fill="var(--paper-raised)" stroke="var(--amber)" stroke-width="2.5"/>
      <text x="121" y="74">⚖️</text>
      <text x="150" y="115" font-size="12">משפטי</text>
      <text x="150" y="130" font-size="10.5" font-weight="400" fill="var(--ink-soft)">(Judicial)</text>

      <circle cx="-121" cy="70" r="26" fill="var(--paper-raised)" stroke="var(--red)" stroke-width="2.5"/>
      <text x="-121" y="74">🏢</text>
      <text x="-150" y="115" font-size="12">תפעולי / אבטחתי</text>
      <text x="-150" y="130" font-size="10.5" font-weight="400" fill="var(--ink-soft)">(Operational)</text>
    </g>
  </g>
</svg>
<p class="fig-legend"><b>איור 4 (שחזור).</b> שלושה תחומי איום מרכזיים שבהם מנוצלים זיופים עמוקים וזיופים רדודים, כשהסיכון המיידי ביותר במרכז ומתפשט החוצה בציר הזמן: פגיעה באנשים, ערעור הליכים משפטיים, וניצול פרצות תפעוליות/אבטחתיות בארגונים.</p>
</div>"""


COMPARE_TABLE_HTML = """
<h2 id="sec-1-compare">טבלת השוואה מהירה — סוגי מדיה מניפולטיבית</h2>
<div class="compare-table-wrap reveal">
  <table class="compare-table">
    <thead>
      <tr><th>קטגוריה</th><th>שימוש ב-AI</th><th>מורכבות עריכה</th><th>קלות זיהוי (יחסית)</th><th>דוגמה אופיינית</th></tr>
    </thead>
    <tbody>
      <tr>
        <td><span class="compare-tag good">זיוף רדוד (Shallowfake)</span></td>
        <td>ללא שימוש בבינה מלאכותית</td>
        <td>נמוכה — עריכה ידנית בסיסית</td>
        <td><span class="ease-badge easy">קל יחסית</span></td>
        <td>האטת וידאו, חיתוך והדבקת דיבור, שינוי הקשר</td>
      </tr>
      <tr>
        <td><span class="compare-tag warn">זיוף עמוק (Deepfake)</span></td>
        <td>מלא — GAN / מודל דיפוזיה</td>
        <td>גבוהה — נדרש מודל מאומן ונתוני אימון</td>
        <td><span class="ease-badge medium">בינוני</span></td>
        <td>החלפת פנים בווידאו, שכפול קול (Voice Cloning)</td>
      </tr>
      <tr>
        <td><span class="compare-tag bad">זיוף ליינסטר (Leinster)</span></td>
        <td>מלא + שכבת עריכה נוספת</td>
        <td>גבוהה מאוד — הסוואה מכוונת של פגמים</td>
        <td><span class="ease-badge hard">קשה מאוד</span></td>
        <td>זיוף עמוק עם הוספת רעש/פילטר מדומה</td>
      </tr>
    </tbody>
  </table>
</div>
"""


def inject_glossary_terms(html_body, entries):
    """עוטף את ההופעה הראשונה של כל מונח מהמילון (בגוף הפרק) ב-span עם טולטיפ.
    פועל רק על טקסט שמחוץ לתגיות HTML, ומבטיח עטיפה של ההופעה הראשונה בלבד
    לכל מונח (בכל פרק בנפרד, כי הפונקציה נקראת מחדש עבור כל פרק)."""
    terms = [e for e in entries if e[0] and e[0].strip()]
    if not terms:
        return html_body
    terms.sort(key=lambda e: -len(e[0]))
    term_map = {e[0]: e for e in terms}
    pattern = re.compile("|".join(re.escape(t[0]) for t in terms))
    used = set()

    def repl(m):
        term = m.group(0)
        if term in used:
            return term
        entry = term_map.get(term)
        if not entry:
            return term
        used.add(term)
        _, _, definition = entry
        safe_def = html.escape(definition, quote=True)
        return f'<span class="gloss-term" tabindex="0" data-def="{safe_def}">{term}</span>'

    segments = re.split(r"(<[^>]+>)", html_body)
    for i, seg in enumerate(segments):
        if seg.startswith("<"):
            continue
        segments[i] = pattern.sub(repl, seg)
    return "".join(segments)


CHAPTER_EXTRAS = {
    1: {
        "takeaways": [
            "זיוף עמוק (Deepfake) נוצר באמצעות טכניקות למידת מכונה מתקדמות (GAN, מודלי דיפוזיה) והופך לבלתי ניתן להבחנה ממדיה אותנטית.",
            "<b>עקרון ליינסטר (The Leinster Principle):</b> זיופים עמוקים \"משוכללים\" בכוונה בעזרת פגמים הקשריים (רעש, פילטרים) כדי לדמות אי-שלמות טבעית ולעקוף זיהוי אנושי ומכונתי כאחד.",
            "זיוף רדוד (Shallowfake) אינו משתמש בבינה מלאכותית כלל — הוא מסתמך על עריכה בסיסית (חיתוך, הדבקה, שינוי מהירות) כדי לעוות משמעות, אך יכול להיות מזיק באותה מידה.",
            "הגישה המומלצת: מעבר מ״תפיסת מזויפים״ ל<b>אימות אותנטיות</b> — ביסוס שרשרת משמורת אמינה ומקור מאומת כבר מתחילת החקירה.",
            "דיוק זיהוי אנושי של דיפייקים עומד על כ-50-60% בלבד — קרוב לניחוש אקראי.",
        ],
        "quiz": [
            ("מהו \"עקרון ליינסטר\" (The Leinster Principle)?", [
                "שיטה סטטיסטית לזיהוי זיופים באמצעות בדיקת רעש רקע בלבד",
                "תופעה שבה זיופים עמוקים משולבים בכוונה עם פגמים הקשריים (כמו רעש או פילטרים) כדי לדמות פגמים טבעיים ולעקוף זיהוי",
                "חוק בינלאומי המסדיר שימוש בבינה מלאכותית ליצירת מדיה",
                "כלי תוכנה לזיהוי זיוף רדוד בלבד",
            ], 1, "עקרון ליינסטר מתאר הוספה מכוונת של פגמים הקשריים לזיוף עמוק, כדי להקשות הן על זיהוי אנושי והן על זיהוי אוטומטי."),
            ("מה ההבדל המרכזי בין זיוף עמוק לזיוף רדוד?", [
                "זיוף עמוק משתמש בבינה מלאכותית ליצירת תוכן סינתטי, בעוד זיוף רדוד מבוסס על עריכה ידנית פשוטה של תוכן אמיתי, ללא AI",
                "זיוף רדוד תמיד יקר יותר להפקה",
                "זיוף עמוק תמיד קל יותר לזיהוי בעין בלתי מזוינת",
                "אין הבדל מהותי — שני המונחים מתארים את אותה תופעה",
            ], 0, "זיוף עמוק = תוכן שנוצר/שונה על ידי AI; זיוף רדוד = עריכה ידנית של תוכן אמיתי, ללא מעורבות בינה מלאכותית."),
            ("מהי הגישה המומלצת החדשה שהמדריך מציע, במקום התמקדות בלעדית ב\"תפיסת מזויפים\"?", [
                "פיתוח כלי AI מתקדמים יותר לזיהוי בלבד",
                "מעבר לדגש על אימות מדיה (Media Authentication): בדיקת מה אמיתי, ביסוס שרשרת משמורת ואימות מקור מתחילת החקירה",
                "הסתמכות בלעדית על עדי ראייה אנושיים",
                "איסור מוחלט על שימוש במדיה דיגיטלית כראייה",
            ], 1, "המדריך קורא למעבר מגישה של \"תפיסת מזויפים\" לגישה פרואקטיבית של אימות אותנטיות מתחילת הטיפול בראיה."),
        ],
    },
    2: {
        "takeaways": [
            "מאז 2022 יצירת דיפייקים הפכה נגישה בהרבה: כמות הדיפייקים המופצים ברשת קפצה מ-500,000 (2023) ל-8 מיליון (2025) — עלייה של כ-1,500%.",
            "הונאות קוליות מבוססות-AI גדלות ב-650% משנה לשנה, עם תחזית להפסדים גלובליים של עד 44.5 מיליארד דולר בשנה.",
            "יעדי הזיוף השתנו: מדמויות ציבור בעיקר (2022-2024) לאזרחים פרטיים רבים יותר ב-2025 (סחיטה, הונאות רומנטיות, פורנוגרפיית נקמה).",
            "<b>\"דיבידנד השקרן\" (Liar's Dividend):</b> ראיות אמיתיות נדחות בטענת \"זה מזויף\" — מה שמערער אמון בראיות דיגיטליות בכלל.",
            "שלושה תחומי איום מרכזיים: אישי (Personnel), משפטי (Judicial), ותפעולי/אבטחתי (Operational/Security).",
        ],
        "quiz": [
            ("לפי הדיווח שצוין במדריך, כמה הפסידו קורבנות הונאות דיפייק ברבעון הראשון של 2025 בלבד (הערכה עולמית)?", [
                "2 מיליון דולר", "200 מיליון דולר", "25.6 מיליון דולר", "44.5 מיליארד דולר",
            ], 1, "לפי דו״ח Resemble.AI, בעבור Q1 2025 בלבד הוערך הנזק בכ-200 מיליון דולר מהונאות דיפייק."),
            ("מהו \"דיבידנד השקרן\" (Liar's Dividend)?", [
                "רווח כספי שמפיק יוצר הדיפייק מהונאה מוצלחת",
                "האפשרות לדחות ראיה אמיתית בטענה שהיא \"מזויפת\", כך שראיות אותנטיות מאבדות אמינות",
                "פיצוי כספי הניתן לקורבנות דיפייק בבתי משפט",
                "שיטת זיהוי המבוססת על ניתוח אודיו",
            ], 1, "ככל שהמודעות לדיפייקים גוברת, כך גדל הסיכון שראיות אמיתיות יידחו כ\"מזויפות\" — זהו \"דיבידנד השקרן\"."),
            ("מקרה הבנק בהונג קונג הדגים בעיקר סיכון של...", [
                "שימוש בשיחת ועידה מבוססת דיפייק לעקיפת אימות פנים-מול-פנים והנעת עובד להעביר כספים",
                "פריצה ישירה לשרתי הבנק וגניבת מידע",
                "זיוף רדוד של מסמכי הלוואה בלבד",
                "תקיפת סייבר קלאסית ללא מעורבות מדיה סינתטית",
            ], 0, "כל משתתפי שיחת הווידאו, כולל דמות שהתחזתה לסמנכ״ל הכספים, היו דמויות דיפייק — מה שהוביל להעברת כ-25.6 מיליון דולר."),
            ("מדוע נגנזו האישומים הקשורים לדיפייק ב\"פרשת אם המעודדות מפנסילבניה\"?", [
                "כי הוכח פורנזית וחד-משמעית שהחומר אינו מזויף",
                "כי המשטרה ביססה את המסקנות על בדיקה חזותית \"בעין בלתי מזוינת\" בלבד, ללא ניתוח פורנזי או אימות מומחה",
                "כי הנאשמת זוכתה על ידי בית המשפט העליון",
                "כי לא נמצאו קורבנות בתיק",
            ], 1, "התביעה נסוגה מהאישומים לאחר שהתגלה שההליך לא כלל בדיקה פורנזית מקצועית, אלא הערכה חזותית בלבד."),
        ],
    },
    3: {
        "takeaways": [
            "<b>מקור ותולדות הקובץ (Provenance)</b> הם קו ההגנה הראשון, ולעיתים היחיד, מפני מניפולציה של מדיה.",
            "מטא-נתונים (זמן, GPS, דגם מכשיר) יכולים לחשוף אי-התאמות, אך ניתנים גם הם למחיקה או זיוף — יש לתעד אותם מוקדם ובאופן מאובטח.",
            "גיבוב (Hashing) והטבעת סימני מים יעילים בעיקר כשהם מיושמים בנקודת הצילום/ההקלטה עצמה (למשל במצלמות גוף של שוטרים).",
            "בלוקצ'יין, יוזמת CAI ותקן C2PA מציעים מסגרות טכנולוגיות חדשות לתיעוד מקור — אך אינן פתרון קסם, ויש לשלבן עם שיטות פורנזיות מסורתיות.",
            "שרשרת משמורת תקינה ממלאת שלוש פונקציות: שמירת סף (Gatekeeping), הקשרה (Contextualizing) ותימוכין (Corroborating).",
        ],
        "quiz": [
            ("מהן שלוש הפונקציות המרכזיות שממלא \"מקור ותולדות הקובץ\" בתהליך הפורנזי?", [
                "הצפנה, דחיסה, גיבוי",
                "שמירת סף (Gatekeeping), הקשרה (Contextualizing) ותימוכין (Corroborating)",
                "זיהוי, אימות, שיפוט",
                "מחיקה, שחזור, ארכוב",
            ], 1, "שלוש הפונקציות: החרגת חומר עם מקור לא מאומת, מתן הקשר לתוכן הקובץ, וחיזוק ממצאים אנליטיים דרך השוואה למקור."),
            ("מדוע הטבעת סימני מים (watermarking) אינה יכולה לשמש כפתרון עצמאי?", [
                "היא יקרה מדי ליישום",
                "אם שיטת ההטבעה נחשפת, ניתן להוסיף סימן מים לתוכן שלא הכיל אותו במקור, או להסירו מתוכן שכן הכיל אותו",
                "היא עובדת רק על קבצי טקסט",
                "אין לה תוקף משפטי באף מדינה",
            ], 1, "חשיפת שיטת ההטבעה מאפשרת זיוף או הסרה של הסימן עצמו, ולכן יש להשתמש בה כחלק ממערך רחב יותר, לא כפתרון בודד."),
            ("מהו תפקידו של תקן C2PA?", [
                "חוק בינלאומי האוסר יצירת דיפייקים",
                "תקן פתוח המגדיר כיצד מוטבעים ומאומתים מטא-נתונים על מקור, עריכה והפצה של קובץ מדיה",
                "כלי לזיהוי קול מזויף בלבד",
                "פרוטוקול הצפנה של תעבורת רשת",
            ], 1, "C2PA הוא תקן טכני פתוח (בהובלת יוזמת CAI ושותפות תעשייתית רחבה) לאימות מקור ואמינות תוכן דיגיטלי."),
        ],
    },
    4: {
        "takeaways": [
            "זיהוי פורנזי מתחלק לשני שלבים: <b>זיהוי ראשוני</b> (Identification — מעלה דגל אדום, יכול להיעשות ע״י כל גורם) ו<b>אימות</b> (Authentication — עיבוד פורנזי מלא שמבצע מומחה).",
            "אין להסתמך על שיטת זיהוי בודדת — יש לשלב מספר שיטות משלימות (מקור, מטא-נתונים, הקשר) תוך שימוש ברמת ביטחון ולא בהחלטה בינארית.",
            "קיים פער השקעה משמעותי בין זיהוי וידאו/תמונה לזיהוי אודיו — תחום האודיו זקוק להשקעה ותשומת לב רבה יותר.",
            "שיטות זיהוי חתימה קלאסיות (Sobel, Canny, Laplacian ועוד) עדיין רלוונטיות ומשלימות כלים מבוססי-AI.",
            "ניתוח תדר רשת החשמל (ENF) יכול לשמש כ\"חותמת זמן ומקום\" ייחודית להקלטות.",
        ],
        "quiz": [
            ("מהו ההבדל בין שלב ה\"זיהוי\" (Identification) לשלב ה\"אימות\" (Authentication)?", [
                "שני המונחים זהים לחלוטין",
                "זיהוי הוא הרמת דגל ראשונית שיכולה להיעשות ע״י כל גורם, בעוד אימות הוא עיבוד פורנזי מלא ומכריע יותר, המבוצע ע״י מומחה",
                "אימות מתבצע רק על ידי בינה מלאכותית",
                "זיהוי מתבצע רק בתוך אולם בית המשפט",
            ], 1, "זיהוי הוא שלב ראשוני של הרמת חשד; אימות הוא הליך פורנזי מלא המבוסס על סמנים מבוססים ומבוצע במסגרת מקצועית."),
            ("מהי מטרת \"ניתוח תדר רשת החשמל\" (ENF Analysis)?", [
                "למדוד את איכות הדחיסה של קובץ האודיו",
                "לזהות תנודות בתדר רשת החשמל (50/60Hz) שנקלטות בטעות בהקלטה, המשמשות כ\"חותמת זמן ומקום\" ייחודית",
                "לחשב את עוצמת האות הכוללת",
                "לזהות שינויי טמפרטורה במיקרופון",
            ], 1, "תנודות תדר רשת החשמל משתנות באופן ייחודי בזמן ובמקום, ולכן ניתן להשוותן למאגר ייחוס לזיהוי מועד/מיקום הקלטה."),
            ("מדוע מדגיש המדריך שאין להסתמך על שיטת זיהוי בודדת?", [
                "כי כל השיטות יקרות מדי ליישום",
                "כי כל שיטה בפני עצמה מוגבלת, וגורמי איום מפתחים כל הזמן טכניקות לעקיפתה — יש לשלב מספר שיטות משלימות",
                "כי החוק אוסר שימוש בשיטה אחת בלבד",
                "כי שיטה בודדת דורשת רישיון מיוחד",
            ], 1, "המדריך קורא לגישה הוליסטית המשלבת מספר שיטות, מקור ומטא-נתונים, ולא הסתמכות על כלי או שיטה בודדים."),
        ],
    },
    5: {
        "takeaways": [
            "כלי זיהוי מבוססי AI/ML הם ברובם \"קופסה שחורה\" (Black Box) — לא ניתן להסביר אילו גורמים (loci) הביאו למסקנה, מה שמקשה על קבילות משפטית.",
            "בהשוואה לניתוח DNA (סף מינימלי של 95% ודאות, בר-הסבר ושחזור מלא), פלט זיהוי דיפייק הוא בגדר \"ניחוש הסתברותי\" ולא מסקנה סטטיסטית מאומתת.",
            "כלי AI/ML מתאימים כיום יותר לשימוש מודיעיני (זיהוי כיווני חקירה) מאשר לשימוש ראייתי-פורנזי ישיר.",
            "<b>תער אוקהאם:</b> פתרון עם פחות הנחות (פיקוח אנושי + כלים ברי-הסבר) עדיף על שכבות מורכבות של קופסאות שחורות.",
            "אין להשתמש בכלי AI ללא פיקוח אנושי מלא בהקשר פורנזי — לא כיום ולא בעתיד הנראה לעין.",
        ],
        "quiz": [
            ("מה נדרש כדי שתוצאת כלי AI תיחשב קבילה בבית משפט, בהשוואה לניתוח DNA?", [
                "סף ביטחון של 50% בלבד",
                "יכולת הסבר מלאה של הגורמים (loci) שהובילו למסקנה, יחד עם שחזוריות ועמידה בביקורת עמיתים — דבר שרוב כלי ה-AI הנוכחיים אינם מספקים",
                "אין צורך בסף ביטחון כלל",
                "די באישור של יצרן הכלי",
            ], 1, "בניתוח DNA ניתן להצביע במדויק על ה\"loci\" שהובילו למסקנה; ברוב כלי ה-AI זה בלתי אפשרי, ולכן קבילותם מוגבלת."),
            ("כיצד בא לידי ביטוי \"תער אוקהאם\" (Occam's Razor) בשילוב AI בפורנזיקה דיגיטלית?", [
                "יש להעדיף תמיד את הכלי הטכנולוגי המתקדם ביותר",
                "יש להעדיף את הפתרון עם פחות הנחות בלתי-מוכחות — פיקוח אנושי עם כלים ברי-הסבר, על פני קופסה שחורה מורכבת",
                "יש להשתמש רק בשיטות ידניות ולעולם לא ב-AI",
                "יש להפעיל כמה שיותר מודלים בו-זמנית",
            ], 1, "פתרון עם פחות הנחות (בקרה אנושית + הסבירות) מועדף על פתרון \"קופסה שחורה\" שדורש הנחת אמון לא-מוסברת."),
            ("מהו התפקיד המומלץ העיקרי של כלי AI/ML בזיהוי דיפייקים, לפי המדריך?", [
                "החלטה סופית ובלעדית לגבי קבילות ראייה",
                "כלי עזר מודיעיני/חוקר לכיווני חקירה, בכפוף לאימות ופיקוח אנושי מלא",
                "תחליף מלא לניתוח פורנזי אנושי",
                "כלי המיועד לשימוש רק בתוך אולמות בית המשפט",
            ], 1, "המדריך ממליץ להשתמש ב-AI/ML בעיקר לצורך גיבוש כיווני חקירה מודיעיניים, לא כתחליף לאימות פורנזי אנושי-מוסבר."),
        ],
    },
    6: {
        "takeaways": [
            "הכשרה בתחום מתחלקת לשלושה מגזרים: אקדמי, מקצועי-משטרתי (Vocational) וייעודי-יצרן (Proprietary) — לכל אחד יתרונות וחסרונות, ושילוב ביניהם הוא הגישה המומלצת.",
            "<b>תלות באמת יסוד (Ground Truth Dependency):</b> לא ניתן לזהות מזויף מבלי לדעת קודם איך נראית מדיה אותנטית — הכשרה בסיסית היא תנאי הכרחי.",
            "<b>הטיית \"מתחזה\" (Impostor Bias):</b> מודעות-יתר לדיפייקים עלולה לגרום לחוקרים לפקפק בראיות אמיתיות ללא בסיס עובדתי.",
            "אין תחליף להכשרה מתמשכת (CPD) — הנוף הטכנולוגי משתנה מדי יום.",
            "מוכנות למתן עדות בבית משפט דורשת: ניסוח שיטות ומגבלותיהן, מסקנות שחזוריות וניתנות להגנה, והכנה לחקירה נגדית.",
        ],
        "quiz": [
            ("מהם שלושת מגזרי ההכשרה שהמדריך מזהה בתחום?", [
                "פרטי, ציבורי, צבאי",
                "אקדמי, מקצועי-משטרתי (Vocational) וייעודי-יצרן (Proprietary)",
                "מקומי, ארצי, בינלאומי",
                "בסיסי, מתקדם, מומחה",
            ], 1, "כל מגזר תורם היבט שונה: קפדנות אקדמית, רלוונטיות תפעולית, ומומחיות ספציפית-לכלי — שילוב ביניהם הוא האידיאלי."),
            ("מהי \"הטיית מתחזה\" (Impostor Bias)?", [
                "נטייה לפרש נכון כל תוכן דיפייק",
                "נטייה לפקפק ביתר על אותנטיות של מדיה אמיתית וחוקית, כתוצאה ממודעות-יתר לקיומם של דיפייקים — לא מבוסס על תוכן הקובץ עצמו",
                "הטיה שמופיעה רק אצל מומחי AI",
                "חוסר אמון גורף של בתי משפט במומחים פורנזיים",
            ], 1, "ללא הכשרה מתאימה במדיה אותנטית, נוצרת נטייה לפקפק בראיות אמיתיות רק בגלל המודעות הגוברת לקיום דיפייקים."),
            ("מהם שלושת המרכיבים הנדרשים ל\"מוכנות למתן עדות בבית המשפט\" (Courtroom Readiness)?", [
                "ידע כללי, ניסיון, המלצות",
                "יכולת לנסח שיטות ומגבלותיהן, מסקנות שחזוריות ומגובות באימות, והכנה למתן עדות תחת חקירה נגדית",
                "תואר אקדמי, רישיון, ותק",
                "גישה לכלי AI מתקדמים בלבד",
            ], 1, "שלושת המרכיבים מבטיחים שהמומחה יוכל להגן על ממצאיו ועל אמינותו האישית תחת ביקורת אדוורסרית."),
        ],
    },
    7: {
        "takeaways": [
            "ברוב מדינות העולם אין עדיין חקיקה ממוקדת וברורה נגד דיפייקים/זיופים רדודים — אכיפה נשענת על חוקים כלליים (הוצאת דיבה, הטרדה, זכויות יוצרים) שאינם מותאמים לאיום.",
            "הצעת חוק בדנמרק מציעה להעניק לאזרחים בעלות משפטית על פניהם, קולם ודמותם — צעד ראשון, אך במסגרת אזרחית בלבד (לא פלילית).",
            "\"דיבידנד השקרן\" מהווה אתגר ראייתי ייחודי: חשודים יכולים לנסות לפסול ראיות אמיתיות בטענת \"AI\".",
            "קיימת מערכת תקנים בינלאומיים רלוונטיים (ISO/IEC 17025, 17020, 21043, 27043, 27037, 42001; ENFSI; SWGDE; NIST SP 800-86; C2PA) שניתן להסתמך עליה בבניית נהלי עבודה.",
            "נדרשת השקעה ייעודית ביחידות פורנזיקה אודיו-ויזואלית מקצועיות, שכן יחידות פורנזיקה דיגיטלית כלליות לרוב חסרות מומחיות ספציפית בתחום.",
        ],
        "quiz": [
            ("מהו האתגר המרכזי המתואר בפרק זה בנוגע למצב החקיקה העולמי?", [
                "חוסר תקציב לאכיפת חוק",
                "שונות רחבה ופרגמנטציה בין מדינות בחוקים הרלוונטיים לדיפייקים, המקשה על אכיפה עקבית ושיתוף פעולה חוצה-גבולות",
                "ריבוי שפות בהליכים משפטיים",
                "מחסור בשופטים בתחום הפלילי",
            ], 1, "בהיעדר תיאום בינלאומי, כל מדינה מפתחת מסגרת שונה, מה שמקשה מאוד על חקירות ושיתופי פעולה חוצי-גבולות."),
            ("מה כולל תקן C2PA שהוזכר גם בפרק 3?", [
                "חוק פלילי בינלאומי נגד דיפייקים",
                "תקן טכני לאימות מקור ואמינות תוכן דיגיטלי",
                "פרוטוקול תקשורת בין מכשירי משטרה",
                "שיטת חקירה משטרתית מסורתית",
            ], 1, "C2PA הוא תקן טכני (לא חוק) שמסייע בביסוס מקור ותולדות קובץ באמצעות מטא-נתונים מאובטחים."),
        ],
    },
    8: {
        "takeaways": [
            "מדיה מניפולטיבית מבוססת-AI היא כבר לא איום עתידי — היא כאן, נפוצה ומשוכללת יותר מדי יום.",
            "אוריינות AI (AI Media Literacy) לגורמי אכיפת חוק היא הבסיס ההכרחי לכל שאר הפתרונות.",
            "זהו מסמך \"חי\" (Living Document) הדורש עדכון שוטף — אין פתרון \"חד-פעמי\" לבעיה.",
            "השאלה המרכזית שהמדריך מציב: \"האם אנחנו בטוחים שהראיות שלנו נקיות מהשפעת AI?\"",
        ],
        "quiz": [
            ("מהי ההמלצה המרכזית \"לטווח קצר\" (Short Term) המופיעה במדריך?", [
                "חתימה על אמנה בינלאומית מחייבת",
                "פיתוח אוריינות מדיה מבוססת-AI (AI Media Literacy) עבור גורמי אכיפת חוק",
                "הקמת בית משפט בינלאומי ייעודי",
                "איסור מוחלט על שימוש בבינה מלאכותית במשטרה",
            ], 1, "אמנה בינלאומית מוגדרת כהמלצת טווח ארוך; ההמלצה המיידית ביותר היא בניית אוריינות AI בסיסית בקרב אנשי אכיפת החוק."),
            ("מדוע המדריך מתאר את עצמו כ\"מסמך חי\" (Living Document)?", [
                "כי הוא מתעדכן אוטומטית באינטרנט",
                "כי קצב ההתפתחות הטכנולוגית מהיר מדי, וההנחיות דורשות עדכון ותחזוקה שוטפים כדי להישאר רלוונטיות",
                "כי הוא מבוסס על נתונים בזמן אמת מבתי משפט",
                "כי הוא מתפרסם מחדש כל שנה קלנדרית בלבד",
            ], 1, "המדריך מדגיש שהמחקר עלול לפגר אחרי הטכנולוגיה, ולכן יש צורך בעדכון ותחזוקה מתמשכים."),
        ],
    },
}


def build_chapter_extra_html(num):
    extra = ""
    if num == 1:
        extra += COMPARE_TABLE_HTML
    if num == 2:
        extra += '<h2 id="sec-2-5-cases">מקרים מהעולם האמיתי — כרטיסי סיכום</h2>' + CASE_STUDIES_HTML
        extra += FIG4_SVG
    return extra


def build_mid_chapter_inserts(num):
    """תרשימים שמוכנסים בסמוך לתחילת גוף הפרק (לפני שאר התוכן)."""
    if num == 2:
        return FIG1_SVG + FIG2_HTML + FIG3_HTML
    return ""


# ---------------------------------------------------------------------------
# 4. בניית תפריט צד לפרקים
# ---------------------------------------------------------------------------

CHAPTER_TITLES_FALLBACK = {
    1: "מבוא", 2: "מפת האיומים", 3: "מניעה במסגרת שרשרת המשמורת",
    4: "זיהוי", 5: "בינה מלאכותית ולמידת מכונה",
    6: "הכשרה והדרכה באיתור זיוף עמוק", 7: "רגולציה ושיקולים משפטיים",
    8: "סיכום והמלצות",
}

RESEARCH_CHAPTER_TITLES_FALLBACK = {
    1: "מבוא", 2: "איומי מדיה סינתטית בדרום-מזרח אסיה",
    3: "תגובת גורמי אכיפת החוק לאיומי מדיה סינתטית",
    4: "המלצות", 5: "תפקידה של אינטרפול", 6: "סיכום",
}


def build_side_nav(chapters, current_chapter, rel):
    out = ['<nav class="side-nav" aria-label="ניווט בין פרקי המדריך">']
    out.append('<p class="side-kicker">המדריך</p>')
    for n in range(1, 9):
        ch = chapters.get(n, {"title": CHAPTER_TITLES_FALLBACK[n]})
        href = f"{rel}chapters/ch{n}.html"
        cur_cls = "ch-link current" if n == current_chapter else "ch-link"
        out.append(
            f'<a class="{cur_cls}" data-ch="{n}" href="{href}">'
            f'<span class="ch-check" aria-hidden="true"></span>{n}. {ch["title"]}</a>'
        )
        if n == current_chapter:
            subs = extract_subsections(ch.get("body", ""))
            if subs:
                out.append('<div class="side-sub">')
                for num, title in subs:
                    out.append(f'<a href="#{slug(num)}">{num} {title}</a>')
                out.append('</div>')
    out.append('<p class="side-kicker">עוד בחומרי ההדרכה</p>')
    out.append(f'<a href="{rel}research.html">מחקר: Forged Realities</a>')
    out.append(f'<a href="{rel}glossary.html">מילון מונחים</a>')
    out.append(f'<a href="{rel}final-quiz.html">מבחן מסכם</a>')
    out.append(f'<a href="{rel}cheat-sheet.html">דף סיכום להדפסה</a>')
    out.append(f'<a href="{rel}source.html">מסמך המקור (PDF)</a>')
    out.append(f'<a href="{rel}references.html">מקורות והערות שוליים</a>')
    out.append(f'<a href="{rel}about.html">אודות המדריך</a>')
    out.append('</nav>')
    return "\n".join(out)


def chapter_pager(num):
    parts = []
    if num > 1:
        prev = CHAPTER_TITLES_FALLBACK[num - 1]
        parts.append(f'<a class="pager-link prev" href="ch{num-1}.html"><span class="pager-dir">&larr; הקודם</span><div class="pager-title">{num-1}. {prev}</div></a>')
    else:
        parts.append('<span></span>')
    if num < 8:
        nxt = CHAPTER_TITLES_FALLBACK[num + 1]
        parts.append(f'<a class="pager-link next" href="ch{num+1}.html"><span class="pager-dir">הבא &rarr;</span><div class="pager-title">{num+1}. {nxt}</div></a>')
    else:
        parts.append(f'<a class="pager-link next" href="../glossary.html"><span class="pager-dir">הבא &rarr;</span><div class="pager-title">מילון מונחים</div></a>')
    return f'<div class="chapter-pager">{"".join(parts)}</div>'


# ---------------------------------------------------------------------------
# 5. עמודי פרק
# ---------------------------------------------------------------------------

def build_chapter_page(num, chapters, glossary_entries=None):
    ch = chapters[num]
    title = ch["title"]
    body_html = render_md(ch["body"], footnote_href="../references.html#fn-")
    body_html = inject_glossary_terms(body_html, glossary_entries or [])
    if num == 4:
        body_html = wrap_as_accordion(body_html)
    rel = "../"
    side_nav = build_side_nav(chapters, num, rel)
    mid_insert = build_mid_chapter_inserts(num)
    extra_html = build_chapter_extra_html(num)
    extras = CHAPTER_EXTRAS.get(num, {"takeaways": [], "quiz": []})
    takeaways_html = takeaway_box(extras["takeaways"]) if extras["takeaways"] else ""
    quiz_html = quiz_block(num, extras["quiz"]) if extras["quiz"] else ""

    page = []
    page.append(page_head(f"{num}. {title} — מדריך SynthWave", rel))
    page.append(header_html(rel, "chapters/"))
    page.append('<div class="side-nav-backdrop" hidden></div>')
    page.append('<main class="wrap">')
    page.append('<div class="doc-layout">')
    page.append(side_nav)
    page.append('<div class="doc-main">')
    page.append(f'''<div class="chapter-eyebrow reveal">
      <span class="chnum">פרק {num}</span>
      <span class="chkicker">INTERPOL Project SynthWave &middot; Global Guideline</span>
    </div>
    <h1 class="reveal">{title}</h1>''')
    page.append(mid_insert)
    page.append(f'<div class="article-body reveal">{body_html}</div>')
    page.append(extra_html)
    page.append(takeaways_html)
    page.append(quiz_html)
    page.append(f'''<div class="chapter-complete reveal">
      <button class="complete-btn" type="button" data-ch="{num}">
        <span class="complete-icon" aria-hidden="true">✓</span>
        <span class="complete-text">סמן פרק זה כהושלם</span>
      </button>
    </div>''')
    page.append(chapter_pager(num))
    page.append('</div>')  # doc-main
    page.append('</div>')  # doc-layout
    page.append('</main>')
    page.append(footer_html(rel))
    page.append(scripts_html(rel))
    (CHAPTERS_DIR / f"ch{num}.html").write_text("".join(page), encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. עמוד מילון מונחים
# ---------------------------------------------------------------------------

def parse_glossary(body_md):
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body_md.strip()) if b.strip()]
    entries = []
    for b in blocks:
        lines = b.splitlines()
        term_m = re.match(r"^\*\*(.+?)\*\*\s*$", lines[0].strip())
        if not term_m:
            continue
        term_full = term_m.group(1).strip()
        definition = " ".join(l.strip() for l in lines[1:]).strip()
        m2 = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", term_full)
        if m2:
            he_term, en_term = m2.group(1).strip(), m2.group(2).strip()
        else:
            he_term, en_term = term_full, term_full
        entries.append((he_term, en_term, definition))
    entries.sort(key=lambda e: e[1].lower())
    return entries


def term_slug(en_term):
    s = re.sub(r"[^a-z0-9]+", "-", (en_term or "").lower()).strip("-")
    return f"term-{s}" if s else "term"


def build_glossary_page(glossary_body):
    entries = parse_glossary(glossary_body) if glossary_body else []
    rel = ""
    items_html = []
    last_letter = None
    seen_slugs = set()
    entries_with_ids = []
    for he_term, en_term, definition in entries:
        letter = en_term[0].upper() if en_term else "#"
        if letter != last_letter:
            items_html.append(f'<p class="term-letter">{letter}</p>')
            last_letter = letter
        base_slug = term_slug(en_term)
        term_id = base_slug
        i = 2
        while term_id in seen_slugs:
            term_id = f"{base_slug}-{i}"
            i += 1
        seen_slugs.add(term_id)
        entries_with_ids.append((he_term, en_term, definition, term_id))
        items_html.append(f'''<div class="term-item" id="{term_id}">
      <h3>{he_term} <span class="term-en">({en_term})</span></h3>
      <p>{definition}</p>
    </div>''')

    page = []
    page.append(page_head("מילון מונחים — מדריך SynthWave", rel))
    page.append(header_html(rel, "glossary.html"))
    page.append('<main class="wrap medium">')
    page.append('''<p class="kicker reveal">מילון מונחים</p>
    <h1 class="reveal">מונחי יסוד בזיהוי ואימות מדיה סינתטית</h1>
    <p class="reveal">רשימת המונחים המרכזיים מהמדריך, לפי סדר א״ב באנגלית. ניתן לחפש גם במונח העברי.</p>
    <div class="glossary-search reveal">
      <input type="search" id="glossary-search" placeholder="חיפוש מונח... (עברית או אנגלית)">
    </div>
    <div class="term-list reveal">''')
    page.append("\n".join(items_html) if items_html else '<p>תוכן המילון ייטען כאן לאחר השלמת התרגום.</p>')
    page.append('</div>')
    page.append('</main>')
    page.append(footer_html(rel))
    page.append(scripts_html(rel))
    (ROOT / "glossary.html").write_text("".join(page), encoding="utf-8")
    return entries_with_ids


# ---------------------------------------------------------------------------
# 7. עמוד מקורות/הערות שוליים
# ---------------------------------------------------------------------------

def build_references_page(refs_body):
    rel = ""
    if refs_body:
        body_html = render_md(refs_body)
        body_html = linkify_urls(body_html)
        body_html = add_footnote_anchor_ids(body_html, "fn-")
    else:
        body_html = "<p>יתעדכן לאחר השלמת התרגום.</p>"
    page = []
    page.append(page_head("מקורות והערות שוליים — מדריך SynthWave", rel))
    page.append(header_html(rel, "references.html"))
    page.append(f'''<main class="wrap medium">
    <p class="kicker reveal">מקורות</p>
    <h1 class="reveal">מקורות והערות שוליים</h1>
    <p class="reveal">רשימת כל המקורות המצוטטים במדריך המקורי, לפי סדר הופעתם. לחיצה על מספר הפניה [N] בתוך פרק כלשהו מקפיצה לציטוט המדויק כאן; קישורים חיצוניים ניתנים ללחיצה ופותחים את המקור בכרטיסייה נפרדת.</p>
    <div class="article-body reveal" style="font-size:13.5px;">{body_html}</div>
    </main>''')
    page.append(footer_html(rel))
    page.append(scripts_html(rel))
    (ROOT / "references.html").write_text("".join(page), encoding="utf-8")


# ---------------------------------------------------------------------------
# 8. עמוד "אודות"
# ---------------------------------------------------------------------------

def build_about_page(front, about_body):
    rel = ""
    fh = "references.html#fn-"
    foreword = render_md(front.get("foreword", ""), footnote_href=fh)
    ack = render_md(front.get("ack", ""), footnote_href=fh)
    disclaimer = render_md(front.get("disclaimer", ""), footnote_href=fh)
    exec_summary = render_md(front.get("exec_summary", ""), footnote_href=fh)
    about_interpol = render_md(about_body or "", footnote_href=fh)

    page = []
    page.append(page_head("אודות המדריך — מדריך SynthWave", rel))
    page.append(header_html(rel, "about.html"))
    page.append('<main class="wrap medium">')
    page.append('<p class="kicker reveal">אודות</p><h1 class="reveal">אודות המדריך ופרויקט SynthWave</h1>')
    page.append(RESTRICTED_BANNER)
    page.append(f'<h2>דבר הפתיחה</h2><div class="article-body reveal">{foreword}</div>')
    page.append(f'<h2>תקציר מנהלים</h2><div class="article-body reveal">{exec_summary}</div>')
    page.append(f'''<div class="callout warning reveal">
      <p class="callout-label">⚠️ הבהרה משפטית (Disclaimer)</p>
      <div class="article-body">{disclaimer}</div>
    </div>''')
    page.append(f'<h2>תודות</h2><div class="article-body reveal">{ack}</div>')
    page.append(f'<h2>אודות אינטרפול</h2><div class="article-body reveal">{about_interpol}</div>')
    page.append('</main>')
    page.append(footer_html(rel))
    page.append(scripts_html(rel))
    (ROOT / "about.html").write_text("".join(page), encoding="utf-8")


# ---------------------------------------------------------------------------
# 9. עמוד מקור (PDF)
# ---------------------------------------------------------------------------

def build_source_page():
    rel = ""
    page = f'''{page_head("מסמכי המקור — מדריך SynthWave", rel)}{header_html(rel, "source.html")}
<main class="wrap medium">
  <p class="kicker reveal">מסמכי המקור</p>
  <h1 class="reveal">המסמכים המקוריים של אינטרפול (PDF, אנגלית)</h1>
  {RESTRICTED_BANNER}
  <div class="tabs reveal" role="tablist">
    <button class="tab-btn" data-tab="tab-guideline" role="tab" aria-selected="true">Global Guideline &ndash; False Facades</button>
    <button class="tab-btn" data-tab="tab-research" role="tab" aria-selected="false">Research Study &ndash; Forged Realities</button>
  </div>
  <div id="tab-guideline" class="tab-panel">
    <div class="pdf-frame-wrap reveal">
      <iframe src="assets/source/interpol-synthwave-guideline.pdf" title="INTERPOL Project SynthWave Global Guideline PDF"></iframe>
      <p class="pdf-fallback">אם הקובץ אינו נטען: <a href="assets/source/interpol-synthwave-guideline.pdf">פתיחת ה-PDF בכרטיסייה נפרדת</a>. תרגום מלא לעברית זמין <a href="chapters/ch1.html">בפרקי המדריך</a>.</p>
    </div>
  </div>
  <div id="tab-research" class="tab-panel" hidden>
    <div class="pdf-frame-wrap reveal">
      <iframe src="assets/source/interpol-synthwave-research-forged-realities.pdf" title="INTERPOL Project SynthWave Research Study PDF"></iframe>
      <p class="pdf-fallback">אם הקובץ אינו נטען: <a href="assets/source/interpol-synthwave-research-forged-realities.pdf">פתיחת ה-PDF בכרטיסייה נפרדת</a>. תרגום מלא לעברית זמין <a href="research.html">בעמוד המחקר</a>.</p>
    </div>
  </div>
</main>
{footer_html(rel)}{scripts_html(rel)}'''
    (ROOT / "source.html").write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------------
# 9ג. עמוד המחקר המשלים (Research Study - Forged Realities)
# ---------------------------------------------------------------------------

RESEARCH_SRC = ROOT / "hebrew_translation_research.md"


def build_research_side_nav():
    out = ['<nav class="side-nav" aria-label="ניווט במסמך המחקר">']
    out.append('<p class="side-kicker">אודות המחקר</p>')
    out.append('<a href="#r-foreword">דבר הפתיחה</a>')
    out.append('<a href="#r-exec-summary">תקציר מנהלים</a>')
    out.append('<p class="side-kicker">פרקי המחקר</p>')
    for n in range(1, 7):
        title = RESEARCH_CHAPTER_TITLES_FALLBACK[n]
        out.append(f'<a href="#sec-{n}">{n}. {title}</a>')
    out.append('<p class="side-kicker">עוד</p>')
    out.append('<a href="#r-about">אודות אינטרפול</a>')
    out.append('<a href="#r-refs">מקורות והערות שוליים</a>')
    out.append('<a href="chapters/ch1.html">חזרה למדריך המלא</a>')
    out.append('<a href="source.html">מסמך המקור (PDF)</a>')
    out.append('</nav>')
    return "\n".join(out)


def build_research_page():
    if not RESEARCH_SRC.exists():
        return None
    text = RESEARCH_SRC.read_text(encoding="utf-8")
    sections = split_top_sections(text)
    front, chapters, _glossary, refs_body, about_body = classify(sections, max_chapter=6)

    missing = [n for n in range(1, 7) if n not in chapters]
    if missing:
        print("אזהרה (מחקר): לא נמצאו הפרקים הבאים:", missing)

    rel = ""
    side_nav = build_research_side_nav()

    fh = "#rfn-"
    chapters_html = []
    for n in range(1, 7):
        ch = chapters.get(n)
        if not ch:
            continue
        body_html = render_md(ch["body"], footnote_href=fh)
        chapters_html.append(f'''<section class="research-chapter">
      <div class="chapter-eyebrow reveal">
        <span class="chnum">פרק {n}</span>
        <span class="chkicker">INTERPOL Project SynthWave &middot; Research Study</span>
      </div>
      <h2 id="sec-{n}">{n}. {ch["title"]}</h2>
      <div class="article-body reveal">{body_html}</div>
    </section>''')

    foreword = render_md(front.get("foreword", ""), footnote_href=fh)
    ack = render_md(front.get("ack", ""), footnote_href=fh)
    disclaimer = render_md(front.get("disclaimer", ""), footnote_href=fh)
    exec_summary = render_md(front.get("exec_summary", ""), footnote_href=fh)
    about_interpol = render_md(about_body or "", footnote_href=fh)
    if refs_body:
        refs_html = render_md(refs_body)
        refs_html = linkify_urls(refs_html)
        refs_html = add_footnote_anchor_ids(refs_html, "rfn-")
    else:
        refs_html = ""

    page = []
    page.append(page_head("מחקר: Forged Realities — מדריך SynthWave", rel))
    page.append(header_html(rel, "research.html"))
    page.append('<div class="side-nav-backdrop" hidden></div>')
    page.append('<main class="wrap">')
    page.append('<div class="doc-layout">')
    page.append(side_nav)
    page.append('<div class="doc-main">')
    page.append('''<p class="kicker reveal">מחקר משלים · Project SynthWave</p>
    <h1 class="reveal">Forged Realities — איומי מדיה סינתטית בדרום-מזרח אסיה</h1>
    <p class="reveal">מסמך המחקר המשלים למדריך ההנחיה: בחינה גלובלית של השפעת המדיה הסינתטית על עבודת אכיפת החוק, עם התמקדות במדינות דרום-מזרח אסיה שהשתתפו בפרויקט SynthWave (ברוניי, קמבודיה, אינדונזיה, לאוס, מלזיה, הפיליפינים, סינגפור, תאילנד ווייטנאם).</p>''')
    page.append(RESTRICTED_BANNER)
    page.append(f'<h2 id="r-foreword">דבר הפתיחה</h2><div class="article-body reveal">{foreword}</div>')
    page.append(f'<h2 id="r-exec-summary">תקציר מנהלים</h2><div class="article-body reveal">{exec_summary}</div>')
    page.append(f'''<div class="callout warning reveal">
      <p class="callout-label">⚠️ הבהרה משפטית (Disclaimer)</p>
      <div class="article-body">{disclaimer}</div>
    </div>''')
    page.append("".join(chapters_html))
    page.append(f'<h2 id="r-about">אודות אינטרפול</h2><div class="article-body reveal">{about_interpol}</div>')
    page.append(f'<h2>תודות</h2><div class="article-body reveal">{ack}</div>')
    if refs_html:
        page.append(f'<h2 id="r-refs">מקורות והערות שוליים</h2><div class="article-body reveal" style="font-size:13.5px;">{refs_html}</div>')
    page.append('</div>')  # doc-main
    page.append('</div>')  # doc-layout
    page.append('</main>')
    page.append(footer_html(rel))
    page.append(scripts_html(rel))
    (ROOT / "research.html").write_text("".join(page), encoding="utf-8")
    print("מחקר Forged Realities: פרקים שנמצאו:", sorted(chapters.keys()))
    return chapters


# ---------------------------------------------------------------------------
# 9א. מבחן מסכם
# ---------------------------------------------------------------------------

def build_final_quiz_page():
    rel = ""
    picked = []
    for n in range(1, 9):
        qs = CHAPTER_EXTRAS.get(n, {}).get("quiz", [])
        take = qs[:2] if n <= 6 else qs[:1]
        for q in take:
            picked.append((n, q))

    cards = []
    for qi, (chn, (question, options, correct_i, explain)) in enumerate(picked):
        opts_html = []
        for oi, opt in enumerate(options):
            is_correct = "true" if oi == correct_i else "false"
            opts_html.append(
                f'<label class="quiz-opt"><input type="radio" name="qfinal-{qi}" '
                f'data-correct="{is_correct}" data-explain="{html.escape(explain)}"> <span>{opt}</span></label>'
            )
        cards.append(f'''<div class="quiz-card">
  <p class="quiz-q"><span class="quiz-chtag">פרק {chn}</span>{qi + 1}. {question}</p>
  <div class="quiz-opts">{''.join(opts_html)}</div>
  <button class="quiz-check" type="button">בדיקת תשובה</button>
  <div class="quiz-feedback"></div>
</div>''')

    quiz_html = f'''<div class="quiz-block final-quiz reveal">
  <div id="final-quiz-previous" class="final-quiz-previous" hidden>
    📌 הציון האחרון שנשמר במכשיר זה: <strong class="prev-pct"></strong> (<span class="prev-date"></span>)
  </div>
  {''.join(cards)}
  <p class="quiz-score"></p>
  <div class="final-quiz-result" hidden>
    <p class="final-quiz-pct"></p>
    <p class="final-quiz-detail"></p>
  </div>
</div>'''

    page = []
    page.append(page_head("מבחן מסכם — מדריך SynthWave", rel))
    page.append(header_html(rel, "final-quiz.html"))
    page.append(f'''<main class="wrap medium">
  <p class="kicker reveal">בדיקת ידע מסכמת</p>
  <h1 class="reveal">מבחן מסכם על כל פרקי המדריך</h1>
  <p class="reveal">מבחר שאלות מייצג מתוך כל שמונת הפרקים. הציון נשמר במכשיר זה בלבד (localStorage בדפדפן), לצורך מעקב אישי אחר ההתקדמות — הוא אינו נשלח לאף שרת.</p>
  {quiz_html}
</main>''')
    page.append(footer_html(rel))
    page.append(scripts_html(rel))
    (ROOT / "final-quiz.html").write_text("".join(page), encoding="utf-8")


# ---------------------------------------------------------------------------
# 9ב. דף סיכום להדפסה
# ---------------------------------------------------------------------------

def build_cheat_sheet_page(chapters):
    rel = ""
    sections = []
    for n in range(1, 9):
        ch = chapters.get(n, {"title": CHAPTER_TITLES_FALLBACK[n]})
        extras = CHAPTER_EXTRAS.get(n, {"takeaways": []})
        items = "".join(f"<li>{t}</li>" for t in extras.get("takeaways", []))
        if not items:
            items = "<li>יתעדכן לאחר השלמת התרגום.</li>"
        sections.append(f'''<section class="cheat-section">
      <h2><span class="cheat-num">{n}</span> {ch["title"]}</h2>
      <ul>{items}</ul>
    </section>''')

    page = []
    page.append(page_head("דף סיכום להדפסה — מדריך SynthWave", rel))
    page.append(header_html(rel, "cheat-sheet.html"))
    page.append(f'''<main class="wrap medium">
  <div class="cheat-toolbar no-print">
    <p class="kicker reveal" style="margin:0;">דף סיכום להדפסה</p>
    <button class="print-btn" type="button" onclick="window.print()">🖨️ הדפסת הדף</button>
  </div>
  <h1 class="reveal">עיקרי המדריך — כל שמונת הפרקים בתמצית</h1>
  <p class="reveal">גיליון תמציתי לשימוש שוטף במעבדה — כל "עיקרי הפרק" משמונת פרקי המדריך, בפורמט קומפקטי המיועד להדפסה ולשמירה בתיק פיזי.</p>
  {''.join(sections)}
</main>''')
    page.append(footer_html(rel))
    page.append(scripts_html(rel))
    (ROOT / "cheat-sheet.html").write_text("".join(page), encoding="utf-8")


# ---------------------------------------------------------------------------
# 10. עמוד הבית
# ---------------------------------------------------------------------------

CHAPTER_ICONS = {
    1: "📘", 2: "🗺️", 3: "🔗", 4: "🔍",
    5: "🤖", 6: "🎓", 7: "⚖️", 8: "✅",
}


def build_index_page(chapters):
    rel = ""
    cards = []
    for n in range(1, 9):
        ch = chapters.get(n, {"title": CHAPTER_TITLES_FALLBACK[n]})
        cards.append(f'''<a class="card reveal" href="chapters/ch{n}.html">
      <span class="card-num">{n:02d}</span>
      <span class="card-icon">{CHAPTER_ICONS.get(n, "📘")}</span>
      <h2>{n}. {ch["title"]}</h2>
    </a>''')
    extra_cards = f'''<a class="card reveal" href="glossary.html">
      <span class="card-icon">📖</span>
      <h2>מילון מונחים</h2>
      <p>כל המונחים המקצועיים מהמדריך, בעברית ובאנגלית, עם חיפוש חי.</p>
    </a>
    <a class="card reveal" href="final-quiz.html">
      <span class="card-icon">📝</span>
      <h2>מבחן מסכם</h2>
      <p>מבחר שאלות מכל הפרקים, עם ציון מסכם באחוזים.</p>
    </a>
    <a class="card reveal" href="cheat-sheet.html">
      <span class="card-icon">🖨️</span>
      <h2>דף סיכום להדפסה</h2>
      <p>עיקרי כל שמונת הפרקים בעמוד אחד קומפקטי, מוכן להדפסה.</p>
    </a>
    <a class="card reveal" href="source.html">
      <span class="card-icon">📄</span>
      <h2>מסמך המקור</h2>
      <p>ה-PDF הרשמי של אינטרפול, לצפייה ואימות מול התרגום.</p>
    </a>'''

    page = f'''{page_head("מדריך SynthWave — הדרכת זיהוי מדיה סינתטית", rel)}{header_html(rel, "index.html")}
<main class="wrap medium">

  {RESTRICTED_BANNER}

  <div class="hero">
    <svg class="hero-deco" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="100" cy="100" r="94" fill="none" stroke="currentColor" stroke-width="1"/>
      <circle cx="100" cy="100" r="70" fill="none" stroke="currentColor" stroke-width="1"/>
      <circle cx="100" cy="100" r="46" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="2 5"/>
      <circle cx="100" cy="100" r="22" fill="none" stroke="currentColor" stroke-width="1.4"/>
    </svg>
    <p class="kicker reveal">INTERPOL Project SynthWave &middot; Global Guideline &ndash; False Facades</p>
    <h1 class="reveal">איתור ואימות מדיה סינתטית עבור גורמי אכיפת חוק</h1>
    <p class="reveal">תרגום ועיבוד הדרכתי מלא לעברית של מדריך ההנחיה הגלובלי של אינטרפול בנושא זיופים עמוקים (Deepfakes) וזיופים רדודים (Shallowfakes) — מפת האיומים, שרשרת המשמורת, שיטות זיהוי פורנזיות, בינה מלאכותית, הכשרה, רגולציה והמלצות. כולל תובנות מרכזיות ומבחני ידע עצמיים בכל פרק.</p>
  </div>

  <div class="stat-tiles reveal">
    <div class="stat-tile danger"><span class="stat-num">1,500%</span><span class="stat-cap">עלייה בכמות הדיפייקים המופצים ברשת, 2023&ndash;2025</span></div>
    <div class="stat-tile warn"><span class="stat-num">~55%</span><span class="stat-cap">דיוק זיהוי אנושי ממוצע של דיפייקים — כמעט ניחוש</span></div>
    <div class="stat-tile"><span class="stat-num">$200M</span><span class="stat-cap">הפסד עולמי מהונאות דיפייק ברבעון הראשון של 2025 בלבד</span></div>
    <div class="stat-tile"><span class="stat-num">$25.6M</span><span class="stat-cap">נגנבו בהונאת שיחת-וידאו דיפייק בהונג קונג</span></div>
  </div>

  <div class="progress-tracker reveal" id="progress-tracker">
    <div class="progress-tracker-head">
      <span class="progress-label">📈 ההתקדמות שלכם בקריאת המדריך</span>
      <span class="progress-count" id="progress-count">0 מתוך 8 פרקים הושלמו</span>
    </div>
    <div class="progress-track"><span class="progress-fill" id="progress-fill" style="width:0%"></span></div>
  </div>

  <h2 class="reveal">פרקי המדריך</h2>
  <div class="cards reveal" style="margin-bottom:40px;">
    {''.join(cards)}
  </div>

  <a class="companion-banner reveal" href="research.html">
    <span class="companion-icon">🌏</span>
    <span class="companion-text">
      <strong>מסמך משלים: Forged Realities</strong>
      <span>מחקר של פרויקט SynthWave על איומי מדיה סינתטית בדרום-מזרח אסיה ותגובת גורמי אכיפת החוק בשטח — תרגום מלא לעברית</span>
    </span>
    <span class="companion-arrow" aria-hidden="true">&larr;</span>
  </a>

  <h2 class="reveal">חומרי עזר נוספים</h2>
  <div class="cards reveal">
    {extra_cards}
  </div>

</main>
{footer_html(rel)}{scripts_html(rel)}'''
    (ROOT / "index.html").write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------------
# 11. אינדקס חיפוש גלובלי (JSON, נצרך ע"י main.js)
# ---------------------------------------------------------------------------

def build_search_index(chapters, glossary_entries_with_ids, research_chapters=None):
    index = []
    for n in range(1, 9):
        ch = chapters.get(n)
        if not ch:
            continue
        index.append({
            "title": f"{n}. {ch['title']}",
            "url": f"chapters/ch{n}.html",
            "chapter": n,
            "type": "chapter",
        })
        for num, title in extract_subsections(ch.get("body", "")):
            index.append({
                "title": f"{num} {title}",
                "url": f"chapters/ch{n}.html#{slug(num)}",
                "chapter": n,
                "type": "section",
            })
    for n, ch in (research_chapters or {}).items():
        index.append({
            "title": f"{n}. {ch['title']}",
            "url": f"research.html#sec-{n}",
            "chapter": n,
            "type": "research",
        })
        for num, title in extract_subsections(ch.get("body", "")):
            index.append({
                "title": f"{num} {title}",
                "url": f"research.html#{slug(num)}",
                "chapter": n,
                "type": "research",
            })
    for he_term, en_term, definition, term_id in glossary_entries_with_ids:
        index.append({
            "title": f"{he_term} ({en_term})",
            "url": f"glossary.html#{term_id}",
            "chapter": None,
            "type": "glossary",
        })
    assets_dir = ROOT / "assets"
    assets_dir.mkdir(exist_ok=True)
    (assets_dir / "search-index.json").write_text(
        json.dumps(index, ensure_ascii=False), encoding="utf-8"
    )
    return index


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    text = SRC.read_text(encoding="utf-8")
    sections = split_top_sections(text)
    front, chapters, glossary_body, refs_body, about_body = classify(sections)

    missing = [n for n in range(1, 9) if n not in chapters]
    if missing:
        print("אזהרה: לא נמצאו הפרקים הבאים בקובץ המקור:", missing)

    glossary_entries_with_ids = build_glossary_page(glossary_body)
    glossary_entries = [(he, en, d) for he, en, d, _id in glossary_entries_with_ids]

    for n in range(1, 9):
        if n in chapters:
            build_chapter_page(n, chapters, glossary_entries)

    build_index_page(chapters)
    build_references_page(refs_body)
    build_about_page(front, about_body)
    build_source_page()
    build_final_quiz_page()
    build_cheat_sheet_page(chapters)
    research_chapters = build_research_page()
    build_search_index(chapters, glossary_entries_with_ids, research_chapters)

    print("הרכבת האתר הושלמה.")
    print("פרקים שנמצאו:", sorted(chapters.keys()))
    print("מילון מונחים:", "נמצא" if glossary_body else "לא נמצא", f"({len(glossary_entries_with_ids)} מונחים)")
    print("הערות שוליים:", "נמצא" if refs_body else "לא נמצא")
    print("אודות אינטרפול:", "נמצא" if about_body else "לא נמצא")
    print("front matter keys:", list(front.keys()))


if __name__ == "__main__":
    main()
