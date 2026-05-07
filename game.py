from js import document, localStorage, JSON, performance, setTimeout, unlockAudio, playRing, confettiBurst, play_baby_bird
from js import play_egg_taps, play_hatch_crack, play_chick_chirp, play_duck_quack, fetch
from pyscript import when  # @when attaches event handlers by selector. [2](https://stackoverflow.com/questions/79035217/how-to-play-a-mp3-file-with-pyscript)[3](https://github.com/pyodide/pyodide/discussions/2229)
import json
import random, math
from pyodide.ffi import create_proxy

KEY = "rainbow_sums_stats_v1"
GAME_DURATION = 150_000  # ms
game_start_ms = None
game_over = False
game_timer = None
_next_proxy = None
mascot = document.getElementById("mascot")
eggSvg = document.getElementById("eggSvg")
mascotEmoji = document.getElementById("mascotEmoji")
crackEls = document.querySelectorAll("#eggSvg .crack")
cracks = 0  # how many cracks shown in egg stage

LANG = "pt"
TEXT = {}

async def load_lang():
    global TEXT
    r = await fetch(f"lang/{LANG}.json")
    TEXT = json.loads(await r.text())

DEBUG = False

def log(*x):
    if DEBUG:
        print(*x)

def now_ms() -> float:
    return float(performance.now())

def clear_anim(el):
    el.classList.remove("anim-wobble", "anim-crack", "anim-chick", "anim-duck")
    el.offsetWidth  # reflow

def set_egg_cracks(n):
    # n can be 0..len(crackEls)
    for i, el in enumerate(crackEls):
        el.style.opacity = "1" if i < n else "0"

def stage_from_correct(cor):
    if cor < 20:
        return "egg"
    if cor < 40:
        return "hatching"
    if cor < 60:
        return "chick"
    return "duck"

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def pair_key(a, b):
    a, b = (a, b) if a <= b else (b, a)
    return f"{a}-{b}"

ALL_PAIRS = []
for s in range(2, 11):
    for a in range(0, s + 1):
        b = s - a
        if a <= b:
            ALL_PAIRS.append((a, b))

stats = {}

def load_stats():
    global stats
    raw = localStorage.getItem(KEY)
    if raw:
        try:
            # raw is a JSON string stored earlier
            stats = json.loads(str(raw))
        except Exception as e:
            log("⚠️ Ops, erro! Recomeçando:", e)
            stats = {}
    else:
        stats = {}

def save_stats():
    # Store as plain JSON text
    localStorage.setItem(KEY, json.dumps(stats))

def get_entry(a, b):
    k = pair_key(a, b)
    if k not in stats:
        stats[k] = {"attempts": 0, "correct": 0, "ema_time": None, "last_ms": 0}
    return stats[k]

def overall_totals():
    att = sum(v["attempts"] for v in stats.values()) if stats else 0
    cor = sum(v["correct"] for v in stats.values()) if stats else 0
    times = [v["ema_time"] for v in stats.values() if v.get("ema_time") is not None]
    avg_t = sum(times)/len(times) if times else None
    return att, cor, avg_t

WARMUP_TOTAL_ATTEMPTS = 18
TARGET_TIME = 3.6
MIN_ATTEMPTS_FOR_PAIR = 2

def pair_weight(a, b):
    entry = get_entry(a, b)
    attempts = entry["attempts"]
    correct = entry["correct"]
    ema_time = entry["ema_time"]

    explore = 1.0 / math.sqrt(attempts + 1)
    err = 0.45 if attempts == 0 else (1.0 - (correct / attempts))
    t_factor = 0.6 if ema_time is None else max(0.0, (ema_time / TARGET_TIME) - 1.0)

    difficulty = 1.0 + (2.2 * err) + (1.2 * t_factor) + (0.6 * explore)
    return clamp(difficulty, 0.35, 4.0)

def choose_next_pair():
    total_attempts, _, _ = overall_totals()
    if total_attempts < WARMUP_TOTAL_ATTEMPTS:
        return random.choice(ALL_PAIRS), False

    weights = [pair_weight(a,b) for (a,b) in ALL_PAIRS]
    for i, (a,b) in enumerate(ALL_PAIRS):
        if get_entry(a,b)["attempts"] < MIN_ATTEMPTS_FOR_PAIR:
            weights[i] *= 1.25
    return random.choices(ALL_PAIRS, weights=weights, k=1)[0], True

aBox = document.getElementById("aBox")
bBox = document.getElementById("bBox")
sumBox = document.getElementById("sumBox")
message = document.getElementById("message")
answers = document.getElementById("answers")
gameCard = document.getElementById("gameCard")
overlay = document.getElementById("gameOverOverlay")
finalScoreEl = document.getElementById("finalScore")
birdAnim = document.getElementById("birdAnim")
restartBtn = document.getElementById("restartBtn")

