# -*- coding: utf-8 -*-
"""
جارفيس — مساعد شخصي بيشتغل على اللابتوب.
- وش بيتكلم + صوت (في المتصفح على http://127.0.0.1:5000)
- يفتح برامج ومواقع لما تقوله
- يعرف جدول الجامعة ويفكّرك بالمحاضرات
- يبعت تذكير على الواتساب (عن طريق WhatsApp Web)
"""
import os, re, sys, json, threading, time, datetime, subprocess, webbrowser, base64
import brain

# خلي الطباعة العربية ماتعلّقش في شاشة الويندوز
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, "data.json")
APPS_FILE = os.path.join(BASE, "apps.json")
FACE_FILE = os.path.join(BASE, "face.html")
ICS_FILE  = os.path.join(BASE, "jarvis_calendar.ics")

# آخر يوم في الترم (لتكرار المحاضرات في تقويم الأيفون) — عدّله لو حبيت
TERM_END = datetime.date(2027, 1, 31)

try:
    from flask import Flask, request, jsonify, Response
    app = Flask(__name__)
except Exception:
    app = None  # ماينفعش نشغّل السيرفر من غير flask، بس توليد التقويم بيشتغل

# ------------------------------------------------------------------ بيانات
DAYS = [("sat","السبت"),("sun","الأحد"),("mon","الاتنين"),
        ("tue","الثلاث"),("wed","الأربع"),("thu","الخميس"),("fri","الجمعة")]
DAYLABEL = {k:v for k,v in DAYS}
JSDAY = ["mon","tue","wed","thu","fri","sat","sun"]  # python weekday(): Mon=0..Sun=6

def day_key(d):      return JSDAY[d.weekday()]
def ymd(d):          return d.strftime("%Y-%m-%d")
def now():           return datetime.datetime.now()

_lock = threading.Lock()
_announce = []   # تنبيهات جاهزة عشان الوش ينطقها

def uid():
    import random, string
    return "".join(random.choice(string.ascii_lowercase+string.digits) for _ in range(7))

def default_data():
    routine = {k: [] for k,_ in DAYS}
    def ev(t, title, typ, place): return {"id":uid(),"time":t,"title":title,"type":typ,"place":place,"link":""}
    # Sample timetable — replace with your own from the Week tab (or by talking to JARVIS)
    routine["sun"] = [
        ev("09:00","Sample Lecture","lecture","Hall A"),
        ev("10:45","Sample Lab","lab","Computer Lab"),
    ]
    routine["tue"] = [
        ev("12:30","Sample Meeting","ميتنج","Teams"),
    ]
    return {
        "profile": {"name":"","whatsapp":""},
        "routine": routine,
        "overrides": {},
        "memory": [],
        "settings": {"reminderMin":15,"whatsapp_enabled":False,"api_key":"","model":"","gemini_key":""},
        "done": {},
        "fired": {},
    }

def default_apps():
    return {
        "يوتيوب|youtube|يوتوب": {"url":"https://www.youtube.com"},
        "جوجل|google|البحث": {"url":"https://www.google.com"},
        "تيمز|teams|الميتنج|الاجتماع": {"url":"https://teams.microsoft.com"},
        "واتساب|whatsapp|الواتس": {"url":"https://web.whatsapp.com"},
        "جيميل|gmail|الايميل|الإيميل|الميل": {"url":"https://mail.google.com"},
        "فيسبوك|facebook|الفيس": {"url":"https://www.facebook.com"},
        "تويتر|twitter|اكس": {"url":"https://twitter.com"},
        "انستجرام|instagram|انستا": {"url":"https://www.instagram.com"},
        "شات جي بي تي|chatgpt|جي بي تي": {"url":"https://chat.openai.com"},
        "جوجل كلاسروم|classroom|الكلاسروم": {"url":"https://classroom.google.com"},
        "الدرايف|drive|جوجل درايف": {"url":"https://drive.google.com"},
        "الكروم|chrome|المتصفح|البراوزر": {"cmd":"start chrome"},
        "الكالكوليتر|الحاسبة|calculator|calc": {"cmd":"calc"},
        "المفكرة|نوتباد|notepad": {"cmd":"notepad"},
        "البينت|الرسام|paint": {"cmd":"mspaint"},
        "الاعدادات|الإعدادات|settings": {"cmd":"start ms-settings:"},
        "الملفات|المستكشف|explorer|الفايلات": {"cmd":"explorer"},
        "الوورد|word": {"cmd":"start winword"},
        "الاكسيل|excel": {"cmd":"start excel"},
        "البوربوينت|powerpoint|باوربوينت": {"cmd":"start powerpnt"},
        "الفيجوال|vs code|كود|vscode": {"cmd":"code"},
    }

def load_json(path, default_fn):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if path == DATA_FILE:
            base = default_data()
            for k in base:
                if k not in d: d[k] = base[k]
        return d
    except Exception:
        d = default_fn()
        save_json(path, d)
        return d

def save_json(path, d):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save error:", e)

DATA = load_json(DATA_FILE, default_data)
APPS = load_json(APPS_FILE, default_apps)

def persist(): save_json(DATA_FILE, DATA)

# ------------------------------------------------------------------ أدوات وقت
AR2EN = {"٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9"}
def norm_digits(s): return "".join(AR2EN.get(c,c) for c in s)

def to_min(t):
    if not t: return 9999
    p = t.split(":"); return int(p[0])*60 + int(p[1] if len(p)>1 else 0)

def fmt12(t):
    if not t: return "—"
    h,m = int(t.split(":")[0]), t.split(":")[1]
    ap = "ص" if h < 12 else "م"
    hh = h % 12
    if hh == 0: hh = 12
    return f"{hh}:{m} {ap}"

AR_MONTHS = ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو",
             "أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
def ar_date(d): return f"{d.day} {AR_MONTHS[d.month-1]}"

