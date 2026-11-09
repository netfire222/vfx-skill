# vfx - סקיל אפקטים לרילס ל-Claude

חמש פקודות שמוסיפות לסרטון מדבר (talking head) אפקטים כמו בריל מקצועי, עם תמיכה מלאה בעברית ובכיוון מימין לשמאל.

| פקודה | מה היא עושה |
|---|---|
| `/vfx strike` | מילה ענקית מעל הראש, קו אדום מוחק אותה ומילה חדשה נכנסת במקומה |
| `/vfx echo` | כותרת גדולה שנכנסת מאחורי הראש עם עותקי מתאר שמתפזרים |
| `/vfx spotlight` | הרקע מחשיך, אור חם על הדובר וכותרת ניאון מהבהבת |
| `/vfx freeze-mark` | עצירת פריים, הבזק, זום ועיגול אדום סביב הפנים |
| `/vfx pinned-comment` | כרטיס תגובה מוצמד שקופץ למעלה |
| `/vfx showcase` | עוטף את התוצאה בממשק Claude עם פקודות מוקלדות, סאונד וקריאה לפעולה |

## התקנה

**ב-Claude (אתר או אפליקציה):** מורידים את [vfx-skill.zip](https://github.com/netfire222/vfx-skill/raw/main/vfx-skill.zip), נכנסים ל-Customize ואז Skills, לוחצים על הפלוס, Create skill ו-Upload a skill, ומעלים את הקובץ.

**ב-Claude Code:**
```bash
mkdir -p ~/.claude/skills
unzip ~/Downloads/vfx-skill.zip -d ~/.claude/skills
brew install ffmpeg node
pip3 install numpy pillow fonttools python-bidi ai-edge-litert "opencv-python-headless<5"
```

המדריך המלא בעברית: https://www.netaneles.com/skill-efektim-reels/

⭐ אם הסקיל עזר לכם, תנו לו כוכב (Star) בראש העמוד. זה עוזר לאנשים נוספים למצוא אותו.

נבנה ע״י נתנאל אסטריכר · ייעוץ, הדרכות והרצאות AI לעסקים
