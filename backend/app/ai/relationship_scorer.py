"""
AI/ML Module for Fragment Relationship Scoring

This module provides a lightweight Random Forest classifier for estimating
fragment relationship probabilities. Training data is SYNTHETIC/CONTROLLED
and NOT derived from real forensic evidence. This is a hackathon prototype.

IMPORTANT: No real-world forensic accuracy is claimed.
"""

import json
import random
import numpy as np
from pathlib import Path
from typing import Callable
from dataclasses import dataclass

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# Import Fragment type for type hints
try:
    from app.models.scan import Fragment
except ImportError:
    Fragment = object  # Fallback for type hints


@dataclass
class PairFeatures:
    """Feature vector for a fragment pair."""
    entropy_similarity: float
    size_similarity: float
    byte_stats_similarity: float
    adjacency_bonus: float
    offset_distance: float
    entropy_a: float
    entropy_b: float
    size_a: int
    size_b: int
    same_size_flag: float

    def to_array(self) -> np.ndarray:
        return np.array([
            self.entropy_similarity,
            self.size_similarity,
            self.byte_stats_similarity,
            self.adjacency_bonus,
            self.offset_distance,
            self.entropy_a,
            self.entropy_b,
            float(self.size_a),
            float(self.size_b),
            self.same_size_flag
        ], dtype=np.float32)