def items_for(d):
    key = day_key(d); ds = ymd(d)
    ov = DATA["overrides"].get(ds, {})
    removed = ov.get("removeIds", [])
    base = [dict(it, src="routine") for it in DATA["routine"].get(key, []) if it["id"] not in removed]
    extra = [dict(it, src="override") for it in ov.get("add", [])]
    allv = base + extra
    allv.sort(key=lambda x: to_min(x.get("time","")))
    return allv

# ------------------------------------------------------------------ تنفيذ أوامر النظام
def do_open(target):
    try:
        if target.get("url"):
            webbrowser.open(target["url"]); return True
        if target.get("cmd"):
            subprocess.Popen(target["cmd"], shell=True); return True
    except Exception as e:
        print("open error:", e)
    return False

def find_app(text):
    for keys, tgt in APPS.items():
        for k in keys.split("|"):
            if k and k in text:
                return tgt, k
    return None, None

import glob
def find_start_menu_app(query):
    """يدوّر على اختصار برنامج (.lnk) في الستارت مينيو بالاسم."""
    q = (query or "").lower().strip()
    if not q: return None
    # كلمات مش برنامج
    q = re.sub(r"\b(the|app|application|program|please|برنامج|تطبيق|بتاع|اللي|على اللابتوب)\b","",q).strip()
    if not q: return None
    dirs = [
        os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    exact=None; best=None; best_len=999
    for d in dirs:
        if not d or not os.path.isdir(d): continue
        for lnk in glob.glob(os.path.join(d, "**", "*.lnk"), recursive=True):
            name = os.path.splitext(os.path.basename(lnk))[0]
            nl = name.lower()
            if nl == q: exact = lnk
            elif q in nl or nl in q:
                if len(nl) < best_len: best, best_len = lnk, len(nl)
    return exact or best

_startapps_cache = None
def _get_start_apps():
    """كل التطبيقات اللي في قايمة ابدأ (عادية + Store) بالاسم و AppID."""
    global _startapps_cache
    if _startapps_cache is not None: return _startapps_cache
    try:
        out = subprocess.check_output(
            ["powershell","-NoProfile","-Command","Get-StartApps | ConvertTo-Json -Compress"],
            timeout=20, text=True, encoding="utf-8", errors="ignore")
        data = json.loads(out)
        if isinstance(data, dict): data = [data]
        _startapps_cache = [a for a in data if a.get("Name") and a.get("AppID")]
    except Exception as e:
        print("Get-StartApps error:", e); _startapps_cache = []
    return _startapps_cache

def find_start_app(query):
    q = (query or "").lower().strip()
    if not q: return None
    exact=None; best=None; bl=999
    for a in _get_start_apps():
        name = a["Name"].lower()
        if name == q: exact = a
        elif q in name or name in q:
            if len(name) < bl: best, bl = a, len(name)
    return exact or best

def open_program(query):
    """قايمة جارفيس -> كل برامج قايمة ابدأ -> اختصارات .lnk -> بحث جوجل."""
    # مانفتحش كاميرا الويندوز — كاميرا جارفيس بتتفتح من الواجهة
    if re.search(r"\b(camera|webcam)\b|الكاميرا|كاميرا|كاميره", (query or ""), re.I):
        return "Just say 'open the camera' and I'll switch on my own camera to see what you're holding."
    q = re.sub(r"\b(the|app|application|program|please|برنامج|تطبيق|بتاع|اللي|على اللابتوب|ليا|لي)\b"," ",(query or "")).strip()
    tgt, k = find_app(q or query)
    if tgt and do_open(tgt): return "Opened " + k
    # كل تطبيقات قايمة ابدأ
    a = find_start_app(q)
    if a:
        try:
            subprocess.Popen('explorer.exe "shell:appsFolder\\%s"' % a["AppID"], shell=True)
            return "Opened " + a["Name"]
        except Exception as e:
            print("launch uwp error:", e)
    # اختصارات كلاسيكية
    lnk = find_start_menu_app(q)
    if lnk:
        try:
            os.startfile(lnk)
            return "Opened " + os.path.splitext(os.path.basename(lnk))[0]
        except Exception as e:
            print("startfile error:", e)
    webbrowser.open("https://www.google.com/search?q=" + (query or q))
    return "I couldn't find that app installed, so I searched the web for it."

# ------------------------------------------------------------------ parser
DAYWORDS = [
    ("sat", ["السبت","سبت"]),
    ("sun", ["الاحد","الأحد","احد","الحد"]),
    ("mon", ["الاتنين","الإثنين","الاثنين","اتنين"]),
    ("tue", ["الثلاث","الثلاثاء","التلات","تلات","ثلاث"]),
    ("wed", ["الاربع","الأربعاء","الاربعاء","اربع"]),
    ("thu", ["الخميس","خميس"]),
    ("fri", ["الجمعة","الجمعه","جمعة"]),
]
PERIODS = {  # فترات الجامعة بالساعة
    "الاولى":"09:00","الأولى":"09:00","الفترة الاولى":"09:00","اولى":"09:00",
    "التانية":"10:45","الثانية":"10:45","تانية":"10:45",
    "التالتة":"12:30","الثالثة":"12:30","تالتة":"12:30",
    "الرابعة":"14:15","الرابعه":"14:15","رابعة":"14:15",
}

def parse_time(t):
    m = re.search(r"(?:الساعة\s*)?(\d{1,2})(?::(\d{2}))?\s*(ص|صباحا|صباحاً|م|مساء|مساءً|pm|am)?", t)
    if not m: return ""
    h = int(m.group(1)); mm = m.group(2) or "00"; ap = (m.group(3) or "").lower()
    if any(x in ap for x in ["م","مساء","pm"]) and h < 12: h += 12
    if any(x in ap for x in ["ص","صباح","am"]) and h == 12: h = 0
    if 0 <= h <= 23: return f"{h:02d}:{mm}"
    return ""

def detect_day(t):
    for key, words in DAYWORDS:
        for w in words:
            if re.search(r"(^|\s)"+re.escape(w)+r"(\s|$)", t):
                return key
    return None

def classify_type(t):
    if re.search(r"ميتنج|اجتماع|meeting|مقابلة|كول|call", t): return "ميتنج"
    if re.search(r"كويز|امتحان|quiz|exam|اختبار|مهمة|تاسك|task|واجب|اسايمنت|assignment|سلّم|سلم|اذاكر|مذاكرة", t): return "مهمة"
    if re.search(r"سكشن|section", t): return "سكشن"
    if re.search(r"معمل|لاب|lab", t): return "lab"
    if re.search(r"محاضرة|lecture|لكتشر", t): return "lecture"
    return "مهمة"

# ------------------------------------------------------------------ عقل AI
CONV = []   # تاريخ المحادثة (نص بس)
ASSIGNMENT = ""  # نص الأساينمنت اللي اترفع

def build_context():
    d = now()
    mem = DATA.get("memory", [])
    lines = [f"اسم المستخدم: {DATA['profile'].get('name','')}",
             f"النهاردة: {DAYLABEL[day_key(d)]} {ar_date(d)}، الساعة {fmt12(d.strftime('%H:%M'))}"]
    if mem:
        lines.append("حاجات فاكرها عن المستخدم:")
        for m in mem[-20:]: lines.append(" - "+m["text"])
    items = items_for(d)
    if items:
        lines.append("جدول النهاردة:")
        for it in items: lines.append(f" - {fmt12(it['time'])} {it['title']}"+(f" ({it['place']})" if it.get('place') else ""))
    # ملخص الأسبوع
    lines.append("الجدول الأسبوعي الثابت:")
    for k,label in DAYS:
        lst = DATA["routine"].get(k,[])
        if lst:
            lines.append(f" {label}: " + "، ".join(f"{fmt12(x['time'])} {x['title']}" for x in sorted(lst,key=lambda z:to_min(z.get('time','')))))
    if ASSIGNMENT:
        lines.append("\nThe user uploaded this assignment. When they ask you to solve/code it, write code that solves exactly this:\n" + ASSIGNMENT[:4000])
    return "\n".join(lines)

def add_event_struct(title, day, tm="", typ="lecture", important=False, recurring=False):
    item = {"id":uid(),"time":tm or "","title":title or "حاجة","type":typ,"place":"","link":"","important":bool(important)}
    day = (day or "").lower().strip()
    ar2en = {"السبت":"sat","الاحد":"sun","الأحد":"sun","الاتنين":"mon","الاثنين":"mon",
             "الثلاث":"tue","الثلاثاء":"tue","الاربع":"wed","الأربعاء":"wed","الخميس":"thu","الجمعة":"fri",
             "النهاردة":"today","بكرة":"tomorrow"}
    day = ar2en.get(day, day)
    if day in ("today","tomorrow"):
        dd = now()+datetime.timedelta(days=1 if day=="tomorrow" else 0)
        ov = DATA["overrides"].setdefault(ymd(dd), {"add":[],"removeIds":[]}); ov["add"].append(item)
        persist(); build_ics(); return f"اتسجّلت «{title}» يوم {DAYLABEL[day_key(dd)]}"
    if day in DAYLABEL:
        if important and not recurring:
            dd = next_weekday(day); ov = DATA["overrides"].setdefault(ymd(dd), {"add":[],"removeIds":[]}); ov["add"].append(item)
            persist(); build_ics(); return f"اتسجّلت «{title}» يوم {DAYLABEL[day]} الجاي، وهفكّرك قبلها بيوم"
        DATA["routine"][day].append(item); persist(); build_ics()
        return f"اتسجّلت «{title}» كل {DAYLABEL[day]}"
    # مفيش يوم واضح → النهاردة
    ov = DATA["overrides"].setdefault(ymd(now()), {"add":[],"removeIds":[]}); ov["add"].append(item)
    persist(); build_ics(); return f"اتسجّلت «{title}» النهاردة"

def _h_remember(a):
    DATA["memory"].append({"id":uid(),"text":a.get("fact","").strip(),"when":ar_date(now())}); persist()
    return "اتحفظت"
def close_program(query):
    q = re.sub(r"\b(the|app|application|program|برنامج|تطبيق|بتاع|اللي|ليا|لي)\b"," ",(query or "")).strip()
    if not q: return "Which program should I close?"
    qq = q.replace("'", "''")
    ps = ("$q='%s'; $p=Get-Process | ?{ ($_.MainWindowTitle -and $_.MainWindowTitle -like \"*$q*\") "
          "-or ($_.ProcessName -like \"*$q*\") }; if($p){ $n=($p|Select-Object -Expand ProcessName -Unique) -join ', '; "
          "$p | Stop-Process -Force -ErrorAction SilentlyContinue; \"CLOSED:$n\" } else { 'NONE' }") % qq
    try:
        out = subprocess.check_output(["powershell","-NoProfile","-Command",ps],
                                      timeout=15, text=True, encoding="utf-8", errors="ignore").strip()
        if out.startswith("CLOSED:"):
            return "Closed " + out[len("CLOSED:"):].strip()
        return "I don't see that program running."
    except Exception as e:
        print("close error:", e); return "I couldn't close it."

import shutil
WORKSPACE = os.path.join(os.path.expanduser("~"), "Documents", "JarvisProjects")
LAST_FILE = None

def create_code_file(filename, content):
    global LAST_FILE
    safe = re.sub(r'[<>:"/\\|?*]', "_", (filename or "file.txt")).strip() or "file.txt"
    try:
        os.makedirs(WORKSPACE, exist_ok=True)
        path = os.path.join(WORKSPACE, safe)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content or "")
        LAST_FILE = path
    except Exception as e:
        print("write file error:", e); return "I couldn't create the file."
    # افتحه في VS Code، وإلا المحرر الافتراضي
    try:
        if shutil.which("code"):
            subprocess.Popen('code "%s"' % path, shell=True)
            return "Created %s and opened it in VS Code." % safe
        os.startfile(path)
        return "Created %s and opened it. (Install VS Code's 'code' command to open it there.)" % safe
    except Exception as e:
        print("open file error:", e)
        return "Created %s in your Documents\\JarvisProjects folder." % safe

