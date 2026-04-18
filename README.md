# Handwritten Digit Recognizer

A small Tkinter app that recognizes a digit (0-9) you draw with the mouse.
The classifier is a scikit-learn `MLPClassifier` trained on MNIST.

## Requirements

- Python 3.10+
- `pip install numpy scikit-learn pillow joblib`

## Usage

```bash
# 1) Train once (downloads MNIST, ~15s on CPU, writes mnist_mlp.joblib)
python train_model.py

# 2) Launch the drawing GUI
python digit_app.py
```

Draw a digit in the black canvas and click **Predict**. **Clear** resets
the canvas.

## Files

- `train_model.py` - downloads MNIST, trains an MLP (128, 64), saves the model
- `digit_app.py` - Tkinter canvas; crops, centers, and resizes the drawing
  to 28x28 before feeding it to the model