class SyntheticDatasetGenerator:
    """
    Generates SYNTHETIC/CONTROLLED training data for the Random Forest.
    
    This is NOT real forensic data. It uses controlled patterns:
    - Positive pairs: adjacent fragments, similar entropy/size, same file
    - Negative pairs: distant fragments, different entropy/size, different files
    """

    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
        random.seed(random_seed)
        np.random.seed(random_seed)

    def _generate_related_pair(self) -> tuple[PairFeatures, int]:
        """Generate features for a related fragment pair (label=1)."""
        # Simulate adjacent fragments from same file
        entropy_base = random.uniform(0.0, 8.0)
        entropy_a = entropy_base + random.uniform(-0.2, 0.2)
        entropy_b = entropy_base + random.uniform(-0.2, 0.2)
        entropy_a = max(0.0, min(8.0, entropy_a))
        entropy_b = max(0.0, min(8.0, entropy_b))

        size_a = 4096
        size_b = 4096 if random.random() > 0.1 else random.randint(100, 4095)

        entropy_diff = abs(entropy_a - entropy_b)
        entropy_sim = max(0.0, 1.0 - (entropy_diff / 8.0))

        size_diff = abs(size_a - size_b)
        max_size = max(size_a, size_b)
        size_sim = max(0.0, 1.0 - (size_diff / max_size)) if max_size > 0 else 1.0

        # Byte stats - similar for related fragments
        byte_stats_sim = random.uniform(0.7, 1.0)

        # Adjacent fragments
        offset_a = random.randint(0, 100000) * 4096
        offset_b = offset_a + size_a
        adjacency_bonus = 1.0
        offset_distance = 1.0

        same_size_flag = 1.0 if size_a == size_b else 0.0

        features = PairFeatures(
            entropy_similarity=entropy_sim,
            size_similarity=size_sim,
            byte_stats_similarity=byte_stats_sim,
            adjacency_bonus=adjacency_bonus,
            offset_distance=offset_distance,
            entropy_a=entropy_a,
            entropy_b=entropy_b,
            size_a=size_a,
            size_b=size_b,
            same_size_flag=same_size_flag
        )
        return features, 1

    def _generate_unrelated_pair(self) -> tuple[PairFeatures, int]:
        """Generate features for an unrelated fragment pair (label=0)."""
        # Simulate fragments from different files or distant locations
        entropy_a = random.uniform(0.0, 8.0)
        entropy_b = random.uniform(0.0, 8.0)

        size_a = random.choice([4096, random.randint(100, 4095)])
        size_b = random.choice([4096, random.randint(100, 4095)])

        entropy_diff = abs(entropy_a - entropy_b)
        entropy_sim = max(0.0, 1.0 - (entropy_diff / 8.0))

        size_diff = abs(size_a - size_b)
        max_size = max(size_a, size_b)
        size_sim = max(0.0, 1.0 - (size_diff / max_size)) if max_size > 0 else 1.0

        # Byte stats - dissimilar for unrelated
        byte_stats_sim = random.uniform(0.0, 0.6)

        # Non-adjacent
        offset_a = random.randint(0, 100000) * 4096
        offset_b = random.randint(0, 100000) * 4096
        while abs(offset_a - offset_b) < 4096 * 2:
            offset_b = random.randint(0, 100000) * 4096
        
        adjacency_bonus = 0.0
        offset_distance = min(1.0, abs(offset_a - offset_b) / (4096 * 10))

        same_size_flag = 1.0 if size_a == size_b else 0.0

        features = PairFeatures(
            entropy_similarity=entropy_sim,
            size_similarity=size_sim,
            byte_stats_similarity=byte_stats_sim,
            adjacency_bonus=adjacency_bonus,
            offset_distance=offset_distance,
            entropy_a=entropy_a,
            entropy_b=entropy_b,
            size_a=size_a,
            size_b=size_b,
            same_size_flag=same_size_flag
        )
        return features, 0

    def generate(self, n_samples: int = 2000) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic dataset.
        
        Args:
            n_samples: Total samples (balanced positive/negative)
            
        Returns:
            X: Feature matrix, y: Labels
        """
        n_half = n_samples // 2
        X = []
        y = []

        for _ in range(n_half):
            features, label = self._generate_related_pair()
            X.append(features.to_array())
            y.append(label)

        for _ in range(n_half):
            features, label = self._generate_unrelated_pair()
            X.append(features.to_array())
            y.append(label)

        # Shuffle
        indices = np.arange(n_samples)
        np.random.shuffle(indices)
        X = np.array(X)[indices]
        y = np.array(y)[indices]

        return X, y


class FragmentRelationshipModel:
    """
    Random Forest model for fragment relationship scoring.
    
    Provides probability scores [0, 1] for fragment pair relationships.
    Falls back gracefully if sklearn is unavailable.
    """

    def __init__(self, model_path: Path | None = None):
        self.model: RandomForestClassifier | None = None
        self.scaler: StandardScaler | None = None
        self.is_trained = False
        self.model_path = model_path or Path("models/fragment_rf_model.json")
        self.feature_names = [
            "entropy_similarity",
            "size_similarity", 
            "byte_stats_similarity",
            "adjacency_bonus",
            "offset_distance",
            "entropy_a",
            "entropy_b",
            "size_a",
            "size_b",
            "same_size_flag"
        ]

    def train(self, n_samples: int = 2000) -> dict:
        """Train the model on synthetic data."""
        if not SKLEARN_AVAILABLE:
            return {"status": "sklearn_unavailable", "trained": False}

        generator = SyntheticDatasetGenerator()
        X, y = generator.generate(n_samples)

        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Scale
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Train Random Forest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            class_weight="balanced",
            n_jobs=-1
        )
        self.model.fit(X_train_scaled, y_train)

        # Evaluate
        train_acc = self.model.score(X_train_scaled, y_train)
        test_acc = self.model.score(X_test_scaled, y_test)

        self.is_trained = True

        return {
            "status": "trained",
            "trained": True,
            "train_accuracy": round(train_acc, 4),
            "test_accuracy": round(test_acc, 4),
            "n_samples": n_samples,
            "n_features": len(self.feature_names),
            "data_type": "SYNTHETIC/CONTROLLED - NOT REAL FORENSIC DATA"
        }

    def predict_proba(self, features: PairFeatures) -> float:
        """Predict relationship probability [0, 1]."""
        if not self.is_trained or self.model is None or self.scaler is None:
            raise RuntimeError("Model not trained")

        X = features.to_array().reshape(1, -1)
        X_scaled = self.scaler.transform(X)
        proba = self.model.predict_proba(X_scaled)[0]
        return float(proba[1])  # Probability of class 1 (related)

    def save(self) -> bool:
        """Save model metadata (weights not persisted in this prototype)."""
        if not self.is_trained:
            return False
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "model_type": "RandomForestClassifier",
            "n_estimators": 100,
            "max_depth": 10,
            "feature_names": self.feature_names,
            "data_type": "SYNTHETIC/CONTROLLED",
            "trained": True
        }
        with open(self.model_path, "w") as f:
            json.dump(metadata, f, indent=2)
        return True

    def load(self) -> bool:
        """Load model (re-trains in this prototype since weights not persisted)."""
        if not SKLEARN_AVAILABLE:
            return False
        try:
            # In a real implementation, we'd load joblib/pickle
            # For prototype, we re-train
            result = self.train()
            return result.get("trained", False)
        except Exception:
            return False


def create_ml_scorer() -> Callable[[Fragment, Fragment], tuple[float, dict]] | None:
    """
    Factory function to create ML-based scorer for RelationshipScorer.
    Returns None if ML unavailable (fallback to baseline).
    """
    if not SKLEARN_AVAILABLE:
        return None

    model = FragmentRelationshipModel()
    train_result = model.train()

    if not train_result.get("trained", False):
        return None

    def ml_scorer(frag_a: Fragment, frag_b: Fragment) -> tuple[float, dict]:
        # Extract features using same logic as baseline
        entropy_diff = abs(frag_a.entropy - frag_b.entropy)
        entropy_sim = max(0.0, 1.0 - (entropy_diff / 8.0))

        size_diff = abs(frag_a.size - frag_b.size)
        max_size = max(frag_a.size, frag_b.size)
        size_sim = max(0.0, 1.0 - (size_diff / max_size)) if max_size > 0 else 1.0

        stats_a = frag_a.byte_stats
        stats_b = frag_b.byte_stats
        if stats_a and stats_b:
            byte_sim = 0.0
            count = 0
            for key in ["unique_bytes", "null_bytes", "max_byte_freq", "avg_byte_freq"]:
                if key in stats_a and key in stats_b:
                    val_a, val_b = stats_a[key], stats_b[key]
                    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                        max_val = max(val_a, val_b)
                        if max_val > 0:
                            diff = abs(val_a - val_b)
                            sim = max(0.0, 1.0 - (diff / max_val))
                            byte_sim += sim
                            count += 1
            byte_sim = byte_sim / count if count > 0 else 0.0
        else:
            byte_sim = 0.0

        offset_diff = abs(frag_a.offset - frag_b.offset)
        adjacency_bonus = 1.0 if offset_diff == frag_a.size or offset_diff == frag_b.size else 0.0
        offset_distance = min(1.0, offset_diff / (4096 * 10))

        same_size_flag = 1.0 if frag_a.size == frag_b.size else 0.0

        features = PairFeatures(
            entropy_similarity=entropy_sim,
            size_similarity=size_sim,
            byte_stats_similarity=byte_sim,
            adjacency_bonus=adjacency_bonus,
            offset_distance=offset_distance,
            entropy_a=frag_a.entropy,
            entropy_b=frag_b.entropy,
            size_a=frag_a.size,
            size_b=frag_b.size,
            same_size_flag=same_size_flag
        )

        try:
            ml_score = model.predict_proba(features)
            details = {
                "entropy_similarity": round(entropy_sim, 4),
                "size_similarity": round(size_sim, 4),
                "byte_stats_similarity": round(byte_sim, 4),
                "adjacency_bonus": adjacency_bonus,
                "ml_score": round(ml_score, 4),
                "scoring_method": "random_forest"
            }
            return ml_score, details
        except Exception:
            # Fallback handled by caller
            raise

    return ml_scorer


def get_baseline_scorer() -> Callable[[Fragment, Fragment], tuple[float, dict]]:
    """Return the baseline deterministic scorer."""
    def baseline_scorer(frag_a: Fragment, frag_b: Fragment) -> tuple[float, dict]:
        score = 0.0
        details = {}

        entropy_diff = abs(frag_a.entropy - frag_b.entropy)
        entropy_sim = max(0.0, 1.0 - (entropy_diff / 8.0))
        score += entropy_sim * 0.4
        details["entropy_similarity"] = round(entropy_sim, 4)

        size_diff = abs(frag_a.size - frag_b.size)
        max_size = max(frag_a.size, frag_b.size)
        size_sim = max(0.0, 1.0 - (size_diff / max_size)) if max_size > 0 else 1.0
        score += size_sim * 0.2
        details["size_similarity"] = round(size_sim, 4)

        stats_a = frag_a.byte_stats
        stats_b = frag_b.byte_stats
        if stats_a and stats_b:
            byte_sim = 0.0
            count = 0
            for key in ["unique_bytes", "null_bytes", "max_byte_freq", "avg_byte_freq"]:
                if key in stats_a and key in stats_b:
                    val_a, val_b = stats_a[key], stats_b[key]
                    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                        max_val = max(val_a, val_b)
                        if max_val > 0:
                            diff = abs(val_a - val_b)
                            sim = max(0.0, 1.0 - (diff / max_val))
                            byte_sim += sim
                            count += 1
            byte_sim = byte_sim / count if count > 0 else 0.0
            score += byte_sim * 0.3
            details["byte_stats_similarity"] = round(byte_sim, 4)

        offset_diff = abs(frag_a.offset - frag_b.offset)
        adj_bonus = 1.0 if offset_diff == frag_a.size or offset_diff == frag_b.size else 0.0
        score += adj_bonus * 0.1
        details["adjacency_bonus"] = adj_bonus
        details["scoring_method"] = "baseline"

        return min(1.0, score), details

    return baseline_scorer