_PROC_NAMES = {"chrome":"Chrome","msedge":"Edge","firefox":"Firefox","code":"VS Code",
    "idea64":"IntelliJ","studio64":"Android Studio","devenv":"Visual Studio","spotify":"Spotify",
    "discord":"Discord","whatsapp":"WhatsApp","steam":"Steam","explorer":"File Explorer",
    "winword":"Word","excel":"Excel","powerpnt":"PowerPoint","notepad":"Notepad","calculatorapp":"Calculator",
    "arduino ide":"Arduino IDE","vlc":"VLC","obs64":"OBS","telegram":"Telegram"}
def list_open_apps():
    ps = ("Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
          "Select-Object -Expand ProcessName -Unique")
    try:
        out = subprocess.check_output(["powershell","-NoProfile","-Command",ps],
                                      timeout=15, text=True, encoding="utf-8", errors="ignore")
        NOISE = ("webview","textinputhost","applicationframehost","systemsettings","overlay",
                 "runtimebroker","shellexperience","searchhost","startmenu","lockapp","nvidia",
                 "python","conhost","windowsterminal","widgets","searchapp","gamebar","crosshair")
        names, seen = [], set()
        for n in out.splitlines():
            n = n.strip()
            if not n: continue
            base = n.lower().split(".")[0]
            if any(x in n.lower() for x in NOISE): continue
            friendly = _PROC_NAMES.get(n.lower()) or _PROC_NAMES.get(base) or n.split(".")[0]
            if friendly.lower() not in seen:
                seen.add(friendly.lower()); names.append(friendly)
        if not names: return "Nothing with a window is open right now."
        return "Open apps: " + ", ".join(names) + "."
    except Exception as e:
        print("list apps error:", e); return "I couldn't check the open apps."

