"""Omok (오목 / Gomoku) game for two human players on one machine.

Features:
  - 15x15 board; Black plays first; first to 5-in-a-row (any direction) wins.
  - A realistic wooden "딱" click is synthesized once to sounds/clack.wav
    and played whenever a stone is placed.
  - End-of-game cutscenes (separate Tk Toplevel windows):
      Black wins → 경떡이 does a hula dance and opens her arms for a
                   hug while a cheerful ukulele-style BGM loops.
      White wins → Dad charges in from the right, grabs 경떡이, and
                   drags her into the tent while she flails and cries.
                   A slow chromatic-descent BGM plays underneath.
    Only one cutscene runs per game (the one that matches the winner).

All audio (click + both BGMs) is generated programmatically with the
stdlib `wave` module on first run and cached under sounds/.
"""

from __future__ import annotations

import array
import math
import random
import tkinter as tk
import wave
import winsound
from pathlib import Path
from tkinter import font as tkfont

# --- constants ------------------------------------------------------

BOARD_SIZE = 15
EMPTY, BLACK, WHITE = 0, 1, 2
CELL = 42  # pixels between adjacent intersections
MARGIN = 30  # pixels from canvas edge to outermost line
BOARD_PIXELS = MARGIN * 2 + CELL * (BOARD_SIZE - 1)  # canvas width/height
STONE_RADIUS = CELL // 2 - 3
BOARD_WOOD = "#e6b877"  # wooden goban tan
LINE_COLOR = "#4a2e12"

STONE_LABEL = {BLACK: "흑돌", WHITE: "백돌"}
STONE_GLYPH = {BLACK: "⚫", WHITE: "⚪"}

SOUNDS_DIR = Path(__file__).with_name("sounds")
CLACK_PATH = SOUNDS_DIR / "clack.wav"
HAPPY_BGM_PATH = SOUNDS_DIR / "hula_bgm.wav"
CAUGHT_BGM_PATH = SOUNDS_DIR / "caught_bgm.wav"

# --- audio synthesis ------------------------------------------------


def _write_wav(path: Path, samples, sr: int = 22050) -> None:
    """Write a mono 16-bit PCM WAV from an iterable of floats in [-1, 1]."""
    buf = array.array(
        "h", (int(max(-1.0, min(1.0, s)) * 32000) for s in samples)
    )
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(buf.tobytes())


def _make_clack(path: Path) -> None:
    """Short wooden impact: damped high-frequency mix + noise transient."""
    sr = 22050
    dur = 0.07
    n = int(sr * dur)
    out = []
    for i in range(n):
        t = i / sr
        env = math.exp(-t * 90)
        s = (
            0.5 * math.sin(2 * math.pi * 1400 * t)
            + 0.3 * math.sin(2 * math.pi * 2100 * t)
            + 0.25 * math.sin(2 * math.pi * 3200 * t)
            + 0.4 * (random.random() * 2 - 1)
        )
        out.append(s * env * 0.9)
    _write_wav(path, out, sr)


_NOTE_SEMI = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10,
    "B": 11,
}


def _freq(note: str) -> float:
    """Convert scientific pitch name like 'C5' or 'F#4' to Hz."""
    letter = note[:-1]
    octave = int(note[-1])
    midi = 12 * (octave + 1) + _NOTE_SEMI[letter]
    return 440.0 * 2 ** ((midi - 69) / 12)


def _render_melody(
    notes, tempo_bpm: float, path: Path, voice: str = "pluck", sr: int = 22050
) -> None:
    """Render (note_or_None, beats) pairs to a mono WAV.

    voice='pluck' → quick-attack exponential decay (ukulele-ish).
    voice='sustain' → slow attack / long hold (lullaby voice).
    """
    beat_s = 60.0 / tempo_bpm
    out: list[float] = []
    for name, beats in notes:
        dur_s = beats * beat_s
        n = int(sr * dur_s)
        if name is None:
            out.extend([0.0] * n)
            continue
        f = _freq(name)
        for i in range(n):
            t = i / sr
            if voice == "pluck":
                if t < 0.008:
                    env = t / 0.008
                else:
                    env = math.exp(-(t - 0.008) * 2.6)
            else:  # sustain
                attack, release = 0.08, 0.18
                if t < attack:
                    env = t / attack
                elif t > dur_s - release:
                    env = max(0.0, (dur_s - t) / release)
                else:
                    env = 1.0
            s = (
                0.6 * math.sin(2 * math.pi * f * t)
                + 0.18 * math.sin(2 * math.pi * 2 * f * t)
                + 0.08 * math.sin(2 * math.pi * 3 * f * t)
            )
            out.append(s * env * 0.35)
    _write_wav(path, out, sr)


