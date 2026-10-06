# -*- coding: utf-8 -*-
"""
JARVIS brain — connects to an LLM (Groq, free) so it can think, answer, and use tools.
No external packages — urllib only.
"""
import json, time, urllib.request, urllib.error

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM = """You are JARVIS, a personal AI assistant in the style of Tony Stark's JARVIS: composed, concise, polished, lightly witty, and genuinely helpful. You speak English.

Rules:
- Keep replies short and natural, the way a real assistant speaks out loud. Avoid emojis and markup.
- Answer general questions directly from your knowledge.
- When the user tells you something about themselves (preferences, names, facts, anything worth remembering), call the remember tool.
- When they ask you to open an app or website, call open_app. When they ask to close/quit/exit a program, call close_app. When they ask what's open/running, call list_open_apps (then they may ask you to close some).
- When they ask you to write code, create a file, or start a script/program, write the full code yourself and call create_code_file with a sensible filename and the complete content. Then tell them briefly what you created. For an assignment or project, do NOT ask clarifying questions — make reasonable assumptions and produce complete, working code. For a multi-file/multi-class project, create the files one at a time (one create_code_file call per class/file).
- When they ask you to run or execute the code, call run_code_file, then read back the output briefly.
- When they mention a lecture, quiz, task, or meeting, call add_to_schedule. Quizzes and exams are important (important=true) and one-time (not recurring).
- When they ask about their schedule, call get_schedule, then reply with ONLY the subject name and the time for each item, as a short spoken list. Do NOT mention the date, the day name, the month, room/place names, or codes. No intro ("Certainly"), no sign-off ("let me know..."). Example: "At 9, Operating Systems Lab. At 10:45, Logic Design Lab. At 12:30, Data Mining Lab."
- Refer to yourself as JARVIS. Keep every answer brief and spoken-friendly.

Current facts about the user and their schedule are provided below — use them in your replies."""

TOOLS = [
    {"name":"remember","description":"Save a fact about the user to remember later.",
     "input_schema":{"type":"object","properties":{"fact":{"type":"string"}},"required":["fact"]}},
    {"name":"open_app","description":"Open an app or website on the laptop.",
     "input_schema":{"type":"object","properties":{"query":{"type":"string","description":"app or site name, e.g. Teams, YouTube, Classroom"}},"required":["query"]}},
    {"name":"close_app","description":"Close/quit a running program on the laptop by name.",
     "input_schema":{"type":"object","properties":{"query":{"type":"string","description":"program name, e.g. Discord, Chrome, Calculator"}},"required":["query"]}},
    {"name":"list_open_apps","description":"List the programs currently open (with a window) on the laptop.",
     "input_schema":{"type":"object","properties":{}}},
    {"name":"create_code_file","description":"Write code or text to a file and open it in VS Code. Use when the user asks you to create a file, write code, or start a program/script.",
     "input_schema":{"type":"object","properties":{
        "filename":{"type":"string","description":"file name with extension, e.g. main.py, index.html, blink.ino"},
        "content":{"type":"string","description":"the full file content / code you wrote"}},
        "required":["filename","content"]}},
    {"name":"run_code_file","description":"Run a Python or JavaScript file you created and get its output. Use when the user says run/execute the code.",
     "input_schema":{"type":"object","properties":{"filename":{"type":"string","description":"optional; the file to run. Leave empty to run the last created file."}}}},
    {"name":"add_to_schedule","description":"Add a lecture/quiz/task/meeting to the user's schedule.",
     "input_schema":{"type":"object","properties":{
        "title":{"type":"string"},
        "day":{"type":"string","description":"today, tomorrow, sat, sun, mon, tue, wed, thu, fri"},
        "time":{"type":"string","description":"24h HH:MM, optional"},
        "type":{"type":"string","enum":["lecture","lab","ميتنج","مهمة","سكشن"]},
        "important":{"type":"boolean","description":"true for quiz/exam/important"},
        "recurring":{"type":"boolean","description":"true if it repeats weekly"}},
        "required":["title","day"]}},
    {"name":"get_schedule","description":"Get the user's schedule for a given day.",
     "input_schema":{"type":"object","properties":{"day":{"type":"string","description":"today, tomorrow, or a weekday name"}},"required":["day"]}},
]


def _http(url, headers, payload):
    # User-Agent ضروري عشان Cloudflare مايبلوكش الطلب (error 1010)
    headers = dict(headers)
    headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS/1.0")
    headers.setdefault("Accept", "application/json")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- Groq (OpenAI-style)
def _tools_openai():
    return [{"type":"function","function":{"name":t["name"],"description":t["description"],"parameters":t["input_schema"]}} for t in TOOLS]

GROQ_FALLBACKS = ["openai/gpt-oss-120b", "llama-3.1-70b-versatile", "llama-3.1-8b-instant"]