def _h_open(a):
    return open_program(a.get("query",""))
def _h_close(a):
    return close_program(a.get("query",""))
def _h_list(a):
    return list_open_apps()
def _h_create(a):
    return create_code_file(a.get("filename",""), a.get("content",""))

def run_code_file(filename=""):
    path = None
    if filename:
        safe = re.sub(r'[<>:"/\\|?*]', "_", filename).strip()
        p = os.path.join(WORKSPACE, safe)
        if os.path.exists(p): path = p
    if not path: path = LAST_FILE
    if not path or not os.path.exists(path):
        return "I don't have a file to run yet. Ask me to create one first."
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py": cmd = ["py", path]
    elif ext == ".js": cmd = ["node", path]
    else: return "I can run Python or JavaScript files directly. For this one, open it in its editor."
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25, cwd=WORKSPACE,
                           encoding="utf-8", errors="ignore")
        out = ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()
        name = os.path.basename(path)
        if not out: return f"Ran {name} with no output."
        return f"Ran {name}. Output:\n{out[:800]}"
    except subprocess.TimeoutExpired:
        return "It was taking too long, so I stopped it."
    except Exception as e:
        print("run error:", e); return "I couldn't run it: " + str(e)[:80]
def _h_run(a):
    return run_code_file(a.get("filename",""))
def _h_add(a):
    return add_event_struct(a.get("title",""), a.get("day",""), a.get("time",""),
                            a.get("type","lecture"), a.get("important",False), a.get("recurring",False))
def _h_getsched(a):
    day = (a.get("day","today") or "today").lower().strip()
    en2 = {"saturday":"sat","sunday":"sun","monday":"mon","tuesday":"tue","wednesday":"wed","thursday":"thu","friday":"fri"}
    day = en2.get(day, day)
    if day == "today": d = now()
    elif day == "tomorrow": d = now()+datetime.timedelta(days=1)
    elif day in DAYLABEL:
        d = now()
        for i in range(7):
            c = now()+datetime.timedelta(days=i)
            if day_key(c)==day: d=c; break
    else: d = now()
    items = items_for(d)
    if not items: return "nothing scheduled"
    return ", ".join(f"{fmt12(it['time'])} {it['title']}" for it in items)

AI_HANDLERS = {"remember":_h_remember,"open_app":_h_open,"close_app":_h_close,"list_open_apps":_h_list,"create_code_file":_h_create,"run_code_file":_h_run,"add_to_schedule":_h_add,"get_schedule":_h_getsched}

def ai_reply(raw):
    s = DATA["settings"]
    key = s.get("api_key","")
    model = s.get("model","") or "openai/gpt-oss-120b"
    reply, changed = brain.respond("groq", raw, key, model,
                                   build_context(), CONV[-8:], AI_HANDLERS)
    CONV.append({"role":"user","content":raw})
    CONV.append({"role":"assistant","content":reply})
    if len(CONV) > 16: del CONV[:len(CONV)-16]
    return {"reply":reply,"speak":True,"refresh":changed}

