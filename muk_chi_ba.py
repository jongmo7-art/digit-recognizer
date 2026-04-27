"""Muk-Chi-Ba (묵찌빠) game: human vs computer, Tkinter UI with voice SFX.

Rules:
  Phase 1 — plain Rock/Scissors/Paper until someone wins a throw; that
  player becomes the attacker (공격자).
  Phase 2 — both throw again. If the throws match, the current attacker
  wins the whole match. If they differ, the winner of the throw becomes
  the new attacker and play continues.

Stakes (configured by the user for their kids): win = sleep with mom at
the upcoming camping trip, lose = sleep with dad. Pure-random CPU.

Sound effects: Korean "묵/찌/빠" voices are synthesized once via the
Windows Speech API (System.Speech) into sounds/*.wav on first run, then
played back asynchronously with winsound on every throw.

End-of-match cutscenes: when the user wins, a cartoon character
"경떡이" dances with confetti; when they lose, 경떡이 cries and walks
with Dad into a tent for the night. Both run in Toplevel windows so
the main game window stays available for "다시하기".
"""

import math
import random
import subprocess
import tkinter as tk
import winsound
from pathlib import Path
from tkinter import font as tkfont

# Internal move tokens; Korean display names live in KOREAN below.
ROCK = "rock"
SCISSORS = "scissors"
PAPER = "paper"
MOVES = [ROCK, SCISSORS, PAPER]

KOREAN = {ROCK: "바위(묵)", SCISSORS: "가위(찌)", PAPER: "보(빠)"}
EMOJI = {ROCK: "✊", SCISSORS: "✌", PAPER: "✋"}
# Key beats value.
BEATS = {ROCK: SCISSORS, SCISSORS: PAPER, PAPER: ROCK}
# Move -> sound file stem (matches the Korean syllable).
SOUND_STEM = {ROCK: "muk", SCISSORS: "jji", PAPER: "ppa"}

SOUNDS_DIR = Path(__file__).with_name("sounds")
# Delay between the user's throw sound and the CPU's reveal, in ms.
REVEAL_DELAY_MS = 500


# --- sound helpers --------------------------------------------------

def _ensure_sounds() -> None:
    """Generate muk/jji/ppa WAVs via Windows SAPI on first run.

    Writes a UTF-8-BOM PowerShell script so PS 5.1 reads the Hangul
    literals correctly (without the BOM, PS 5.1 falls back to the
    legacy code page and mangles the text).
    """
    SOUNDS_DIR.mkdir(exist_ok=True)
    needed = [f"{s}.wav" for s in SOUND_STEM.values()]
    if all((SOUNDS_DIR / n).exists() for n in needed):
        return
    script = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$ko = $s.GetInstalledVoices() | Where-Object "
        "{ $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | Select-Object -First 1\n"
        "if ($ko) { $s.SelectVoice($ko.VoiceInfo.Name) }\n"
        "$s.Rate = 2\n"
        "$base = Split-Path -Parent $MyInvocation.MyCommand.Path\n"
        "foreach ($pair in @(@('muk','묵'), @('jji','찌'), @('ppa','빠'))) {\n"
        "    $out = Join-Path $base ($pair[0] + '.wav')\n"
        "    $s.SetOutputToWaveFile($out)\n"
        "    $s.Speak($pair[1])\n"
        "}\n"
        "$s.Dispose()\n"
    )
    script_path = SOUNDS_DIR / "_gen.ps1"
    script_path.write_text(script, encoding="utf-8-sig")
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        # Sound is optional — the game still works silently if this fails.
        pass


def _play_sound(stem: str) -> None:
    """Play a pre-generated WAV asynchronously. No-op if the file is missing."""
    p = SOUNDS_DIR / f"{stem}.wav"
    if p.exists():
        winsound.PlaySound(str(p), winsound.SND_FILENAME | winsound.SND_ASYNC)


# --- end-of-match cutscenes ----------------------------------------