def _groq_call(headers, payload, model):
    """Try the given model, then fall back to known-good models if it's gone."""
    models = [model] + [m for m in GROQ_FALLBACKS if m != model]
    last = None
    for m in models:
        payload["model"] = m
        try:
            return _http(GROQ_URL, headers, payload)
        except urllib.error.HTTPError as e:
            if e.code == 429:             # rate limit -> استنى وأعد مرة
                time.sleep(12)
                try:
                    return _http(GROQ_URL, headers, payload)
                except urllib.error.HTTPError as e2:
                    if e2.code in (400, 404): last = e2; continue
                    raise
            if e.code in (400, 404):      # model unavailable/decommissioned -> try next
                last = e; continue
            raise
    raise last

def _respond_groq(user_text, api_key, model, sys_full, history, handlers):
    headers = {"Authorization":"Bearer "+api_key,"content-type":"application/json"}
    messages = [{"role":"system","content":sys_full}] + list(history) + [{"role":"user","content":user_text}]
    did = False
    for _ in range(5):
        resp = _groq_call(headers,
                     {"messages":messages,"tools":_tools_openai(),"max_tokens":4096,"temperature":0.6}, model)
        msg = resp["choices"][0]["message"]
        messages.append(msg)
        calls = msg.get("tool_calls")
        if calls:
            for tc in calls:
                name = tc["function"]["name"]
                try: args = json.loads(tc["function"].get("arguments") or "{}")
                except Exception: args = {}
                out = handlers.get(name, lambda a:"n/a")(args)
                if name in ("remember","add_to_schedule"): did=True
                messages.append({"role":"tool","tool_call_id":tc["id"],"content":str(out)})
            continue
        return ((msg.get("content") or "Done.").strip(), did)
    return ("That took too long, try again.", did)


# ---------------------------------------------------------------- Gemini vision (FREE)
GEMINI_VISION_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
SYSTEM_VISION = ("You are JARVIS, a witty, concise assistant speaking out loud. "
                 "ALWAYS reply in English, no matter what language the question is written in. "
                 "Focus ONLY on the object or objects the person is holding up or showing toward the camera "
                 "(in the center/foreground). IGNORE the person's face or body, the wall, the background, "
                 "lighting, and anything they are not holding — never mention those. "
                 "If they ask how many objects they are holding, carefully COUNT the distinct items in their "
                 "hands and state the number first, then name each one (e.g. 'Two: an Arduino Uno and a breadboard'). "
                 "Otherwise, name what they are holding (e.g. ESP32, Arduino Uno, Arduino Nano, breadboard, a sensor "
                 "or module). Keep it short and natural.")

def vision(image_b64, question, api_key, context_block="", mime_type="image/jpeg", system=None, max_tokens=400):
    """image_b64: raw base64 (no data: prefix). mime_type can be image/* or application/pdf."""
    prompt = (system or SYSTEM_VISION) + ("\n"+context_block if context_block else "") + \
             "\n\nUser: " + (question or "What do you see in front of me?")
    body = {"contents":[{"parts":[
        {"inline_data":{"mime_type":mime_type,"data":image_b64}},
        {"text":prompt}]}],
        "generationConfig":{"maxOutputTokens":max_tokens}}
    headers = {"content-type":"application/json", "x-goog-api-key":api_key}
    last = ""
    for m in GEMINI_VISION_MODELS:
        url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % m
        try:
            resp = _http(url, headers, body)
            for cand in resp.get("candidates", []):
                parts = cand.get("content", {}).get("parts", [])
                txt = "".join(p.get("text","") for p in parts)
                if txt.strip(): return txt.strip()
            last = "I couldn't make out anything."
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):   # model name not available -> try next
                continue
            if e.code in (401, 403):
                return "The Gemini key seems invalid. Add a valid key in Settings (vision)."
            try: msg = json.loads(e.read().decode()).get("error",{}).get("message","")
            except Exception: msg = str(e)
            return "Vision error: " + str(msg)[:120]
        except Exception as e:
            return "Vision failed: " + str(e)[:80]
    return last or "Couldn't reach the vision model."

# ---------------------------------------------------------------- dispatcher
def respond(provider, user_text, api_key, model, context_block, history, handlers):
    sys_full = SYSTEM + "\n\n=== Current info ===\n" + context_block
    try:
        return _respond_groq(user_text, api_key, model, sys_full, history, handlers)
    except urllib.error.HTTPError as e:
        try: msg = json.loads(e.read().decode()).get("error",{}).get("message","")
        except Exception: msg = str(e)
        if e.code in (401,403): return ("The API key seems invalid. Check it in Settings.", False)
        if e.code == 429: return ("Rate limit hit — give it a moment and try again.", False)
        return ("API problem: "+str(msg)[:120], False)
    except Exception as e:
        return ("I can't reach my brain right now ("+str(e)[:70]+"). Check the key and your connection.", False)