def handle_command(raw, source="text"):
    t = norm_digits(raw.strip())
    low = t.lower()

    if not t:
        return {"reply":"اتكلم يا باشا، أنا سامعك.","speak":True}

    # لو فيه مفتاح API → استخدم العقل الذكي
    if DATA["settings"].get("api_key"):
        return ai_reply(raw)

    # ---- تحية / أسئلة بسيطة
    if re.search(r"^(ازيك|إزيك|عامل ايه|صباح|مساء|هاي|hi|hello|اهلا|أهلا|سلام)", low):
        nm = DATA["profile"].get("name","")
        return {"reply": f"أهلاً {nm}! أنا جارفيس، تحت أمرك. عايز أفتحلك حاجة ولا أقولك جدولك؟","speak":True}

    if re.search(r"الساعة كام|كام الساعة|الوقت", t):
        return {"reply": f"الساعة دلوقتي {fmt12(now().strftime('%H:%M'))}.","speak":True}

    if re.search(r"(انت مين|إنت مين|مين انت|اسمك ايه)", t):
        return {"reply":"أنا جارفيس، مساعدك الشخصي. بفتحلك البرامج والمواقع، وبفكّرك بمحاضراتك وكل اللي عليك.","speak":True}

    # ---- قفل برنامج
    cm = re.match(r"^(اقفل|اقفلي|قفل|سكر|اغلق|close|quit|exit|kill)\s+(.+)", t, re.I)
    if cm:
        return {"reply": close_program(cm.group(2)), "speak":True}

    # ---- فتح برامج/مواقع
    if re.search(r"^(افتح|افتحلي|شغل|شغّل|ادخل|روح|هات)\b", t) or "افتح" in low:
        # لينك محاضرة/كورس معين؟
        link = find_course_link(t)
        if link:
            webbrowser.open(link["link"])
            return {"reply": f"فتحتلك {link['title']} ✓","speak":True,"refresh":False}
        term = re.sub(r"^(افتح|افتحلي|شغل|شغّل|ادخل|روح|هات)\s*","",t).strip() or t
        return {"reply": open_program(term), "speak":True}

    # ---- استعلام الجدول
    if re.search(r"(عندي ايه|عليا ايه|جدولي|مواعيدي|محاضراتي|ايه النهاردة|ايه بكرة|ايه يوم)", t):
        return schedule_query(t)

    # ---- ذاكرة
    mem = re.match(r"^(افتكر|افكر|خليك فاكر|اعرف اني|معلومة|ذاكرتي)\s*:?\s*(.+)", t)
    if mem:
        DATA["memory"].append({"id":uid(),"text":mem.group(2).strip(),"when":ar_date(now())})
        persist()
        return {"reply":"تمام، حفظتها عندي 🧠","speak":True,"refresh":True}

    # ---- إضافة / تعديل في الجدول  (خد بالك / ضيف / عندي)
    if re.search(r"(خد بالك|خلي بالك|ضيف|سجل|سجّل|عندي|عليا|اكتب عندك|افتكرلي)", t):
        return add_event_from_text(t)

    # افتراضي: لو فيه يوم أو وقت اعتبره إضافة، غير كده رد عام
    if detect_day(t) or parse_time(t) or any(p in t for p in PERIODS):
        return add_event_from_text(t)

    return {"reply":"مش متأكد قصدك إيه. تقدر تقول مثلاً: «افتح تيمز» أو «عندي إيه بكرة» أو «خد بالك الأحد الفترة الأولى كويز نتورك».","speak":True}

def find_course_link(t):
    # لو فيه كود كورس أو كلمة ليها لينك محفوظ النهاردة/الأسبوع
    for d_off in range(0,7):
        d = now()+datetime.timedelta(days=d_off)
        for it in items_for(d):
            if it.get("link"):
                code = re.sub(r"\s+","",it["title"].split("—")[0]).lower()
                if code and code in re.sub(r"\s+","",t.lower()):
                    return it
    return None

def schedule_query(t):
    key = detect_day(t)
    if re.search(r"بكرة|بكره|غدا", t):
        d = now()+datetime.timedelta(days=1)
    elif key:
        d = now()
        # أقرب يوم بالاسم ده
        for i in range(7):
            cand = now()+datetime.timedelta(days=i)
            if day_key(cand)==key: d=cand; break
    else:
        d = now()
    items = items_for(d)
    label = DAYLABEL[day_key(d)]
    if not items:
        return {"reply": f"يوم {label} مفيش عندك حاجة. 🎉","speak":True}
    lines = [f"{label} عندك {len(items)}:"]
    spoken = [f"يوم {label} عندك {len(items)} حاجة."]
    for it in items:
        lines.append(f"• {fmt12(it['time'])} — {it['title']}" + (f" ({it['place']})" if it.get('place') else ""))
        spoken.append(f"{fmt12(it['time'])} {it['title']}.")
    return {"reply":"\n".join(lines),"speak":True,"speakText":" ".join(spoken)}