class _SceneBase(tk.Toplevel):
    """Shared Toplevel + Canvas frame driver for the win/lose scenes."""

    W = 520
    H = 420
    TICK_MS = 60

    def __init__(self, parent: tk.Misc, title: str, bg: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.configure(bg=bg)
        self.canvas = tk.Canvas(
            self, width=self.W, height=self.H, bg=bg, highlightthickness=0
        )
        self.canvas.pack()
        self.frame = 0
        self.stopped = False
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(self.TICK_MS, self._loop)

    def _loop(self) -> None:
        if self.stopped:
            return
        try:
            self._tick()
        except tk.TclError:
            # Window was destroyed mid-tick; stop silently.
            return
        self.frame += 1
        self.after(self.TICK_MS, self._loop)

    def _tick(self) -> None:
        raise NotImplementedError

    def _close(self) -> None:
        self.stopped = True
        self.destroy()


# Shared palette for the 경떡이 character.
SKIN = "#ffd7a0"
OUTLINE = "#6d4c2a"
KID_SHIRT = "#ff7043"


class WinScene(_SceneBase):
    """경떡이 dances with confetti raining down."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "🏆 경떡이 우승 댄스!", bg="#fff8e1")

        self.canvas.create_text(
            self.W // 2,
            32,
            text="🎉 경떡이 우승 댄스! 🎉",
            font=("Malgun Gothic", 20, "bold"),
            fill="#d81b60",
        )
        self.canvas.create_text(
            self.W // 2,
            62,
            text="오늘 밤은 엄마랑 잘 거야~ 💕",
            font=("Malgun Gothic", 14),
            fill="#6a1b9a",
        )

        # Character parts; positions updated every tick in _tick().
        self.cx = self.W // 2
        self.cy = 250
        self.head = self.canvas.create_oval(
            0, 0, 0, 0, fill=SKIN, outline=OUTLINE, width=2
        )
        self.body = self.canvas.create_oval(
            0, 0, 0, 0, fill=KID_SHIRT, outline=OUTLINE, width=2
        )
        self.left_arm = self.canvas.create_line(
            0, 0, 0, 0, width=5, fill=OUTLINE, capstyle="round"
        )
        self.right_arm = self.canvas.create_line(
            0, 0, 0, 0, width=5, fill=OUTLINE, capstyle="round"
        )
        self.left_leg = self.canvas.create_line(
            0, 0, 0, 0, width=5, fill=OUTLINE, capstyle="round"
        )
        self.right_leg = self.canvas.create_line(
            0, 0, 0, 0, width=5, fill=OUTLINE, capstyle="round"
        )
        self.left_eye = self.canvas.create_oval(0, 0, 0, 0, fill="#222")
        self.right_eye = self.canvas.create_oval(0, 0, 0, 0, fill="#222")
        self.mouth = self.canvas.create_arc(
            0, 0, 0, 0, style="arc", start=200, extent=140, width=3, outline=OUTLINE
        )
        self.name_tag = self.canvas.create_text(
            0, 0, text="경떡이", font=("Malgun Gothic", 12, "bold"), fill="#d81b60"
        )

        # Confetti: list of [canvas_id, x, y, vy, size, color].
        self.palette = ["#e91e63", "#ffeb3b", "#4fc3f7", "#81c784", "#ba68c8", "#ff7043"]
        self.confetti: list[list] = []
        for _ in range(35):
            x = random.uniform(0, self.W)
            y = random.uniform(-self.H, 0)
            vy = random.uniform(2.5, 5.5)
            size = random.uniform(5, 10)
            color = random.choice(self.palette)
            cid = self.canvas.create_oval(
                x, y, x + size, y + size, fill=color, outline=""
            )
            self.confetti.append([cid, x, y, vy, size])

    def _tick(self) -> None:
        t = self.frame
        # Vertical bounce: small hop every beat.
        bounce = -abs(math.sin(t * 0.35)) * 22
        # Arm and leg swing phases (opposite legs/arms).
        arm = math.sin(t * 0.55)
        leg = math.cos(t * 0.55)

        cx = self.cx
        cy = self.cy + bounce

        # Head (40x40).
        self.canvas.coords(self.head, cx - 30, cy - 80, cx + 30, cy - 20)
        # Body (oval torso).
        self.canvas.coords(self.body, cx - 25, cy - 20, cx + 25, cy + 40)
        # Arms: shoulders at (cx±25, cy-10), hands swing.
        self.canvas.coords(
            self.left_arm, cx - 25, cy - 10, cx - 55, cy - 10 - arm * 35
        )
        self.canvas.coords(
            self.right_arm, cx + 25, cy - 10, cx + 55, cy - 10 + arm * 35
        )
        # Legs: hips at (cx±12, cy+40), feet kick alternately.
        self.canvas.coords(
            self.left_leg, cx - 12, cy + 40, cx - 20 + leg * 18, cy + 80
        )
        self.canvas.coords(
            self.right_leg, cx + 12, cy + 40, cx + 20 - leg * 18, cy + 80
        )
        # Eyes (small ovals).
        self.canvas.coords(self.left_eye, cx - 14, cy - 58, cx - 8, cy - 50)
        self.canvas.coords(self.right_eye, cx + 8, cy - 58, cx + 14, cy - 50)
        # Big smile arc.
        self.canvas.coords(self.mouth, cx - 14, cy - 48, cx + 14, cy - 30)
        # Name tag above head.
        self.canvas.coords(self.name_tag, cx, cy - 95)

        # Confetti fall and recycle.
        for c in self.confetti:
            cid, x, y, vy, size = c
            y += vy
            if y > self.H:
                y = -10
                x = random.uniform(0, self.W)
            c[1], c[2] = x, y
            self.canvas.coords(cid, x, y, x + size, y + size)


class LoseScene(_SceneBase):
    """경떡이 cries, Dad walks in, they enter the tent together."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, "😢 경떡이 아빠랑 텐트로...", bg="#0d1b2a")

        # Background: ground strip and a tent on the left.
        ground_y = 330
        self.canvas.create_rectangle(
            0, ground_y, self.W, self.H, fill="#2e7d32", outline=""
        )
        # Moon and stars.
        self.canvas.create_oval(
            self.W - 90, 40, self.W - 30, 100, fill="#fff59d", outline=""
        )
        for x, y in [(60, 70), (140, 40), (220, 90), (310, 60), (400, 110), (470, 180)]:
            self.canvas.create_text(
                x, y, text="✦", fill="#fff59d", font=("Segoe UI Symbol", 12)
            )
        # Tent: brown triangle with dark door.
        tent_cx = 90
        tent_base_w = 130
        tent_h = 100
        self.canvas.create_polygon(
            tent_cx - tent_base_w // 2,
            ground_y,
            tent_cx + tent_base_w // 2,
            ground_y,
            tent_cx,
            ground_y - tent_h,
            fill="#8d6e63",
            outline="#4e342e",
            width=2,
        )
        # Tent seam.
        self.canvas.create_line(
            tent_cx, ground_y, tent_cx, ground_y - tent_h, fill="#4e342e", width=2
        )
        # Door (darker inner triangle).
        self.canvas.create_polygon(
            tent_cx - 14,
            ground_y,
            tent_cx + 14,
            ground_y,
            tent_cx,
            ground_y - 55,
            fill="#1b0f0a",
            outline="",
        )
        self.tent_cx = tent_cx
        self.ground_y = ground_y

        # Title text.
        self.canvas.create_text(
            self.W // 2,
            32,
            text="경떡이는 아빠랑 자러 가요...",
            font=("Malgun Gothic", 18, "bold"),
            fill="#ffcdd2",
        )

        # Kid (경떡이) — starts at center-right of the ground.
        self.kx = 360.0
        self.ky = float(ground_y - 60)
        self.kid_name = self.canvas.create_text(
            0, 0, text="경떡이", font=("Malgun Gothic", 11, "bold"), fill="#ffe0b2"
        )
        self.kid_head = self.canvas.create_oval(
            0, 0, 0, 0, fill=SKIN, outline=OUTLINE, width=2
        )
        self.kid_body = self.canvas.create_oval(
            0, 0, 0, 0, fill=KID_SHIRT, outline=OUTLINE, width=2
        )
        self.kid_left_arm = self.canvas.create_line(0, 0, 0, 0, width=4, fill=OUTLINE)
        self.kid_right_arm = self.canvas.create_line(0, 0, 0, 0, width=4, fill=OUTLINE)
        self.kid_left_leg = self.canvas.create_line(0, 0, 0, 0, width=4, fill=OUTLINE)
        self.kid_right_leg = self.canvas.create_line(0, 0, 0, 0, width=4, fill=OUTLINE)
        # Sad mouth = downward arc (start 20, extent 140 flips smile to frown when drawn below pivot).
        self.kid_mouth = self.canvas.create_arc(
            0, 0, 0, 0, style="arc", start=20, extent=140, width=2, outline=OUTLINE
        )
        # Squinty/closed eyes — short lines.
        self.kid_left_eye = self.canvas.create_line(0, 0, 0, 0, width=2, fill="#222")
        self.kid_right_eye = self.canvas.create_line(0, 0, 0, 0, width=2, fill="#222")
        # Speech bubble text above kid.
        self.bubble = self.canvas.create_text(
            0,
            0,
            text="아빠~ 으앙 ㅠㅠ",
            font=("Malgun Gothic", 14, "bold"),
            fill="#ef9a9a",
        )
        # Falling tears: list of [canvas_id, x, y].
        self.tears: list[list] = []

        # Dad — enters from off-screen right.
        self.dx = self.W + 40.0
        self.dy = float(ground_y - 70)
        self.dad_head = self.canvas.create_oval(
            0, 0, 0, 0, fill=SKIN, outline="#3e2723", width=2
        )
        self.dad_body = self.canvas.create_oval(
            0, 0, 0, 0, fill="#455a64", outline="#263238", width=2
        )
        self.dad_left_arm = self.canvas.create_line(
            0, 0, 0, 0, width=4, fill="#263238"
        )
        self.dad_right_arm = self.canvas.create_line(
            0, 0, 0, 0, width=4, fill="#263238"
        )
        self.dad_left_leg = self.canvas.create_line(
            0, 0, 0, 0, width=4, fill="#263238"
        )
        self.dad_right_leg = self.canvas.create_line(
            0, 0, 0, 0, width=4, fill="#263238"
        )
        self.dad_mouth = self.canvas.create_line(
            0, 0, 0, 0, width=2, fill="#263238"
        )
        self.dad_eye_l = self.canvas.create_oval(0, 0, 0, 0, fill="#222")
        self.dad_eye_r = self.canvas.create_oval(0, 0, 0, 0, fill="#222")
        self.dad_name = self.canvas.create_text(
            0, 0, text="아빠", font=("Malgun Gothic", 11, "bold"), fill="#b3e5fc"
        )

        self.hidden = False
        self.zzz_id: int | None = None

    def _tick(self) -> None:
        t = self.frame

        # --- phase timeline ------------------------------------------------
        # 0-18: kid cries alone, dad still off-screen right
        # 18-48: dad walks in from right toward the kid
        # 48+: they walk left together toward the tent; disappear at x<tent
        kid_bob = math.sin(t * 0.2) * 2.0

        if t >= 18 and self.dx > 300:
            self.dx -= 5.0
        if t >= 48:
            # Walk together; swap the bubble text after a beat.
            if self.kx > self.tent_cx + 10:
                self.kx -= 3.0
                self.dx -= 3.0
        if t == 60:
            self.canvas.itemconfig(self.bubble, text="흑흑... 가자 아빠 🥲")

        # --- kid drawing ---------------------------------------------------
        kx = self.kx
        ky = self.ky + kid_bob
        self.canvas.coords(self.kid_name, kx, ky - 75)
        self.canvas.coords(self.kid_head, kx - 24, ky - 60, kx + 24, ky - 12)
        self.canvas.coords(self.kid_body, kx - 20, ky - 12, kx + 20, ky + 30)
        # Sad drooping arms.
        self.canvas.coords(self.kid_left_arm, kx - 20, ky - 5, kx - 34, ky + 22)
        self.canvas.coords(self.kid_right_arm, kx + 20, ky - 5, kx + 34, ky + 22)
        # Legs: slight walking swing once the journey starts.
        if t >= 48:
            swing = math.sin(t * 0.45) * 8
        else:
            swing = 0
        self.canvas.coords(self.kid_left_leg, kx - 10, ky + 30, kx - 10 + swing, ky + 60)
        self.canvas.coords(self.kid_right_leg, kx + 10, ky + 30, kx + 10 - swing, ky + 60)
        # Frowning mouth.
        self.canvas.coords(self.kid_mouth, kx - 10, ky - 18, kx + 10, ky - 4)
        # Closed crying eyes (short diagonal lines).
        self.canvas.coords(self.kid_left_eye, kx - 15, ky - 40, kx - 7, ky - 36)
        self.canvas.coords(self.kid_right_eye, kx + 7, ky - 40, kx + 15, ky - 36)

        # Tears: spawn from each eye periodically while still crying in place.
        if t % 5 == 0 and self.kx > self.tent_cx + 30:
            for side in (-12, 12):
                tid = self.canvas.create_oval(
                    kx + side - 3,
                    ky - 32,
                    kx + side + 3,
                    ky - 26,
                    fill="#4fc3f7",
                    outline="",
                )
                self.tears.append([tid, kx + side, ky - 32])
        alive: list[list] = []
        for tear in self.tears:
            tid, tx, ty = tear
            ty += 4
            tear[2] = ty
            self.canvas.coords(tid, tx - 3, ty, tx + 3, ty + 6)
            if ty > self.ground_y:
                self.canvas.delete(tid)
            else:
                alive.append(tear)
        self.tears = alive

        # Bubble follows kid.
        self.canvas.coords(self.bubble, kx, ky - 95)

        # --- dad drawing ---------------------------------------------------
        dx = self.dx
        dy = self.dy
        self.canvas.coords(self.dad_name, dx, dy - 85)
        self.canvas.coords(self.dad_head, dx - 28, dy - 70, dx + 28, dy - 14)
        self.canvas.coords(self.dad_body, dx - 24, dy - 14, dx + 24, dy + 38)
        # Walking leg swing while moving.
        if self.dx > 300 or t >= 48:
            leg_swing = math.sin(t * 0.45 + math.pi) * 10
        else:
            leg_swing = 0
        self.canvas.coords(self.dad_left_leg, dx - 10, dy + 38, dx - 10 + leg_swing, dy + 75)
        self.canvas.coords(self.dad_right_leg, dx + 10, dy + 38, dx + 10 - leg_swing, dy + 75)
        # Left arm reaches slightly toward the kid once close.
        reach = -20 if t >= 40 else -14
        self.canvas.coords(self.dad_left_arm, dx - 24, dy - 5, dx + reach, dy + 10)
        self.canvas.coords(self.dad_right_arm, dx + 24, dy - 5, dx + 36, dy + 18)
        # Gentle smile.
        self.canvas.coords(self.dad_mouth, dx - 8, dy - 28, dx + 8, dy - 26)
        self.canvas.coords(self.dad_eye_l, dx - 14, dy - 45, dx - 10, dy - 41)
        self.canvas.coords(self.dad_eye_r, dx + 10, dy - 45, dx + 14, dy - 41)

        # --- tent entry + sleep -------------------------------------------
        if not self.hidden and self.kx <= self.tent_cx + 10:
            # Hide both characters and switch to a zzz bubble over the tent.
            for item in (
                self.kid_head,
                self.kid_body,
                self.kid_left_arm,
                self.kid_right_arm,
                self.kid_left_leg,
                self.kid_right_leg,
                self.kid_mouth,
                self.kid_left_eye,
                self.kid_right_eye,
                self.kid_name,
                self.dad_head,
                self.dad_body,
                self.dad_left_arm,
                self.dad_right_arm,
                self.dad_left_leg,
                self.dad_right_leg,
                self.dad_mouth,
                self.dad_eye_l,
                self.dad_eye_r,
                self.dad_name,
                self.bubble,
            ):
                self.canvas.itemconfig(item, state="hidden")
            self.zzz_id = self.canvas.create_text(
                self.tent_cx + 30,
                self.ground_y - 120,
                text="Zzz... 😴",
                font=("Malgun Gothic", 18, "bold"),
                fill="#e1f5fe",
            )
            self.hidden = True

        if self.hidden and self.zzz_id is not None:
            # Gentle float for the zzz text.
            dy_off = math.sin(t * 0.1) * 3
            self.canvas.coords(
                self.zzz_id, self.tent_cx + 30, self.ground_y - 120 + dy_off
            )


# --- game app -------------------------------------------------------


class MukChiBaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("묵찌빠 - 캠핑 잠자리 대결!")
        root.geometry("560x540")
        root.resizable(False, False)
        root.configure(bg="#fffaf0")

        # None = phase 1 (RPS to decide attacker); "user"/"cpu" = phase 2.
        self.attacker: str | None = None
        self.game_over = False
        # Blocks clicks while the CPU reveal is animating.
        self._revealing = False
        # Current cutscene window, if any.
        self._scene: _SceneBase | None = None

        title_font = tkfont.Font(family="Malgun Gothic", size=20, weight="bold")
        big = tkfont.Font(family="Malgun Gothic", size=14)
        mid = tkfont.Font(family="Malgun Gothic", size=12)
        small = tkfont.Font(family="Malgun Gothic", size=10)
        huge_emoji = tkfont.Font(family="Segoe UI Emoji", size=48)

        tk.Label(
            root,
            text="🏕️  캠핑 잠자리 대결!  🏕️",
            font=title_font,
            bg="#fffaf0",
            fg="#b33a3a",
        ).pack(pady=(14, 2))
        tk.Label(
            root,
            text="이기면 엄마랑, 지면 아빠랑 자는 거야! 💪",
            font=small,
            bg="#fffaf0",
            fg="#555",
        ).pack()

        self.phase_var = tk.StringVar()
        tk.Label(
            root, textvariable=self.phase_var, font=mid, bg="#fffaf0", fg="#2a6"
        ).pack(pady=(8, 2))

        # Last-throw display: me on the left, computer on the right.
        frame = tk.Frame(root, bg="#fffaf0")
        frame.pack(pady=6)
        self.user_emoji_var = tk.StringVar(value="❔")
        self.cpu_emoji_var = tk.StringVar(value="❔")
        tk.Label(frame, text="나", font=big, bg="#fffaf0").grid(row=0, column=0, padx=40)
        tk.Label(frame, text="VS", font=big, bg="#fffaf0", fg="#c33").grid(
            row=0, column=1, rowspan=2
        )
        tk.Label(frame, text="컴퓨터", font=big, bg="#fffaf0").grid(
            row=0, column=2, padx=40
        )
        tk.Label(
            frame, textvariable=self.user_emoji_var, font=huge_emoji, bg="#fffaf0"
        ).grid(row=1, column=0)
        tk.Label(
            frame, textvariable=self.cpu_emoji_var, font=huge_emoji, bg="#fffaf0"
        ).grid(row=1, column=2)

        # Move buttons.
        btns = tk.Frame(root, bg="#fffaf0")
        btns.pack(pady=8)
        self.buttons: dict[str, tk.Button] = {}
        for i, move in enumerate(MOVES):
            b = tk.Button(
                btns,
                text=f"{EMOJI[move]}\n{KOREAN[move]}",
                font=big,
                width=7,
                height=3,
                bg="#ffe8a3",
                activebackground="#ffd670",
                command=lambda m=move: self._play(m),
            )
            b.grid(row=0, column=i, padx=8)
            self.buttons[move] = b

        self.result_var = tk.StringVar()
        tk.Label(
            root,
            textvariable=self.result_var,
            font=mid,
            wraplength=520,
            justify="center",
            bg="#fffaf0",
        ).pack(pady=10)

        self.reset_btn = tk.Button(
            root,
            text="🔄 다시하기",
            font=mid,
            bg="#b3e5fc",
            activebackground="#81d4fa",
            command=self._reset,
            state="disabled",
        )
        self.reset_btn.pack(pady=4)

        self._reset()

    # --- game logic -------------------------------------------------

    def _reset(self) -> None:
        # Close any lingering cutscene from a previous match.
        if self._scene is not None:
            try:
                self._scene._close()
            except Exception:
                pass
            self._scene = None

        self.attacker = None
        self.game_over = False
        self._revealing = False
        self.phase_var.set("1단계: 가위바위보! (공격자 정하기)")
        self.result_var.set("아래에서 하나를 골라봐! ✊  ✌  ✋")
        self.user_emoji_var.set("❔")
        self.cpu_emoji_var.set("❔")
        self.reset_btn.config(state="disabled")
        for b in self.buttons.values():
            b.config(state="normal")

    def _play(self, user_move: str) -> None:
        if self.game_over or self._revealing:
            return
        self._revealing = True
        for b in self.buttons.values():
            b.config(state="disabled")

        cpu_move = random.choice(MOVES)
        # Show the user's choice immediately; hide CPU until the reveal.
        self.user_emoji_var.set(EMOJI[user_move])
        self.cpu_emoji_var.set("❔")
        _play_sound(SOUND_STEM[user_move])

        self.root.after(REVEAL_DELAY_MS, lambda: self._reveal(user_move, cpu_move))

    def _reveal(self, user_move: str, cpu_move: str) -> None:
        self.cpu_emoji_var.set(EMOJI[cpu_move])
        _play_sound(SOUND_STEM[cpu_move])
        self._revealing = False
        if not self.game_over:
            for b in self.buttons.values():
                b.config(state="normal")
        self._resolve(user_move, cpu_move)

    def _resolve(self, user_move: str, cpu_move: str) -> None:
        if self.attacker is None:
            # Phase 1: standard RPS to decide the attacker.
            if user_move == cpu_move:
                self.result_var.set(
                    f"비겼다! 둘 다 {KOREAN[user_move]} 😅  다시 해봐!"
                )
                return
            winner = "user" if BEATS[user_move] == cpu_move else "cpu"
            self.attacker = winner
            who = "내가" if winner == "user" else "컴퓨터가"
            self.phase_var.set("2단계: 묵! 찌! 빠! (같은 걸 내면 공격자 승)")
            self.result_var.set(
                f"🔥 {who} 공격자!  이제 같은 걸 내면 {who} 이겨!"
            )
            return

        # Phase 2: muk-chi-ba.
        if user_move == cpu_move:
            # Same throw -> current attacker wins the match.
            self._finish(self.attacker)
            return
        new_attacker = "user" if BEATS[user_move] == cpu_move else "cpu"
        self.attacker = new_attacker
        who = "내가" if new_attacker == "user" else "컴퓨터가"
        self.result_var.set(f"⚔️ {who} 공격자로 바뀌었어! 계속 간다!")

    def _finish(self, winner: str) -> None:
        self.game_over = True
        for b in self.buttons.values():
            b.config(state="disabled")
        self.reset_btn.config(state="normal")
        if winner == "user":
            self.phase_var.set("🎉 내가 이겼다! 🎉")
            self.result_var.set(
                "와~ 우승!! 🏆\n캠핑에서 엄마랑 같이 자는 거야! 💕🏕️"
            )
            self.root.after(700, self._open_win_scene)
        else:
            self.phase_var.set("😄 컴퓨터 승!")
            self.result_var.set(
                "아이고~ 아쉽다! 😂\n캠핑에서 아빠랑 같이 자는 거야! 🏕️👨"
            )
            self.root.after(700, self._open_lose_scene)

    def _open_win_scene(self) -> None:
        self._scene = WinScene(self.root)

    def _open_lose_scene(self) -> None:
        self._scene = LoseScene(self.root)


def main() -> None:
    _ensure_sounds()
    root = tk.Tk()
    MukChiBaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
