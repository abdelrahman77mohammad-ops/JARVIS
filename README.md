<div align="center">

# 🤖 JARVIS — A Personal AI Assistant

**A voice-controlled desktop assistant that talks back, sees through your camera,
manages your university schedule, opens and controls your apps, and even writes,
explains, and runs code for you.**

Built by Computer Science students, for the daily grind of student life.

</div>

---

## 📖 The story

Over the last **three months**, as Computer Science students, we kept running into the
same thing: too many lectures, labs, quizzes, assignments and little tasks to track — and
too much time lost to the small stuff (opening the same apps, hunting for lecture links,
writing boilerplate code).

So we built our own **JARVIS** — an AI assistant that actually *helps* with the day‑to‑day:
it keeps our schedule, reminds us before lectures and quizzes, opens and closes programs on
command, sees hardware parts through the webcam, reads an assignment and starts writing the
solution, runs the code, and explains it — all by voice.

It's **open source**, so if you're curious how a project like this comes together, dig in. 👇

---

## ✨ What it can do

- 🎙️ **Hands‑free voice** — always‑listening; talk naturally, it replies out loud in a natural English voice.
- 🧠 **Real AI brain** — an LLM with tool‑use (free via **Groq**), so it reasons, answers anything, and decides what to do.
- 📅 **Schedule manager** — recurring weekly timetable + one‑off quizzes/meetings. *"What's on today?"* → subject + time.
- ⏰ **Reminders everywhere** — in‑app + browser notifications, **WhatsApp** messages, and an **iPhone calendar (.ics)** with a *day‑before* alarm for quizzes (works offline, laptop closed).
- 🧩 **Memory** — tell it facts about you; it remembers them across sessions.
- 🖥️ **App control** — *"open Arduino"*, *"close Discord"*, *"what apps are open?"* — opens/closes any installed program (classic + Microsoft Store apps).
- 👁️ **Computer vision** — *"open the camera" → "what am I holding?" / "how many objects?"* — recognizes hardware (ESP32, Arduino, breadboards, sensors) and counts the items in your hand, via **Google Gemini**.
- 📎 **Assignment solver** — upload an assignment (PDF / image / text); it reads it and writes the code to solve it.
- ⌨️ **Coding partner** — *"write a Python script that…"* → it writes the file, **opens it in VS Code / IntelliJ / Arduino IDE**, explains it, and *"run it"* executes it and reads back the output.

---

## 🛠️ Tech stack & how it was built

| Layer | What we used |
|-------|--------------|
| **Backend** | Python 3.11 + **Flask** (local server on `127.0.0.1:5000`) |
| **AI brain** | **Groq** API (free — `openai/gpt-oss-120b`) with OpenAI‑style tool calling |
| **Vision** | **Google Gemini** (`gemini-2.5-flash`) for camera + document understanding |
| **Voice** | Browser **Web Speech API** — `SpeechRecognition` (in) + `SpeechSynthesis` (out, natural neural voices) |
| **Frontend** | Vanilla **HTML/CSS/JS**, animated arc‑reactor **Canvas** face, no framework |
| **System control** | Windows `Get-StartApps`, `shell:appsFolder`, PowerShell, `subprocess` |
| **Reminders** | iCalendar (`.ics`) with alarms · `pywhatkit` (WhatsApp Web) |
| **Storage** | Local JSON (`data.json`) — everything stays on your machine |
| **Networking** | Plain `urllib` to the LLM/vision APIs (no SDKs) |

**Architecture**

```
┌──────────────┐   HTTP    ┌─────────────────┐
│  face.html   │ ───────▶  │   jarvis.py     │  Flask server
│  (browser)   │           │                 │
│ orb · voice  │ ◀───────  │  tool dispatch  │
│ camera       │  JSON     └───┬────────┬────┘
└──────────────┘               │        │
             ┌─────────────────┘        └──────────────────┐
             ▼                                              ▼
        brain.py                                     system control
  (Groq tool‑use,                             open/close apps · write/run/explain
   Gemini vision)                             code · schedule · reminders
```

Every spoken or typed message goes to the Flask backend. If a brain key is set, it's sent to
the LLM with a set of **tools** (`open_app`, `close_app`, `list_open_apps`,
`create_code_file`, `run_code_file`, `add_to_schedule`, `get_schedule`, `remember`). The LLM
replies conversationally and triggers the matching action. Camera frames and uploaded
documents are sent to Gemini.

---

## 🚀 Run it yourself

**Requirements:** Python 3.11+, Google Chrome or Microsoft Edge (Edge gives the most natural voices).

```bash
git clone https://github.com/abdelrahman77mohammad-ops/JARVIS.git
cd JARVIS
pip install -r requirements.txt
python jarvis.py
```

Opens automatically at `http://127.0.0.1:5000`. On Windows, just double‑click **`START.bat`**.

- **Enable the brain (free):** key from [console.groq.com](https://console.groq.com) → **Settings → JARVIS Brain**.
- **Enable the camera (free):** key from [aistudio.google.com](https://aistudio.google.com/app/apikey) → **Settings → Camera / Vision**.

Try: *"what's on today?"* · *"open Arduino"* · *"open the camera, what am I holding?"* · *"write a Python file that prints the Fibonacci sequence, then run it"*.

---

## 🎬 Demo

See JARVIS in action: [`demo.mp4`](demo.mp4)

---

## 🔒 Privacy

All your data (schedule, memory, API keys) lives locally in `data.json`, which is **git‑ignored**
and never leaves your machine. The only outbound calls are to the LLM/vision APIs you enable.

## 🙌 Open source

This started as our own student project — feel free to explore the code, learn from it, fork it,
and build your own JARVIS. Ideas and PRs welcome.

## 📝 License

MIT — see [LICENSE](LICENSE).
