#!/usr/bin/env bash
set -euo pipefail
cat > train.py <<'PY'
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

X, y = load_iris(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)
print("accuracy", RandomForestClassifier().fit(X_train, y_train).score(X_test, y_test))
PY