def add_event_from_text(t):
    time_s = ""
    for p,v in PERIODS.items():
        if p in t: time_s = v; break
    if not time_s: time_s = parse_time(t)
    typ = classify_type(t)
    key = detect_day(t)
    scope_today = bool(re.search(r"النهاردة|النهارده|انهاردة", t))
    scope_tom = bool(re.search(r"بكرة|بكره|غدا", t))

    # لينك
    link = ""
    lm = re.search(r"https?://\S+", t)
    if lm: link = lm.group(0)

    # عنوان: نظّف الكلمات الدالة
    title = t
    for junk in [r"https?://\S+", r"خد بالك", r"خلي بالك", r"ضيف", r"سجّل", r"سجل",
                 r"عندي", r"عليا", r"اكتب عندك", r"افتكرلي", r"الفترة", r"فترة",
                 r"النهاردة", r"النهارده", r"بكرة", r"بكره", r"الساعة", r"\bكل\b"]:
        title = re.sub(junk, " ", title)
    for key2, words in DAYWORDS:
        for w in words: title = re.sub(r"(^|\s)"+re.escape(w)+r"(\s|$)"," ", title)
    for p in PERIODS: title = title.replace(p," ")
    title = re.sub(r"\b\d{1,2}(?::\d{2})?\s*(?:ص|م|am|pm)?\b"," ", title)
    title = re.sub(r"\s{2,}"," ", title).strip(" ،,-")
    if not title:
        title = {"lab":"معمل","lecture":"محاضرة","ميتنج":"ميتنج","مهمة":"مهمة","سكشن":"سكشن"}.get(typ,"حاجة")

    important = bool(re.search(r"كويز|امتحان|quiz|exam|اختبار|مهم|تسليم|deadline", t, re.I)) or typ=="مهمة"
    item = {"id":uid(),"time":time_s,"title":title,"type":typ,"place":"","link":link,"important":important}

    if scope_today or scope_tom:
        d = now()+datetime.timedelta(days=1 if scope_tom else 0)
        ds = ymd(d)
        ov = DATA["overrides"].setdefault(ds, {"add":[],"removeIds":[]})
        ov["add"].append(item); persist()
        return {"reply": f"تمام، سجّلت «{title}» يوم {DAYLABEL[day_key(d)]}"+(f" الساعة {fmt12(time_s)}" if time_s else "")+". هفكّرك بيها ✓","speak":True,"refresh":True}
    if key:
        recurring = bool(re.search(r"كل\s", t))  # "كل أحد" = متكرر كل أسبوع
        if important and not recurring:
            # كويز/امتحان/حاجة مهمة = مرة واحدة يوم اليوم الجاي
            d = next_weekday(key); ds = ymd(d)
            ov = DATA["overrides"].setdefault(ds, {"add":[],"removeIds":[]})
            ov["add"].append(item); persist()
            return {"reply": f"تمام، سجّلت «{title}» يوم {DAYLABEL[key]} الجاي ({ar_date(d)})"+(f" الساعة {fmt12(time_s)}" if time_s else "")+". وهفكّرك قبلها بيوم ⏰","speak":True,"refresh":True}
        DATA["routine"][key].append(item); persist()
        return {"reply": f"سجّلت «{title}» كل يوم {DAYLABEL[key]}"+(f" الساعة {fmt12(time_s)}" if time_s else "")+" ✓","speak":True,"refresh":True}
    # من غير يوم → النهاردة
    ds = ymd(now())
    ov = DATA["overrides"].setdefault(ds, {"add":[],"removeIds":[]})
    ov["add"].append(item); persist()
    return {"reply": f"سجّلت «{title}» النهاردة ✓ (لو عايزها ثابتة قول اليوم: مثلاً «كل أحد»)","speak":True,"refresh":True}

# ------------------------------------------------------------------ واتساب
def send_whatsapp(number, msg):
    number = number.strip().replace(" ","")
    if not number.startswith("+"):
        number = "+2"+number if number.startswith("01") else "+"+number
    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(number, msg, wait_time=15, tab_close=True, close_time=3)
        return True
    except Exception as e:
        print("whatsapp error:", e)
        return False

# ------------------------------------------------------------------ scheduler
def reminder_loop():
    while True:
        try:
            s = DATA["settings"]; rem = int(s.get("reminderMin",15))
            d = now(); ds = ymd(d); nmin = d.hour*60+d.minute
            for it in items_for(d):
                if not it.get("time"): continue
                diff = to_min(it["time"]) - nmin
                fkey = ds+"|"+it["id"]
                if 0 <= diff <= rem and not DATA["fired"].get(fkey) and not DATA["done"].get(fkey):
                    DATA["fired"][fkey] = True; persist()
                    text = f"⏰ فاكرك: {it['title']} " + ("دلوقتي" if diff<=1 else f"خلال {diff} دقيقة") + (f" — {it['place']}" if it.get('place') else "")
                    with _lock:
                        _announce.append(text)
                    if s.get("whatsapp_enabled") and DATA["profile"].get("whatsapp"):
                        msg = f"جارفيس ⏰\n{it['title']}\nالساعة {fmt12(it['time'])}" + (f"\n{it['place']}" if it.get('place') else "")
                        threading.Thread(target=send_whatsapp, args=(DATA['profile']['whatsapp'], msg), daemon=True).start()
        except Exception as e:
            print("loop error:", e)
        time.sleep(30)

# ------------------------------------------------------------------ تقويم الأيفون (ICS)
def is_important(it):
    if it.get("important"): return True
    return it.get("type") == "مهمة" or bool(re.search(r"كويز|امتحان|quiz|exam|اختبار|تسليم|deadline", it.get("title",""), re.I))

def _ics_dt(d, t):
    h, m = (t.split(":")+["00"])[:2]
    return f"{d.strftime('%Y%m%d')}T{int(h):02d}{int(m):02d}00"

def _alarm(trigger, desc):
    return ("BEGIN:VALARM\r\nACTION:DISPLAY\r\n"
            f"DESCRIPTION:{desc}\r\nTRIGGER:{trigger}\r\nEND:VALARM\r\n")

WEEKDAY_RRULE = {"mon":"MO","tue":"TU","wed":"WE","thu":"TH","fri":"FR","sat":"SA","sun":"SU"}

def next_weekday(key):
    target = ["mon","tue","wed","thu","fri","sat","sun"].index(key)
    today = datetime.date.today()
    delta = (target - today.weekday()) % 7
    return today + datetime.timedelta(days=delta)

