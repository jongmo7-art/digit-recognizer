# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A two-file handwritten-digit recognizer: an MNIST-trained scikit-learn `MLPClassifier` plus a Tkinter canvas that predicts what the user draws. Windows-first (see `run.bat`).

## Commands

```bash
# Train the classifier (downloads MNIST the first time, ~15s on CPU, writes mnist_mlp.joblib)
python train_model.py

# Launch the drawing GUI (requires mnist_mlp.joblib to exist)
python digit_app.py
```

On Windows, `run.bat` is the double-clickable entrypoint: it trains if the model file is missing, then launches the GUI.

There is no test suite, linter config, or build step.

## Environment notes

- The installed Python on this machine is `C:\Users\jongm\AppData\Local\Programs\Python\Python312\python.exe` and is **not on `PATH`**. `run.bat` hardcodes this path; invoke Python through that path (or via `run.bat`) from tooling.
- `pandas` is intentionally not installed. `train_model.py` passes `parser="liac-arff"` to `fetch_openml` — do not change that to `"auto"` without also adding pandas as a dependency.
- `mnist_mlp.joblib` (~1.7 MB) is gitignored. It is not a source artifact; regenerate with `train_model.py` rather than committing it.

## Architecture

The non-obvious piece is the inference-time preprocessing in `digit_app.py` (`DigitApp._preprocess`). The canvas is drawn at 280×280 for smooth strokes but MNIST inputs are 28×28, and MNIST digits are centered by **pixel center-of-mass** inside a 28×28 frame with the digit fitting in a 20×20 box. `_preprocess` reproduces that: crop to the drawing's bounding box → resize to fit a 20×20 box preserving aspect ratio → paste onto a black 28×28 canvas at an offset that places the center-of-mass at (14, 14). A naive "resize the whole 280×280 canvas to 28×28" shortcut would shift the train/inference distributions and noticeably hurt accuracy, so preserve this flow when editing.

The drawing state is held twice in parallel: the Tk `Canvas` widget for display and a PIL `Image` of the same size for pixel access. Strokes are mirrored into both in `_on_drag`. The PIL image — not the widget — is what `_preprocess` reads.

## Conventions

All code comments, strings, and identifiers in this repo are in English, even when the user converses in Korean. Keep that style when editing.