streakEl = document.getElementById("streak")
accuracyEl = document.getElementById("accuracy")
avgtimeEl = document.getElementById("avgtime")
adaptEl = document.getElementById("adapt")

startBtn = document.getElementById("startBtn")
resetBtn = document.getElementById("resetBtn")
peekBtn = document.getElementById("peekBtn")
hintEl = document.getElementById("hint")

current = None
current_sum = None
shown_ms = None
streak = 0
started = False
game_attempts = 0
game_correct = 0

def set_message(text, kind="neutral"):
    message.className = f"pill {kind}"
    message.innerHTML = text

def set_problem(a, b):
    global current, current_sum, shown_ms
    current = (a, b)
    current_sum = a + b
    shown_ms = now_ms()

    da, db = (a, b) if random.random() < 0.5 else (b, a)
    aBox.textContent = str(da)
    bBox.textContent = str(db)
    sumBox.textContent = "?"

    for el in (aBox, bBox, sumBox):
        el.classList.remove("pop")
        el.offsetWidth
        el.classList.add("pop")

def render_answer_buttons():
    answers.innerHTML = ""
    for v in range(2, 11):
        btn = document.createElement("button")
        btn.className = "ans"
        btn.textContent = str(v)
        btn.dataset.val = str(v)
        answers.appendChild(btn)

def update_side_panel():
    att, cor, avg_t = overall_totals()
    accuracyEl.textContent = "—" if att == 0 else f"{round((cor/att)*100)}%"
    avgtimeEl.textContent = "—" if avg_t is None else f"{avg_t:.1f}s"
    streakEl.textContent = str(streak)
    adaptEl.textContent = "preparando…" if att < WARMUP_TOTAL_ATTEMPTS else "LIGADO ✅"

def record_attempt(a, b, was_correct: bool, time_to_correct_s):
    entry = get_entry(a, b)
    entry["attempts"] += 1
    if was_correct:
        entry["correct"] += 1
        if time_to_correct_s is not None:
            if entry["ema_time"] is None:
                entry["ema_time"] = float(time_to_correct_s)
            else:
                entry["ema_time"] = 0.70 * float(entry["ema_time"]) + 0.30 * float(time_to_correct_s)
    entry["last_ms"] = now_ms()
    save_stats()

def gentle_hint(a, b):
    bigger = max(a, b)
    smaller = min(a, b)
    return f"" #Try counting up from <b>{bigger}</b> by <b>{smaller}</b>!"

def flash_wrong():
    gameCard.classList.remove("shake")
    gameCard.offsetWidth
    gameCard.classList.add("shake")

def celebrate_right():
    playRing()
    confettiBurst()
    sumBox.classList.remove("pop")
    sumBox.offsetWidth
    sumBox.classList.add("pop")

def next_question():
    global game_over, TEXT
    if game_over:
        return

    if now_ms() - game_start_ms >= GAME_DURATION:
        end_game()
        return

    (a, b), _ = choose_next_pair()
    set_problem(a, b)
    set_message(TEXT["answer"] +" 👇", "neutral")
    update_side_panel()

def _next_proxy_func():
    next_question()

_next_proxy = create_proxy(_next_proxy_func)

def submit_answer(val: int):
    global streak, game_attempts, game_correct, cracks, crackEls, TEXT
    if not started or current is None:
        return
    
    a, b = current
    correct = (val == current_sum)
    game_attempts += 1

    if correct:
        t = (now_ms() - shown_ms) / 1000.0 if shown_ms is not None else None
        record_attempt(a, b, True, t)
        streak += 1
        game_correct += 1
        sumBox.textContent = str(val)
        set_message(f"✅ {TEXT["good"]}! <b>{a} + {b} = {val}</b>", "good")
        celebrate_right()
        update_side_panel()

        # cracks grow only before chick stage
        st = stage_from_correct(game_correct)
        if st == "egg":
            cracks = min(cracks + 0.5, len(crackEls))
        else:
            cracks = 0

        update_mascot(on_correct=True)

        # next question fast
        setTimeout(_next_proxy, 200)
    else:
        record_attempt(a, b, False, None)
        streak = 0
        flash_wrong()
        set_message(f"❌ {TEXT["bad"]}. {gentle_hint(a,b)}", "bad")
        update_side_panel()