def _make_happy_bgm(path: Path) -> None:
    """Upbeat C-major ukulele arpeggio loop (~8.7 s)."""
    notes = [
        ("C5", 0.5), ("E5", 0.5), ("G5", 0.5), ("E5", 0.5),
        ("F5", 0.5), ("A5", 0.5), ("G5", 0.5), ("E5", 0.5),
        ("D5", 0.5), ("F5", 0.5), ("A5", 0.5), ("F5", 0.5),
        ("E5", 0.5), ("G5", 0.5), ("C5", 1.0), ("G4", 0.5),
    ]
    _render_melody(notes, tempo_bpm=108, path=path, voice="pluck")


def _make_caught_bgm(path: Path) -> None:
    """Chromatic-descent A-minor 'being dragged away' theme (~13 s).

    Uses half-step slides (G#↔A, C#4) to convey reluctance / a slow
    march to bedtime. Plodding 70 bpm matches dad's walking pace.
    """
    notes = [
        ("C5", 1.0), ("B4", 1.0), ("A4", 2.0),         # opening sigh
        ("G#4", 1.0), ("A4", 1.0), ("G4", 2.0),         # chromatic wobble
        ("F4", 1.0), ("E4", 1.0), ("F4", 1.0), ("E4", 1.0),  # back-and-forth (resist)
        ("D4", 2.0), ("E4", 1.0), ("A3", 1.0),           # resolution
    ]
    _render_melody(notes, tempo_bpm=70, path=path, voice="sustain")


def _ensure_audio() -> None:
    SOUNDS_DIR.mkdir(exist_ok=True)
    if not CLACK_PATH.exists():
        _make_clack(CLACK_PATH)
    if not HAPPY_BGM_PATH.exists():
        _make_happy_bgm(HAPPY_BGM_PATH)
    if not CAUGHT_BGM_PATH.exists():
        _make_caught_bgm(CAUGHT_BGM_PATH)


def _play_clack() -> None:
    if CLACK_PATH.exists():
        winsound.PlaySound(
            str(CLACK_PATH), winsound.SND_FILENAME | winsound.SND_ASYNC
        )


def _start_bgm(path: Path) -> None:
    if path.exists():
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP,
        )


def _stop_bgm() -> None:
    winsound.PlaySound(None, winsound.SND_PURGE)


# --- cutscenes ------------------------------------------------------


SKIN = "#ffd7a0"
OUTLINE = "#6d4c2a"


