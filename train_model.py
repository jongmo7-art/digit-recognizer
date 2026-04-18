"""Train a handwritten-digit classifier on MNIST and save it to disk.

Run once: `python train_model.py`. Produces `mnist_mlp.joblib`.
"""

from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.datasets import fetch_openml
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

MODEL_PATH = Path(__file__).with_name("mnist_mlp.joblib")


def main() -> None:
    print("Downloading MNIST (this may take a minute on first run)...")
    # as_frame=False returns numpy arrays; parser="auto" picks the fastest
    mnist = fetch_openml("mnist_784", version=1, as_frame=False, parser="liac-arff")
    X = mnist.data.astype(np.float32) / 255.0  # scale pixel values to [0, 1]
    y = mnist.target.astype(np.int64)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=10_000, random_state=42, stratify=y
    )

    # A small MLP is plenty for MNIST and trains in under a minute on CPU.
    clf = MLPClassifier(
        hidden_layer_sizes=(128, 64),
        activation="relu",
        solver="adam",
        batch_size=256,
        max_iter=20,
        random_state=42,
        verbose=True,
    )

    print(f"Training on {len(X_train)} samples...")
    start = time.time()
    clf.fit(X_train, y_train)
    elapsed = time.time() - start

    acc = accuracy_score(y_test, clf.predict(X_test))
    print(f"Training time: {elapsed:.1f}s | Test accuracy: {acc:.4f}")

    joblib.dump(clf, MODEL_PATH)
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