def build_ics():
    L = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Jarvis//AR//","CALSCALE:GREGORIAN",
         "METHOD:PUBLISH","X-WR-CALNAME:جارفيس — جدولي","X-WR-TIMEZONE:Africa/Cairo"]
    lines = "\r\n".join(L) + "\r\n"
    out = [lines]
    rem = int(DATA["settings"].get("reminderMin", 15))
    # المحاضرات المتكررة
    for key in ["sat","sun","mon","tue","wed","thu","fri"]:
        for it in DATA["routine"].get(key, []):
            if not it.get("time"): continue
            start = next_weekday(key)
            dur_end = (datetime.datetime.combine(start, datetime.time()) +
                       datetime.timedelta(minutes=to_min(it["time"])+90))
            ev = ["BEGIN:VEVENT", f"UID:{it['id']}@jarvis",
                  f"DTSTART;TZID=Africa/Cairo:{_ics_dt(start, it['time'])}",
                  f"DTEND;TZID=Africa/Cairo:{dur_end.strftime('%Y%m%dT%H%M%S')}",
                  f"RRULE:FREQ=WEEKLY;BYDAY={WEEKDAY_RRULE[key]};UNTIL={TERM_END.strftime('%Y%m%d')}T235900",
                  f"SUMMARY:{it['title']}" + (f" — {it['place']}" if it.get('place') else ""),
                  f"LOCATION:{it.get('place','')}"]
            ev_s = "\r\n".join(ev) + "\r\n"
            ev_s += _alarm(f"-PT{rem}M", "فاكرك المحاضرة قربت")
            if is_important(it):
                ev_s += _alarm("-P1D", "بكرة عندك حاجة مهمة!")
            ev_s += "END:VEVENT\r\n"
            out.append(ev_s)
    # الحاجات المحددة بتاريخ (overrides: كويزات/مواعيد)
    for ds, ov in DATA["overrides"].items():
        try: d = datetime.datetime.strptime(ds, "%Y-%m-%d").date()
        except Exception: continue
        for it in ov.get("add", []):
            if not it.get("time"): continue
            end = (datetime.datetime.combine(d, datetime.time()) +
                   datetime.timedelta(minutes=to_min(it["time"])+60))
            ev = ["BEGIN:VEVENT", f"UID:{it['id']}@jarvis",
                  f"DTSTART;TZID=Africa/Cairo:{_ics_dt(d, it['time'])}",
                  f"DTEND;TZID=Africa/Cairo:{end.strftime('%Y%m%dT%H%M%S')}",
                  f"SUMMARY:{it['title']}" + (f" — {it['place']}" if it.get('place') else ""),
                  f"LOCATION:{it.get('place','')}"]
            ev_s = "\r\n".join(ev) + "\r\n"
            ev_s += _alarm(f"-PT{rem}M", "فاكرك")
            if is_important(it):
                ev_s += _alarm("-P1D", "بكرة عندك حاجة مهمة!")
                ev_s += _alarm("-PT60M", "بعد ساعة عندك حاجة مهمة!")
            ev_s += "END:VEVENT\r\n"
            out.append(ev_s)
    out.append("END:VCALENDAR\r\n")
    data = "".join(out)
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write(data)
    return data

# ------------------------------------------------------------------ routes
def route(*a, **k):
    if app is None:
        return lambda f: f
    return app.route(*a, **k)