class _SceneBase(tk.Toplevel):
    """Shared frame-driver + BGM handling for the cutscene windows."""

    W = 560
    H = 440
    TICK_MS = 60
    BGM_PATH: Path | None = None

    def __init__(self, parent: tk.Misc, title: str, bg: str, on_close=None) -> None:
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
        self._on_close = on_close
        self.protocol("WM_DELETE_WINDOW", self._close)
        if self.BGM_PATH is not None:
            _start_bgm(self.BGM_PATH)
        self.after(self.TICK_MS, self._loop)

    def _loop(self) -> None:
        if self.stopped:
            return
        try:
            self._tick()
        except tk.TclError:
            return
        self.frame += 1
        self.after(self.TICK_MS, self._loop)

    def _tick(self) -> None:
        raise NotImplementedError

    def _close(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        _stop_bgm()
        try:
            self.destroy()
        except tk.TclError:
            pass
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:
                pass


class HulaWinScene(_SceneBase):
    """경떡이 dances hula and periodically opens arms for a hug."""

    BGM_PATH = HAPPY_BGM_PATH

    def __init__(self, parent: tk.Misc, winner_label: str, on_close=None) -> None:
        super().__init__(
            parent, f"🌺 경떡이 훌라 댄스 — {winner_label} 승리!", "#fff1d6", on_close
        )
        self.winner_label = winner_label

        # Tropical background: sun and palm silhouettes.
        self.canvas.create_oval(
            self.W - 120, 30, self.W - 40, 110, fill="#ffd54f", outline=""
        )
        # Two simple palm trees (trunk + fronds) at the corners.
        for base_x in (40, self.W - 40):
            self.canvas.create_line(
                base_x, 330, base_x, 230, fill="#5d4037", width=6
            )
            for ang in (-60, -25, 25, 60):
                rad = math.radians(ang)
                self.canvas.create_line(
                    base_x,
                    230,
                    base_x + math.sin(rad) * 55,
                    230 - math.cos(rad) * 35,
                    fill="#2e7d32",
                    width=5,
                    capstyle="round",
                )
        # Sand strip.
        self.canvas.create_rectangle(
            0, 350, self.W, self.H, fill="#f6d28b", outline=""
        )
        # Little waves on the sand.
        for x in range(20, self.W, 40):
            self.canvas.create_arc(
                x - 14, 345, x + 14, 360, start=0, extent=180,
                style="arc", outline="#fff", width=2,
            )

        self.canvas.create_text(
            self.W // 2, 30,
            text=f"🏆 {winner_label} 승리! 🏆",
            font=("Malgun Gothic", 22, "bold"),
            fill="#c2185b",
        )
        self.canvas.create_text(
            self.W // 2, 62,
            text="경떡이가 훌라춤으로 축하하고 안아줘요! 🌺",
            font=("Malgun Gothic", 13),
            fill="#6a1b9a",
        )

        # Character parts — all coords recomputed per tick.
        self.cx = self.W // 2
        self.cy = 260
        self.name_tag = self.canvas.create_text(
            0, 0, text="경떡이", font=("Malgun Gothic", 12, "bold"), fill="#d81b60"
        )
        # Flower crown: 5 pink dots above the head.
        self.crown = [
            self.canvas.create_oval(0, 0, 0, 0, fill="#ec407a", outline="#880e4f")
            for _ in range(5)
        ]
        self.head = self.canvas.create_oval(
            0, 0, 0, 0, fill=SKIN, outline=OUTLINE, width=2
        )
        self.body = self.canvas.create_oval(
            0, 0, 0, 0, fill="#ffab91", outline=OUTLINE, width=2
        )
        # Lei: 8 small circles around the neckline.
        lei_colors = ["#e91e63", "#ffeb3b", "#4fc3f7", "#81c784",
                      "#ba68c8", "#ff7043", "#f06292", "#aed581"]
        self.lei = [
            self.canvas.create_oval(0, 0, 0, 0, fill=c, outline="")
            for c in lei_colors
        ]
        # Grass skirt: 9 vertical strands.
        self.skirt = [
            self.canvas.create_line(0, 0, 0, 0, fill="#66bb6a", width=3)
            for _ in range(9)
        ]
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
        # Big hug-heart that pulses during the "안아주기" beat.
        self.hug_heart = self.canvas.create_text(
            0, 0, text="💖", font=("Segoe UI Emoji", 28), fill="#c62828"
        )
        self.bubble = self.canvas.create_text(
            0, 0, text="안아줄게~! 🤗", font=("Malgun Gothic", 14, "bold"),
            fill="#ad1457",
        )

        # Rising hearts around her.
        self.hearts: list[list] = []

    def _tick(self) -> None:
        t = self.frame
        # Hip sway side to side (smooth).
        sway = math.sin(t * 0.22) * 14
        # Hula arm wave: opposite sides, vertical swing.
        arm_a = math.sin(t * 0.28)
        arm_b = math.sin(t * 0.28 + math.pi)

        # "Hug burst" every ~3.5s: lasts 1s.
        phase = (t * self.TICK_MS) % 3500
        hug_mode = phase < 1000

        cx = self.cx + sway
        cy = self.cy

        # Name above head.
        self.canvas.coords(self.name_tag, cx, cy - 115)
        # Head.
        self.canvas.coords(self.head, cx - 30, cy - 105, cx + 30, cy - 45)
        # Flower crown: 5 dots in a gentle arc above the head.
        for i, cid in enumerate(self.crown):
            frac = (i - 2) / 2  # -1..1
            fx = cx + frac * 24
            fy = cy - 105 + abs(frac) * 6
            self.canvas.coords(cid, fx - 6, fy - 6, fx + 6, fy + 6)
        # Body.
        self.canvas.coords(self.body, cx - 25, cy - 50, cx + 25, cy + 15)
        # Lei around neckline: 8 dots in a semicircle at the top of the body.
        for i, cid in enumerate(self.lei):
            ang = math.pi * (i / 7) + math.pi  # 180..360 deg → bottom arc
            lx = cx + math.cos(ang) * 26
            ly = cy - 48 + math.sin(ang) * 10
            self.canvas.coords(cid, lx - 5, ly - 5, lx + 5, ly + 5)
        # Grass skirt: vertical strands from waist (cy+10) down to cy+50.
        for i, sid in enumerate(self.skirt):
            sx = cx - 24 + i * 6
            length = 36 + (i % 2) * 4
            # Slight sway in skirt direction.
            sway_x = math.sin(t * 0.22 + i * 0.4) * 4
            self.canvas.coords(sid, sx, cy + 10, sx + sway_x, cy + 10 + length)
        # Arms: hug mode = both forward/out, else flowing hula.
        sh_l = (cx - 25, cy - 45)
        sh_r = (cx + 25, cy - 45)
        if hug_mode:
            # Open arms wide for a hug, slight up tilt.
            self.canvas.coords(
                self.left_arm, *sh_l, cx - 70, cy - 60
            )
            self.canvas.coords(
                self.right_arm, *sh_r, cx + 70, cy - 60
            )
        else:
            self.canvas.coords(
                self.left_arm, *sh_l, cx - 60, cy - 45 - arm_a * 35
            )
            self.canvas.coords(
                self.right_arm, *sh_r, cx + 60, cy - 45 - arm_b * 35
            )
        # Legs: slight knee bend with sway.
        self.canvas.coords(
            self.left_leg, cx - 12, cy + 50, cx - 16 + sway * 0.3, cy + 92
        )
        self.canvas.coords(
            self.right_leg, cx + 12, cy + 50, cx + 16 + sway * 0.3, cy + 92
        )
        # Face.
        self.canvas.coords(self.left_eye, cx - 13, cy - 82, cx - 7, cy - 76)
        self.canvas.coords(self.right_eye, cx + 7, cy - 82, cx + 13, cy - 76)
        self.canvas.coords(self.mouth, cx - 13, cy - 75, cx + 13, cy - 58)
        # Hug heart: big pulsing heart in front of chest during hug_mode, small otherwise.
        if hug_mode:
            scale = 28 + int(math.sin(t * 0.6) * 6)
            self.canvas.itemconfig(
                self.hug_heart, font=("Segoe UI Emoji", scale), state="normal"
            )
            self.canvas.coords(self.hug_heart, cx, cy - 10)
            self.canvas.itemconfig(self.bubble, text="꼬옥~ 안아줄게! 🤗💖")
        else:
            self.canvas.itemconfig(
                self.hug_heart, font=("Segoe UI Emoji", 16), state="normal"
            )
            self.canvas.coords(self.hug_heart, cx, cy - 15)
            self.canvas.itemconfig(self.bubble, text="알로하~ 훌라훌라 🌺")
        self.canvas.coords(self.bubble, cx, cy - 135)

        # Floating hearts: spawn occasionally, rise and fade.
        if t % 6 == 0:
            hx = random.uniform(80, self.W - 80)
            hid = self.canvas.create_text(
                hx, self.H - 40, text="💗", font=("Segoe UI Emoji", 16)
            )
            self.hearts.append([hid, hx, self.H - 40])
        alive: list[list] = []
        for h in self.hearts:
            hid, hx, hy = h
            hy -= 2.5
            hx += math.sin((hy + hid) * 0.05) * 1.5
            h[1], h[2] = hx, hy
            self.canvas.coords(hid, hx, hy)
            if hy < 80:
                self.canvas.delete(hid)
            else:
                alive.append(h)
        self.hearts = alive


class DadCatchScene(_SceneBase):
    """Dad charges in, grabs 경떡이, and drags her crying into the tent."""

    BGM_PATH = CAUGHT_BGM_PATH

    def __init__(self, parent: tk.Misc, loser_label: str, on_close=None) -> None:
        super().__init__(
            parent, f"😭 경떡이 잡혔다 — {loser_label} 승리!", "#0d1b2a", on_close
        )

        ground_y = 340
        self.ground_y = ground_y
        self.canvas.create_rectangle(
            0, ground_y, self.W, self.H, fill="#2e7d32", outline=""
        )
        # Moon + stars.
        self.canvas.create_oval(
            self.W - 90, 40, self.W - 30, 100, fill="#fff59d", outline=""
        )
        for x, y in [(60, 70), (140, 40), (220, 90), (310, 60),
                     (400, 110), (470, 180), (90, 160), (370, 40)]:
            self.canvas.create_text(
                x, y, text="✦", fill="#fff59d", font=("Segoe UI Symbol", 12)
            )
        # Tent on the left.
        self.tent_cx = 95
        tent_base_w = 140
        tent_h = 105
        self.canvas.create_polygon(
            self.tent_cx - tent_base_w // 2, ground_y,
            self.tent_cx + tent_base_w // 2, ground_y,
            self.tent_cx, ground_y - tent_h,
            fill="#8d6e63", outline="#4e342e", width=2,
        )
        self.canvas.create_line(
            self.tent_cx, ground_y, self.tent_cx, ground_y - tent_h,
            fill="#4e342e", width=2,
        )
        self.canvas.create_polygon(
            self.tent_cx - 15, ground_y,
            self.tent_cx + 15, ground_y,
            self.tent_cx, ground_y - 60,
            fill="#1b0f0a", outline="",
        )

        self.canvas.create_text(
            self.W // 2, 30,
            text=f"😭 {loser_label} 승리!  경떡이가 아빠한테 잡혔다!",
            font=("Malgun Gothic", 14, "bold"),
            fill="#ffcdd2",
        )

        # Kid (경떡이) starts roughly center-right; she doesn't move until caught.
        self.kx = 330.0
        self.ky = float(ground_y - 60)
        # State flag: True once dad reaches the kid.
        self.caught = False

        self.kid_name = self.canvas.create_text(
            0, 0, text="경떡이", font=("Malgun Gothic", 11, "bold"), fill="#ffe0b2"
        )
        self.kid_head = self.canvas.create_oval(
            0, 0, 0, 0, fill=SKIN, outline=OUTLINE, width=2
        )
        self.kid_body = self.canvas.create_oval(
            0, 0, 0, 0, fill="#ff7043", outline=OUTLINE, width=2
        )
        self.kid_left_arm = self.canvas.create_line(0, 0, 0, 0, width=4, fill=OUTLINE)
        self.kid_right_arm = self.canvas.create_line(0, 0, 0, 0, width=4, fill=OUTLINE)
        self.kid_left_leg = self.canvas.create_line(0, 0, 0, 0, width=4, fill=OUTLINE)
        self.kid_right_leg = self.canvas.create_line(0, 0, 0, 0, width=4, fill=OUTLINE)
        self.kid_mouth = self.canvas.create_arc(
            0, 0, 0, 0, style="arc", start=20, extent=140, width=2, outline=OUTLINE
        )
        self.kid_left_eye = self.canvas.create_line(0, 0, 0, 0, width=2, fill="#222")
        self.kid_right_eye = self.canvas.create_line(0, 0, 0, 0, width=2, fill="#222")
        self.bubble = self.canvas.create_text(
            0, 0, text="어?! 아빠...?", font=("Malgun Gothic", 14, "bold"),
            fill="#ef9a9a",
        )
        # Tears stored as [canvas_id, x, y, vx, vy]; gravity applied per tick.
        self.tears: list[list] = []

        # Dad — enters from the right edge at a brisk walking pace.
        self.dx = self.W + 40.0
        self.dy = float(ground_y - 72)
        self.dad_name = self.canvas.create_text(
            0, 0, text="아빠", font=("Malgun Gothic", 11, "bold"), fill="#b3e5fc"
        )
        self.dad_head = self.canvas.create_oval(
            0, 0, 0, 0, fill=SKIN, outline="#3e2723", width=2
        )
        self.dad_body = self.canvas.create_oval(
            0, 0, 0, 0, fill="#455a64", outline="#263238", width=2
        )
        self.dad_left_arm = self.canvas.create_line(0, 0, 0, 0, width=4, fill="#263238")
        self.dad_right_arm = self.canvas.create_line(0, 0, 0, 0, width=4, fill="#263238")
        self.dad_left_leg = self.canvas.create_line(0, 0, 0, 0, width=4, fill="#263238")
        self.dad_right_leg = self.canvas.create_line(0, 0, 0, 0, width=4, fill="#263238")
        self.dad_mouth = self.canvas.create_line(0, 0, 0, 0, width=2, fill="#263238")
        self.dad_eye_l = self.canvas.create_oval(0, 0, 0, 0, fill="#222")
        self.dad_eye_r = self.canvas.create_oval(0, 0, 0, 0, fill="#222")

        self.hidden = False
        self.zzz_id: int | None = None

    def _tick(self) -> None:
        t = self.frame

        # --- movement timeline --------------------------------------------
        if not self.caught:
            # Dad charges in from the right until he's next to the kid.
            if self.dx > self.kx + 60:
                self.dx -= 5.0
            else:
                self.caught = True
                self.canvas.itemconfig(self.bubble, text="싫어~~!! ㅠㅠ")
        else:
            # Dad drags kid leftward at a plodding pace (kid resists).
            if self.dx > self.tent_cx - 10:
                self.dx -= 2.6
                self.kx = self.dx + 55  # kid always trails behind dad
            # Progressive bubble changes as they approach the tent.
            if t == 60:
                self.canvas.itemconfig(self.bubble, text="가기 싫어~!! 😭")
            elif t == 95:
                self.canvas.itemconfig(self.bubble, text="으앙앙... ㅠㅠ")

        # Kid bobs gently when standing; jerks harder when being dragged.
        kid_bob = (math.sin(t * 0.8) * 5.0) if self.caught else (math.sin(t * 0.2) * 2.0)

        # --- kid drawing --------------------------------------------------
        kx, ky = self.kx, self.ky + kid_bob
        self.canvas.coords(self.kid_name, kx, ky - 75)
        self.canvas.coords(self.kid_head, kx - 24, ky - 60, kx + 24, ky - 12)
        self.canvas.coords(self.kid_body, kx - 20, ky - 12, kx + 20, ky + 30)

        if self.caught:
            # Kid's LEFT arm stretches forward toward dad's grip point.
            grip_x = self.dx + 30
            grip_y = self.dy - 5
            self.canvas.coords(self.kid_left_arm, kx - 20, ky - 5, grip_x, grip_y)
            # Right arm flails freely.
            flail = math.sin(t * 0.6) * 18
            self.canvas.coords(
                self.kid_right_arm, kx + 20, ky - 5, kx + 38, ky - 22 + flail
            )
            # Legs scramble/kick — asymmetric alternating motion.
            leg_a = math.sin(t * 0.75) * 12
            leg_b = math.cos(t * 0.75) * 12
            self.canvas.coords(
                self.kid_left_leg, kx - 10, ky + 30, kx - 10 + leg_a, ky + 58 - abs(leg_a) * 0.4
            )
            self.canvas.coords(
                self.kid_right_leg, kx + 10, ky + 30, kx + 10 + leg_b, ky + 58 - abs(leg_b) * 0.4
            )
        else:
            # Standing normally, arms down.
            self.canvas.coords(self.kid_left_arm, kx - 20, ky - 5, kx - 32, ky + 22)
            self.canvas.coords(self.kid_right_arm, kx + 20, ky - 5, kx + 32, ky + 22)
            self.canvas.coords(self.kid_left_leg, kx - 10, ky + 30, kx - 10, ky + 60)
            self.canvas.coords(self.kid_right_leg, kx + 10, ky + 30, kx + 10, ky + 60)

        # Crying face (frown + squinted eyes) — shown from the start; more
        # visible once dragged.
        self.canvas.coords(self.kid_mouth, kx - 12, ky - 18, kx + 12, ky - 4)
        self.canvas.coords(self.kid_left_eye, kx - 15, ky - 40, kx - 7, ky - 36)
        self.canvas.coords(self.kid_right_eye, kx + 7, ky - 40, kx + 15, ky - 36)

        # Tears: fly sideways + gravity once she's being dragged; drip straight
        # down if she's just standing.
        if self.caught and t % 3 == 0:
            for side in (-12, 12):
                tid = self.canvas.create_oval(
                    kx + side - 3, ky - 32, kx + side + 3, ky - 26,
                    fill="#4fc3f7", outline="",
                )
                # Dragged leftward means tears fly rightward behind her.
                self.tears.append([tid, float(kx + side), float(ky - 32), 4.0, -2.0])
        elif not self.caught and t % 8 == 0:
            for side in (-12, 12):
                tid = self.canvas.create_oval(
                    kx + side - 3, ky - 32, kx + side + 3, ky - 26,
                    fill="#4fc3f7", outline="",
                )
                self.tears.append([tid, float(kx + side), float(ky - 32), 0.0, 3.0])

        alive: list[list] = []
        for tear in self.tears:
            tid, tx, ty, vx, vy = tear
            tx += vx
            ty += vy
            vy += 0.45  # gravity
            tear[1], tear[2], tear[4] = tx, ty, vy
            self.canvas.coords(tid, tx - 3, ty, tx + 3, ty + 6)
            if ty > self.ground_y or tx < -10 or tx > self.W + 10:
                self.canvas.delete(tid)
            else:
                alive.append(tear)
        self.tears = alive

        self.canvas.coords(self.bubble, kx, ky - 95)

        # --- dad drawing --------------------------------------------------
        dx, dy = self.dx, self.dy
        self.canvas.coords(self.dad_name, dx, dy - 85)
        self.canvas.coords(self.dad_head, dx - 28, dy - 70, dx + 28, dy - 14)
        self.canvas.coords(self.dad_body, dx - 24, dy - 14, dx + 24, dy + 38)
        # Walking leg swing (while moving).
        leg_swing = math.sin(t * 0.45 + math.pi) * 10
        self.canvas.coords(
            self.dad_left_leg, dx - 10, dy + 38, dx - 10 + leg_swing, dy + 75
        )
        self.canvas.coords(
            self.dad_right_leg, dx + 10, dy + 38, dx + 10 - leg_swing, dy + 75
        )
        if self.caught:
            # Right arm reaches back (to the right) to grip the kid's hand.
            self.canvas.coords(self.dad_right_arm, dx + 24, dy - 5, dx + 50, dy - 2)
            # Left arm points forward-ish (toward the tent on the left).
            self.canvas.coords(self.dad_left_arm, dx - 24, dy - 5, dx - 40, dy + 5)
        else:
            # Both arms swinging naturally during the approach.
            self.canvas.coords(self.dad_left_arm, dx - 24, dy - 5, dx - 34, dy + 18)
            self.canvas.coords(self.dad_right_arm, dx + 24, dy - 5, dx + 34, dy + 18)
        # Stern mouth (flat horizontal line) and eyes.
        self.canvas.coords(self.dad_mouth, dx - 8, dy - 26, dx + 8, dy - 26)
        self.canvas.coords(self.dad_eye_l, dx - 14, dy - 45, dx - 10, dy - 41)
        self.canvas.coords(self.dad_eye_r, dx + 10, dy - 45, dx + 14, dy - 41)

        # --- tent entry ---------------------------------------------------
        if not self.hidden and self.dx <= self.tent_cx - 10:
            for item in (
                self.kid_head, self.kid_body, self.kid_left_arm,
                self.kid_right_arm, self.kid_left_leg, self.kid_right_leg,
                self.kid_mouth, self.kid_left_eye, self.kid_right_eye,
                self.kid_name, self.dad_head, self.dad_body, self.dad_left_arm,
                self.dad_right_arm, self.dad_left_leg, self.dad_right_leg,
                self.dad_mouth, self.dad_eye_l, self.dad_eye_r, self.dad_name,
                self.bubble,
            ):
                self.canvas.itemconfig(item, state="hidden")
            self.zzz_id = self.canvas.create_text(
                self.tent_cx + 40, self.ground_y - 130,
                text="흑흑... 😭",
                font=("Malgun Gothic", 18, "bold"),
                fill="#e1f5fe",
            )
            self.hidden = True

        if self.hidden and self.zzz_id is not None:
            bob = math.sin(t * 0.1) * 3
            self.canvas.coords(
                self.zzz_id, self.tent_cx + 40, self.ground_y - 130 + bob
            )


# --- game logic + main window --------------------------------------


def _check_win(board: list[list[int]], r: int, c: int, color: int) -> bool:
    """Return True if placing `color` at (r,c) made 5+ in a row."""
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        count = 1
        for sign in (1, -1):
            nr, nc = r + dr * sign, c + dc * sign
            while (
                0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE
                and board[nr][nc] == color
            ):
                count += 1
                nr += dr * sign
                nc += dc * sign
        if count >= 5:
            return True
    return False


class OmokApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("오목 — 흑 vs 백 (사람 vs 사람)")
        root.resizable(False, False)
        root.configure(bg="#fffaf0")

        self.board: list[list[int]] = [
            [EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)
        ]
        self.turn: int = BLACK
        self.game_over = False
        # Open cutscene windows so we can close them on reset.
        self._open_scenes: list[_SceneBase] = []

        status_font = tkfont.Font(family="Malgun Gothic", size=14, weight="bold")
        mid = tkfont.Font(family="Malgun Gothic", size=11)

        self.status_var = tk.StringVar()
        tk.Label(
            root, textvariable=self.status_var, font=status_font,
            bg="#fffaf0", fg="#111",
        ).pack(pady=(10, 2))
        tk.Label(
            root,
            text="경떡이는 흑돌(⚫). 5개 먼저 일렬로! 경떡이가 이기면 훌라, 지면 아빠한테 잡혀가요 💪",
            font=("Malgun Gothic", 9),
            bg="#fffaf0", fg="#666",
        ).pack()

        self.canvas = tk.Canvas(
            root, width=BOARD_PIXELS, height=BOARD_PIXELS,
            bg=BOARD_WOOD, highlightthickness=1, highlightbackground="#5d4037",
        )
        self.canvas.pack(padx=10, pady=8)
        self.canvas.bind("<Button-1>", self._on_click)
        self._draw_board()

        self.reset_btn = tk.Button(
            root, text="🔄 다시 시작", font=mid, bg="#b3e5fc",
            activebackground="#81d4fa", command=self._reset,
        )
        self.reset_btn.pack(pady=(2, 10))

        self._update_status()

    # --- board rendering --------------------------------------------

    def _draw_board(self) -> None:
        # Grid.
        for i in range(BOARD_SIZE):
            x = MARGIN + i * CELL
            self.canvas.create_line(
                MARGIN, x, MARGIN + CELL * (BOARD_SIZE - 1), x,
                fill=LINE_COLOR, width=1,
            )
            self.canvas.create_line(
                x, MARGIN, x, MARGIN + CELL * (BOARD_SIZE - 1),
                fill=LINE_COLOR, width=1,
            )
        # Hoshi dots (5 standard positions on a 15x15 board).
        for r, c in [(3, 3), (3, 11), (11, 3), (11, 11), (7, 7)]:
            x = MARGIN + c * CELL
            y = MARGIN + r * CELL
            self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=LINE_COLOR)

    def _draw_stone(self, r: int, c: int, color: int) -> None:
        x = MARGIN + c * CELL
        y = MARGIN + r * CELL
        if color == BLACK:
            fill, outline = "#111", "#111"
        else:
            fill, outline = "#fafafa", "#444"
        self.canvas.create_oval(
            x - STONE_RADIUS, y - STONE_RADIUS,
            x + STONE_RADIUS, y + STONE_RADIUS,
            fill=fill, outline=outline, width=1,
        )
        # Subtle highlight on white stones for visibility.
        if color == WHITE:
            self.canvas.create_oval(
                x - STONE_RADIUS + 4, y - STONE_RADIUS + 4,
                x - 2, y - 2,
                fill="", outline="#ddd",
            )

    def _update_status(self) -> None:
        if self.game_over:
            return
        label = STONE_LABEL[self.turn]
        glyph = STONE_GLYPH[self.turn]
        self.status_var.set(f"{glyph}  {label} 차례")

    # --- interaction ------------------------------------------------

    def _on_click(self, event: tk.Event) -> None:
        if self.game_over:
            return
        # Snap to the nearest intersection.
        c = round((event.x - MARGIN) / CELL)
        r = round((event.y - MARGIN) / CELL)
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            return
        if self.board[r][c] != EMPTY:
            return
        color = self.turn
        self.board[r][c] = color
        self._draw_stone(r, c, color)
        _play_clack()

        if _check_win(self.board, r, c, color):
            self._finish(color)
            return
        if all(self.board[rr][cc] != EMPTY for rr in range(BOARD_SIZE)
               for cc in range(BOARD_SIZE)):
            self._finish(EMPTY)  # draw
            return
        self.turn = WHITE if self.turn == BLACK else BLACK
        self._update_status()

    # --- end of game ------------------------------------------------

    def _finish(self, winner_color: int) -> None:
        self.game_over = True
        if winner_color == EMPTY:
            self.status_var.set("무승부! 다시 시작하려면 🔄 눌러줘")
            return
        winner_label = STONE_LABEL[winner_color]
        # 경떡이 is the black player. Black winning → celebration; black
        # losing → caught by dad. Only one cutscene per game.
        if winner_color == BLACK:
            self.status_var.set(
                f"🏆 {winner_label} 승리!  경떡이가 하와이로 간다 🌺"
            )
            self.root.after(
                600,
                lambda: self._open_scene(HulaWinScene(self.root, winner_label)),
            )
        else:
            self.status_var.set(
                f"😭 {winner_label} 승리!  경떡이는 아빠한테 잡혔다..."
            )
            self.root.after(
                600,
                lambda: self._open_scene(DadCatchScene(self.root, winner_label)),
            )

    def _open_scene(self, scene: _SceneBase) -> None:
        self._open_scenes.append(scene)

    def _reset(self) -> None:
        # Close any open cutscenes and stop BGM.
        for s in list(self._open_scenes):
            try:
                s._close()
            except Exception:
                pass
        self._open_scenes.clear()
        _stop_bgm()

        self.board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.turn = BLACK
        self.game_over = False
        self.canvas.delete("all")
        self._draw_board()
        self._update_status()


def main() -> None:
    _ensure_audio()
    root = tk.Tk()
    OmokApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
