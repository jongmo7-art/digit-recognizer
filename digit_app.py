"""Tkinter GUI for handwritten digit recognition.

Draw a digit in the black canvas, then click "Predict". The model is the
one trained and saved by `train_model.py`.
"""

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import joblib
import numpy as np
from PIL import Image, ImageDraw, ImageOps

MODEL_PATH = Path(__file__).with_name("mnist_mlp.joblib")

# Canvas is drawn at a larger size for a smooth pen, then downsampled to 28x28
# to match the MNIST input the model was trained on.
CANVAS_SIZE = 280
MNIST_SIZE = 28
PEN_RADIUS = 10  # half-thickness of the stroke in canvas pixels


class DigitApp:
    def __init__(self, root: tk.Tk, model) -> None:
        self.root = root
        self.model = model
        root.title("Handwritten Digit Recognizer")
        root.resizable(False, False)

        self.canvas = tk.Canvas(
            root,
            width=CANVAS_SIZE,
            height=CANVAS_SIZE,
            bg="black",
            cursor="crosshair",
            highlightthickness=1,
            highlightbackground="#444",
        )
        self.canvas.grid(row=0, column=0, columnspan=3, padx=10, pady=10)

        # Parallel PIL image mirrors the canvas so we can feed real pixels
        # to the model instead of re-reading the widget.
        self.image = Image.new("L", (CANVAS_SIZE, CANVAS_SIZE), color=0)
        self.draw = ImageDraw.Draw(self.image)

        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Button-1>", self._on_drag)

        tk.Button(root, text="Predict", width=12, command=self._predict).grid(
            row=1, column=0, padx=6, pady=(0, 10)
        )
        tk.Button(root, text="Clear", width=12, command=self._clear).grid(
            row=1, column=1, padx=6, pady=(0, 10)
        )

        self.result_var = tk.StringVar(value="Draw a digit (0-9)")
        tk.Label(
            root, textvariable=self.result_var, font=("Segoe UI", 14, "bold")
        ).grid(row=1, column=2, padx=6, pady=(0, 10), sticky="w")

    def _on_drag(self, event: tk.Event) -> None:
        x, y = event.x, event.y
        r = PEN_RADIUS
        self.canvas.create_oval(
            x - r, y - r, x + r, y + r, fill="white", outline="white"
        )
        self.draw.ellipse([x - r, y - r, x + r, y + r], fill=255)

    def _clear(self) -> None:
        self.canvas.delete("all")
        self.draw.rectangle([0, 0, CANVAS_SIZE, CANVAS_SIZE], fill=0)
        self.result_var.set("Draw a digit (0-9)")

    def _preprocess(self) -> np.ndarray | None:
        """Crop to the digit's bounding box, center it, resize to 28x28.

        MNIST images are centered by center-of-mass inside a 28x28 frame,
        with the digit fitting in a 20x20 box. We approximate that here so
        the inference distribution matches training.
        """
        bbox = self.image.getbbox()
        if bbox is None:
            return None

        digit = self.image.crop(bbox)
        # Fit the digit into a 20x20 box preserving aspect ratio.
        w, h = digit.size
        scale = 20.0 / max(w, h)
        new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
        digit = digit.resize(new_size, Image.LANCZOS)

        # Paste onto a 28x28 canvas centered by pixel mass.
        canvas = Image.new("L", (MNIST_SIZE, MNIST_SIZE), color=0)
        arr = np.asarray(digit, dtype=np.float32)
        total = arr.sum()
        if total <= 0:
            return None
        ys, xs = np.indices(arr.shape)
        cx = (xs * arr).sum() / total
        cy = (ys * arr).sum() / total
        # Target: place center-of-mass at (14, 14).
        off_x = int(round(MNIST_SIZE / 2 - cx))
        off_y = int(round(MNIST_SIZE / 2 - cy))
        paste_x = max(0, min(MNIST_SIZE - new_size[0], off_x))
        paste_y = max(0, min(MNIST_SIZE - new_size[1], off_y))
        canvas.paste(digit, (paste_x, paste_y))

        vec = np.asarray(canvas, dtype=np.float32).reshape(1, -1) / 255.0
        return vec

    def _predict(self) -> None:
        x = self._preprocess()
        if x is None:
            self.result_var.set("Canvas is empty")
            return
        probs = self.model.predict_proba(x)[0]
        pred = int(np.argmax(probs))
        conf = float(probs[pred])
        self.result_var.set(f"Prediction: {pred}  (confidence {conf:.1%})")


def main() -> None:
    if not MODEL_PATH.exists():
        raise SystemExit(
            f"Model file not found: {MODEL_PATH}\n"
            "Train it first with: python train_model.py"
        )
    model = joblib.load(MODEL_PATH)

    root = tk.Tk()
    DigitApp(root, model)
    root.mainloop()


if __name__ == "__main__":
    main()