@route("/")
def index():
    with open(FACE_FILE, "r", encoding="utf-8") as f:
        resp = Response(f.read(), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

@route("/api/state")
def api_state():
    d = now()
    today = [dict(it, done=DATA["done"].get(ymd(d)+"|"+it["id"],False)) for it in items_for(d)]
    week = {}
    for k,_ in DAYS:
        week[k] = sorted(DATA["routine"].get(k,[]), key=lambda x:to_min(x.get("time","")))
    s = dict(DATA["settings"])
    s["brain_on"] = bool(s.get("api_key"))
    s["gemini_on"] = bool(s.get("gemini_key"))
    s["api_key"] = ""  # ماننزّلش المفاتيح للواجهة
    s["gemini_key"] = ""
    return jsonify({
        "profile": DATA["profile"], "settings": s,
        "today": today, "todayLabel": DAYLABEL[day_key(d)], "todayDate": ar_date(d),
        "week": week, "days": DAYS, "memory": DATA["memory"],
    })

@route("/api/command", methods=["POST"])
def api_command():
    body = request.get_json(force=True)
    res = handle_command(body.get("text",""), body.get("source","text"))
    if res.get("refresh"):
        try: build_ics()
        except Exception as e: print("ics rebuild:", e)
    return jsonify(res)

@route("/api/vision", methods=["POST"])
def api_vision():
    b = request.get_json(force=True)
    img = b.get("image","")
    if "," in img: img = img.split(",",1)[1]   # شيل data:image/...;base64,
    q = b.get("question","")
    key = DATA["settings"].get("gemini_key","")
    if not key:
        return jsonify({"reply":"Add a Google Gemini key in Settings to enable the camera.","speak":True})
    if not img:
        return jsonify({"reply":"I didn't get an image from the camera.","speak":True})
    reply = brain.vision(img, q, key, build_context())
    # خليه في سياق المحادثة عشان العصف الذهني بعد كده
    CONV.append({"role":"user","content":(q or "what do you see?")+" [showed a photo]"})
    CONV.append({"role":"assistant","content":reply})
    if len(CONV) > 16: del CONV[:len(CONV)-16]
    return jsonify({"reply":reply,"speak":True})

@route("/api/assignment", methods=["POST"])
def api_assignment():
    global ASSIGNMENT
    b = request.get_json(force=True)
    name = b.get("filename","file"); data = b.get("data","")
    if "," in data: data = data.split(",",1)[1]
    ext = os.path.splitext(name)[1].lower()
    key = DATA["settings"].get("gemini_key","")
    text = ""
    TRANSCRIBE = ("Transcribe this assignment/problem sheet fully and accurately: every question, "
                  "all requirements, inputs/outputs, and constraints. Output only the assignment text.")
    try:
        if ext in (".txt",".md",".csv",".py",".java",".c",".cpp",".js",".json"):
            text = base64.b64decode(data).decode("utf-8","ignore")
        elif ext == ".pdf":
            if not key: return jsonify({"reply":"Add a Gemini key in Settings to read PDFs.","speak":True})
            text = brain.vision(data, TRANSCRIBE, key, mime_type="application/pdf", system="You transcribe documents.", max_tokens=1500)
        elif ext in (".png",".jpg",".jpeg",".webp",".gif",".bmp"):
            if not key: return jsonify({"reply":"Add a Gemini key in Settings to read images.","speak":True})
            mime = "image/png" if ext==".png" else ("image/webp" if ext==".webp" else "image/jpeg")
            text = brain.vision(data, TRANSCRIBE, key, mime_type=mime, system="You transcribe documents.", max_tokens=1500)
        else:
            return jsonify({"reply":"I can read images, PDFs, or text files for assignments.","speak":True})
    except Exception as e:
        print("assignment error:", e); return jsonify({"reply":"I couldn't read that file.","speak":True})
    ASSIGNMENT = (text or "").strip()
    if not ASSIGNMENT:
        return jsonify({"reply":"I couldn't read anything from that file.","speak":True})
    CONV.append({"role":"user","content":"[uploaded assignment: "+name+"]"})
    CONV.append({"role":"assistant","content":"I've read the assignment."})
    return jsonify({"reply":"Got it — I've read your assignment. Say the word and I'll write the code to solve it.","speak":True})

@route("/api/poll")
def api_poll():
    with _lock:
        out = list(_announce); _announce.clear()
    return jsonify({"announce": out})

@route("/api/event", methods=["POST"])
def api_event():
    b = request.get_json(force=True)
    item = {"id": b.get("id") or uid(), "time": b.get("time",""), "title": b.get("title","").strip() or "حاجة",
            "type": b.get("type","lecture"), "place": b.get("place","").strip(), "link": b.get("link","").strip()}
    scope = b.get("scope")  # dayKey OR a date string
    if scope in DATA["routine"]:
        arr = DATA["routine"][scope]
        idx = next((i for i,x in enumerate(arr) if x["id"]==item["id"]), -1)
        if idx>=0: arr[idx]=item
        else: arr.append(item)
    else:
        ov = DATA["overrides"].setdefault(scope, {"add":[],"removeIds":[]})
        idx = next((i for i,x in enumerate(ov["add"]) if x["id"]==item["id"]), -1)
        if idx>=0: ov["add"][idx]=item
        else: ov["add"].append(item)
    persist(); build_ics(); return jsonify({"ok":True})

@route("/api/delete", methods=["POST"])
def api_delete():
    b = request.get_json(force=True); scope=b.get("scope"); iid=b.get("id")
    if scope in DATA["routine"]:
        DATA["routine"][scope] = [x for x in DATA["routine"][scope] if x["id"]!=iid]
    else:
        ov = DATA["overrides"].get(scope)
        if ov: ov["add"] = [x for x in ov.get("add",[]) if x["id"]!=iid]
    persist(); build_ics(); return jsonify({"ok":True})

@route("/api/done", methods=["POST"])
def api_done():
    b=request.get_json(force=True); k=b["key"]
    DATA["done"][k] = not DATA["done"].get(k,False); persist()
    return jsonify({"ok":True,"done":DATA["done"][k]})

@route("/api/memory", methods=["POST"])
def api_memory():
    b=request.get_json(force=True)
    if b.get("del"):
        DATA["memory"]=[m for m in DATA["memory"] if m["id"]!=b["del"]]
    else:
        DATA["memory"].append({"id":uid(),"text":b["text"].strip(),"when":ar_date(now())})
    persist(); return jsonify({"ok":True})

@route("/api/settings", methods=["POST"])
def api_settings():
    b=request.get_json(force=True)
    if "whatsapp" in b: DATA["profile"]["whatsapp"]=b["whatsapp"].strip()
    if "name" in b and b["name"].strip(): DATA["profile"]["name"]=b["name"].strip()
    if "reminderMin" in b: DATA["settings"]["reminderMin"]=int(b["reminderMin"])
    if "whatsapp_enabled" in b: DATA["settings"]["whatsapp_enabled"]=bool(b["whatsapp_enabled"])
    if "api_key" in b: DATA["settings"]["api_key"]=b["api_key"].strip()
    if "gemini_key" in b: DATA["settings"]["gemini_key"]=b["gemini_key"].strip()
    if "model" in b and b["model"].strip(): DATA["settings"]["model"]=b["model"].strip()
    persist(); return jsonify({"ok":True})

@route("/api/open", methods=["POST"])
def api_open():
    b=request.get_json(force=True); url=b.get("url")
    if url: webbrowser.open(url)
    return jsonify({"ok":True})

@route("/api/test_whatsapp", methods=["POST"])
def api_test_whatsapp():
    num = DATA["profile"].get("whatsapp","")
    if not num: return jsonify({"ok":False,"msg":"اكتب رقم الواتساب الأول"})
    ok = send_whatsapp(num, "جارفيس شغّال ✅ — دي رسالة تجربة.")
    return jsonify({"ok":ok,"msg":"بعتّ رسالة تجربة، شوف الواتساب." if ok else "مش قادر أبعت. اتأكد إن واتساب ويب مسجّل دخول وإن pywhatkit متسطّب."})

@route("/jarvis.ics")
def api_ics():
    data = build_ics()
    return Response(data, mimetype="text/calendar",
                    headers={"Content-Disposition":"attachment; filename=jarvis_calendar.ics"})

@route("/api/build_ics", methods=["POST"])
def api_build_ics():
    build_ics()
    return jsonify({"ok":True,"msg":"اتعمل تقويم جديد. نزّله من زرار «تقويم الأيفون»."})

# ------------------------------------------------------------------ run
def open_browser():
    time.sleep(1.2)
    url = "http://127.0.0.1:5000"
    # نفتح في Microsoft Edge عشان الأصوات الطبيعية (Natural) تبقى متاحة
    try:
        subprocess.Popen('start msedge --new-window "%s"' % url, shell=True); return
    except Exception: pass
    try: webbrowser.open(url)
    except Exception: pass

if __name__ == "__main__":
    # وضع توليد التقويم فقط:  python jarvis.py --ics
    if "--ics" in sys.argv:
        build_ics()
        print("اتعمل ملف التقويم:", ICS_FILE)
        sys.exit(0)
    if app is None:
        print("لازم تسطّب flask الأول:  py -m pip install flask")
        sys.exit(1)
    build_ics()  # نجهّز التقويم من أول تشغيل
    threading.Thread(target=reminder_loop, daemon=True).start()
    threading.Thread(target=open_browser, daemon=True).start()
    print("="*48)
    print("  جارفيس شغّال!  افتح: http://127.0.0.1:5000")
    print("  عشان تقفله: اقفل النافذة دي أو اضغط Ctrl+C")
    print("="*48)
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