def update_mascot(on_correct: bool):
    global cracks, game_correct

    cor = game_correct
    st = stage_from_correct(cor)

    def show_egg_mode(emoji_text=None):
        eggSvg.style.display = "block"
        mascotEmoji.style.display = "none"
        if emoji_text:
            mascotEmoji.textContent = emoji_text

    def show_emoji_mode(ch):
        eggSvg.style.display = "none"
        mascotEmoji.style.display = "block"
        mascotEmoji.textContent = ch

    if st == "egg":
        show_egg_mode()
        set_egg_cracks(int(cracks))
        if on_correct:
            play_egg_taps()
    
    elif st == "hatching":
        show_emoji_mode("🐣")
        if on_correct:
            clear_anim(mascot); mascot.classList.add("anim-crack")
            play_hatch_crack()


    elif st == "chick":
        show_emoji_mode("🐥")
        if on_correct:
            clear_anim(mascot); mascot.classList.add("anim-chick")
            play_chick_chirp()

    else:  # duck
        show_emoji_mode("🦆")
        if on_correct:
            clear_anim(mascot); mascot.classList.add("anim-duck")
            play_duck_quack()


def start_game(_evt=None):
    global started, game_start_ms, game_over, game_attempts, game_correct, cracks
    unlockAudio()
    started = True
    game_over = False
    game_start_ms = now_ms()
    game_attempts = 0
    game_correct = 0
    cracks = 0
    update_mascot(on_correct=False)
    game_start_ms = now_ms()

    def tick():
        if game_over:
            return
        if now_ms() - game_start_ms >= GAME_DURATION:
            end_game()
            return
        setTimeout(tick, 250)  # check every 0.25s

    tick()
    next_question()

def end_game():
    global game_over, started
    game_over = True
    started = False

    att = game_attempts
    cor = game_correct
    acc = 0 if att == 0 else round((cor / att) * 100)

    finalScoreEl.innerHTML = (
        f"{TEXT["attempts"]}: <b>{att}</b><br>"
        f"{TEXT["correct"]}: <b>{cor}</b><br>"
        f"{TEXT["accuracy"]}: <b>{acc}%</b>"
    )

    birdAnim.classList.remove("egg-wobble", "hatch-wiggle", "chick-hop")

    if cor < 20:
        birdAnim.textContent = "🥚"
        birdAnim.classList.add("egg-wobble")
        play_egg_taps()

    elif cor < 40:
        birdAnim.textContent = "🐣"
        birdAnim.classList.add("hatch-wiggle")
        play_hatch_crack()

    else:
        birdAnim.textContent = "🐥"
        birdAnim.classList.add("chick-hop")
        play_chick_chirp()

    overlay.style.display = "flex"

def reset_stats(_evt=None):
    global stats, streak, started, TEXT
    stats = {}
    streak = 0
    started = False
    localStorage.removeItem(KEY)
    set_message(TEXT["reset_stats"], "neutral")
    aBox.textContent = "?"
    bBox.textContent = "?"
    sumBox.textContent = "?"
    update_side_panel()

def show_hardest(_evt=None):
    global TEXT
    if not stats:
        hintEl.textContent = TEXT["hardest"]
        return

    scored = []
    for (a, b) in ALL_PAIRS:
        k = pair_key(a,b)
        if k in stats:
            scored.append(((a,b), pair_weight(a,b), stats[k]))
    if not scored:
        hintEl.textContent = TEXT["learning"]
        return

    scored.sort(key=lambda x: x[1], reverse=True)
    (a,b), w, e = scored[0]
    att, cor = e["attempts"], e["correct"]
    ema = e["ema_time"]
    ema_txt = "—" if ema is None else f"{ema:.1f}s"
    hintEl.innerHTML = (
        f"{TEXT["hard_now"]}: <b>{a}+{b}</b> "
        f"({TEXT["weight"]} {w:.2f}) • {TEXT["attempts"]}: <b>{att}</b> • {TEXT["correct"]}: <b>{cor}</b> • {TEXT["time"]}: <b>{ema_txt}</b>"
    )

# PyScript event binding using @when (recommended). [2](https://stackoverflow.com/questions/79035217/how-to-play-a-mp3-file-with-pyscript)[3](https://github.com/pyodide/pyodide/discussions/2229)
@when("click", "#startBtn")
def _start_clicked(evt):
    start_game(evt)

@when("click", "#resetBtn")
def _reset_clicked(evt):
    reset_stats(evt)

@when("click", "#peekBtn")
def _peek_clicked(evt):
    show_hardest(evt)

@when("click", "#answers")
def _answers_clicked(evt):
    if not evt.target.classList.contains("ans"):
        return
    submit_answer(int(evt.target.dataset.val))

@when("click", "#restartBtn")

@when("click", "#restartBtn")
def _restart(evt):
    overlay.style.display = "none"
    birdAnim.classList.remove("egg-wobble", "hatch-wiggle", "chick-hop")
    start_game(evt)


# Initialize
await load_lang()
load_stats()
render_answer_buttons()
update_side_panel()

# Enable Start only after Python has successfully run
startBtn.disabled = False
startBtn.textContent = TEXT["start"]
set_message("Clique em <b>Começar</b> ✨", "neutral")

log("✅ Python loaded — handlers active, yay")