"""
ReConstructAI - AI Fragment Relevance / Junk Filtering Model

Determines which candidate fragments are likely relevant to a target
artifact reconstruction and which are likely unrelated/junk.

Uses sklearn.ensemble.RandomForestClassifier.
Training data is SYNTHETIC/CONTROLLED only.
"""

import os
import random
import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from app.models.scan import Fragment

# Classification thresholds
HIGH_RELEVANCE_MIN = 0.80
UNCERTAIN_MIN = 0.60
# 0.00 - 0.59 = LOW_RELEVANCE

# Feature names in canonical order
FEATURE_NAMES = [
    "fragment_size_normalized",
    "entropy",
    "unique_byte_count",
    "null_byte_count",
    "avg_byte_frequency",
    "max_byte_frequency",
    "is_complete_fragment",
    "header_match",
    "data_density",
    "low_entropy_ratio",
]


@dataclass
class FragmentRelevanceFeatures:
    """Feature vector for a single fragment."""
    
    fragment_size_normalized: float
    entropy: float
    unique_byte_count: float
    null_byte_count: float
    avg_byte_frequency: float
    max_byte_frequency: float
    is_complete_fragment: float
    header_match: float
    data_density: float
    low_entropy_ratio: float
    
    def to_array(self) -> np.ndarray:
        return np.array([
            self.fragment_size_normalized,
            self.entropy,
            self.unique_byte_count,
            self.null_byte_count,
            self.avg_byte_frequency,
            self.max_byte_frequency,
            self.is_complete_fragment,
            self.header_match,
            self.data_density,
            self.low_entropy_ratio,
        ], dtype=np.float32)


class SyntheticRelevanceDatasetGenerator:
    """
    Generates SYNTHETIC/CONTROLLED training data for the relevance model.
    
    Positive examples: fragments from the target artifact (PDF, JPEG, PNG, etc.)
    Negative examples: junk/unrelated fragments, zeros, random noise.
    """
    
    FRAGMENT_SIZE = 4096
    RANDOM_SEED = 42
    
    def __init__(self, random_seed: int = 42):
        self.random_seed = random_seed
    
    def _bytes_to_features(self, data: bytes, file_type: str = "unknown") -> FragmentRelevanceFeatures:
        """Convert raw bytes to feature vector."""
        size = len(data)
        size_norm = size / self.FRAGMENT_SIZE
        
        if size == 0:
            return FragmentRelevanceFeatures(
                fragment_size_normalized=0.0,
                entropy=0.0,
                unique_byte_count=0.0,
                null_byte_count=0.0,
                avg_byte_frequency=0.0,
                max_byte_frequency=0.0,
                is_complete_fragment=0.0,
                header_match=0.0,
                data_density=0.0,
                low_entropy_ratio=1.0,
            )
        
        # Byte counts
        byte_counts = [0] * 256
        for byte in data:
            byte_counts[byte] += 1
        
        non_zero = [c for c in byte_counts if c > 0]
        unique_bytes = len(non_zero)
        null_bytes = byte_counts[0]
        max_byte_freq = max(byte_counts) / size if size > 0 else 0.0
        avg_byte_freq = sum(non_zero) / len(non_zero) if non_zero else 0.0
        
        # Entropy
        entropy = 0.0
        for count in byte_counts:
            if count > 0:
                probability = count / size
                entropy -= probability * math.log2(probability)
        entropy = round(entropy, 4)
        
        # Header match
        header_match = 0.0
        header = data[:8]
        known_headers = {
            b"%PDF": 1.0,
            b"\x89PNG": 1.0,
            b"\xff\xd8\xff": 1.0,
            b"PK\x03\x04": 1.0,
            b"PK\x05\x06": 1.0,
            b"MZ": 1.0,
            b"\x7fELF": 1.0,
        }
        for sig, score in known_headers.items():
            if header.startswith(sig):
                header_match = score
                break
        
        # Data density (non-null bytes ratio)
        data_density = (size - null_bytes) / size if size > 0 else 0.0
        
        # Low entropy ratio (text-like data)
        low_entropy_ratio = 1.0 - (entropy / 8.0) if entropy > 0 else 1.0
        
        # Is complete fragment
        is_complete = 1.0 if size == self.FRAGMENT_SIZE else 0.0
        
        return FragmentRelevanceFeatures(
            fragment_size_normalized=round(size_norm, 4),
            entropy=entropy,
            unique_byte_count=round(unique_bytes / 256, 4),
            null_byte_count=round(null_bytes / size, 4),
            avg_byte_frequency=round(avg_byte_freq, 6),
            max_byte_frequency=round(max_byte_freq, 6),
            is_complete_fragment=is_complete,
            header_match=header_match,
            data_density=round(data_density, 4),
            low_entropy_ratio=round(low_entropy_ratio, 4),
        )
    
    def _generate_pdf_fragment(self) -> Tuple[np.ndarray, int]:
        """Generate a positive PDF fragment."""
        # Realistic PDF fragment with content
        random.seed(self.random_seed)
        rng = random.Random(hash("pdf_positive") % 10000)
        
        # Simulate PDF content bytes
        content = b"%PDF-1.4\n" + bytes(rng.randint(32, 126) for _ in range(100))
        padding = os.urandom(50)
        data = (content + padding)[:self.FRAGMENT_SIZE]
        data = data.ljust(self.FRAGMENT_SIZE, b"\x00")
        
        features = self._bytes_to_features(data, "PDF")
        return features.to_array(), 1
    
    def _generate_jpeg_fragment(self) -> Tuple[np.ndarray, int]:
        """Generate a positive JPEG fragment."""
        rng = random.Random(hash("jpeg_positive") % 10000)
        
        header = b"\xff\xd8\xff\xe0" + bytes(rng.randint(0, 255) for _ in range(100))
        data = header + bytes(rng.randint(0, 255) for _ in range(self.FRAGMENT_SIZE - len(header)))
        data = data[:self.FRAGMENT_SIZE]
        
        features = self._bytes_to_features(data, "JPEG")
        return features.to_array(), 1
    
    def _generate_png_fragment(self) -> Tuple[np.ndarray, int]:
        """Generate a positive PNG fragment."""
        rng = random.Random(hash("png_positive") % 10000)
        
        header = b"\x89PNG\r\n\x1a\n" + bytes(rng.randint(0, 255) for _ in range(100))
        data = header + bytes(rng.randint(0, 255) for _ in range(self.FRAGMENT_SIZE - len(header)))
        data = data[:self.FRAGMENT_SIZE]
        
        features = self._bytes_to_features(data, "PNG")
        return features.to_array(), 1
    
    def _generate_text_fragment(self) -> Tuple[np.ndarray, int]:
        """Generate a positive text fragment (part of target file)."""
        rng = random.Random(hash("text_positive") % 10000)
        
        content = "".join(chr(rng.randint(32, 126)) for _ in range(self.FRAGMENT_SIZE))
        data = content.encode("ascii")[:self.FRAGMENT_SIZE]
        
        features = self._bytes_to_features(data, "Text")
        return features.to_array(), 1
    
    def _generate_junk_fragment(self) -> Tuple[np.ndarray, int]:
        """Generate a negative junk fragment (unrelated data)."""
        rng = random.Random(hash("junk_negative") % 10000)
        
        # Random noise with high entropy
        data = os.urandom(self.FRAGMENT_SIZE)
        
        features = self._bytes_to_features(data, "junk")
        return features.to_array(), 0
    
    def _generate_zero_fragment(self) -> Tuple[np.ndarray, int]:
        """Generate a negative zero-fill fragment (unallocated)."""
        data = b"\x00" * self.FRAGMENT_SIZE
        
        features = self._bytes_to_features(data, "zero")
        return features.to_array(), 0
    
    def _generate_partial_fragment(self) -> Tuple[np.ndarray, int]:
        """Generate a negative partial fragment (incomplete trailing data)."""
        rng = random.Random(hash("partial_negative") % 10000)
        
        data = os.urandom(rng.randint(1, self.FRAGMENT_SIZE - 1))
        
        features = self._bytes_to_features(data, "partial")
        return features.to_array(), 0
    
    def generate(self, n_samples: int = 200) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate synthetic training data.
        
        Returns:
            X: Feature matrix, y: Labels (1=relevant, 0=irrelevant)
        """
        np.random.seed(self.random_seed)
        random.seed(self.random_seed)
        
        n_positive = n_samples // 2
        n_negative = n_samples - n_positive
        
        positive_generators = [
            self._generate_pdf_fragment,
            self._generate_jpeg_fragment,
            self._generate_png_fragment,
            self._generate_text_fragment,
        ]
        
        negative_generators = [
            self._generate_junk_fragment,
            self._generate_zero_fragment,
            self._generate_partial_fragment,
        ]
        
        X = []
        y = []
        
        # Generate positive samples (relevant fragments)
        for i in range(n_positive):
            gen = positive_generators[i % len(positive_generators)]
            features, label = gen()
            # Add small deterministic variation
            noise = np.random.RandomState(i).normal(0, 0.01, size=features.shape).astype(np.float32)
            features = np.clip(features + noise, 0, 1).astype(np.float32)
            X.append(features)
            y.append(label)
        
        # Generate negative samples (irrelevant fragments)
        for i in range(n_negative):
            gen = negative_generators[i % len(negative_generators)]
            features, label = gen()
            # Add small deterministic variation
            noise = np.random.RandomState(i + n_positive).normal(0, 0.01, size=features.shape).astype(np.float32)
            features = np.clip(features + noise, 0, 1).astype(np.float32)
            X.append(features)
            y.append(label)
        
        # Shuffle
        indices = np.arange(len(X))
        np.random.shuffle(indices)
        X = np.array(X)[indices]
        y = np.array(y)[indices]
        
        return X, y


@dataclass
class FragmentRelevanceResult:
    """Result of relevance scoring for a fragment."""
    
    fragment_id: str
    relevance_score: float  # 0.0 - 1.0
    relevance_class: str    # HIGH_RELEVANCE, UNCERTAIN, LOW_RELEVANCE
    confidence: float = 0.0  # Distance from decision boundary
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fragment_id": self.fragment_id,
            "relevance_score": round(self.relevance_score, 4),
            "relevance_class": self.relevance_class,
            "confidence": round(self.confidence, 4),
        }


class FragmentRelevanceModel:
    """
    Random Forest model for fragment relevance scoring.
    
    Provides probability scores [0, 1] for fragment relevance.
    Trains on synthetic/controlled data.
    """
    
    def __init__(self, model_path: Optional[Path] = None):
        self.model: Optional[RandomForestClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self.is_trained = False
        self.model_path = model_path or Path("models/fragment_relevance_model.json")
        self._generator = SyntheticRelevanceDatasetGenerator()
    
    def train(self, n_samples: int = 200) -> Dict[str, Any]:
        """Train the model on synthetic data."""
        if not SKLEARN_AVAILABLE:
            return {
                "status": "sklearn_unavailable",
                "trained": False,
                "data_type": "SYNTHETIC/CONTROLLED - NOT REAL FORENSIC DATA"
            }
        
        X, y = self._generator.generate(n_samples)
        
        # Use train/test split for evaluation
        from sklearn.model_selection import train_test_split
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        # Scale features
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
        
        train_acc = self.model.score(X_train_scaled, y_train)
        test_acc = self.model.score(X_test_scaled, y_test)
        
        self.is_trained = True
        
        return {
            "status": "trained",
            "trained": True,
            "train_accuracy": round(train_acc, 4),
            "test_accuracy": round(test_acc, 4),
            "n_samples": n_samples,
            "n_features": len(FEATURE_NAMES),
            "feature_names": FEATURE_NAMES,
            "data_type": "SYNTHETIC/CONTROLLED - NOT REAL FORENSIC DATA",
            "thresholds": {
                "high_relevance_min": HIGH_RELEVANCE_MIN,
                "uncertain_min": UNCERTAIN_MIN,
            }
        }
    
    def extract_features(self, data: bytes) -> np.ndarray:
        """Extract feature vector from raw bytes."""
        features = self._generator._bytes_to_features(data)
        return features.to_array()
    
    def extract_fragment_features(self, fragment: Fragment) -> np.ndarray:
        """Extract features from a Fragment object (uses stored features)."""
        size = fragment.size
        size_norm = min(1.0, size / 4096)
        
        byte_stats = fragment.byte_stats or {}
        unique_bytes = byte_stats.get("unique_bytes", 256)
        null_bytes = byte_stats.get("null_bytes", 0)
        max_byte_freq = byte_stats.get("max_byte_freq", 1/4096)
        avg_byte_freq = byte_stats.get("avg_byte_freq", 4096/256)
        
        unique_norm = min(1.0, unique_bytes / 256)
        null_ratio = null_bytes / size if size > 0 else 0.0
        avg_freq_norm = min(1.0, avg_byte_freq / 4096) if avg_byte_freq else 0.0
        max_freq_norm = min(1.0, max_byte_freq * 4096) if max_byte_freq else 0.0
        
        # Data density
        data_density = (size - null_bytes) / size if size > 0 else 0.0
        
        # Low entropy ratio
        low_entropy_ratio = 1.0 - (fragment.entropy / 8.0) if fragment.entropy > 0 else 1.0
        
        # Is complete fragment
        is_complete = 1.0 if size == 4096 else 0.0
        
        # Header match (check if fragment starts with known signature)
        header_match = 0.0
        header = byte_stats.get("header_bytes", "")
        if header:
            try:
                header_bytes = bytes.fromhex(header) if len(header) > 2 else b""
                known_sigs = [b"%PDF", b"\x89PNG", b"\xff\xd8\xff", b"PK\x03\x04", b"MZ"]
                for sig in known_sigs:
                    if header_bytes.startswith(sig):
                        header_match = 1.0
                        break
            except (ValueError, TypeError):
                pass
        
        features = FragmentRelevanceFeatures(
            fragment_size_normalized=round(size_norm, 4),
            entropy=fragment.entropy,
            unique_byte_count=round(unique_norm, 4),
            null_byte_count=round(null_ratio, 4),
            avg_byte_frequency=round(avg_freq_norm, 6),
            max_byte_frequency=round(max_freq_norm, 6),
            is_complete_fragment=is_complete,
            header_match=header_match,
            data_density=round(data_density, 4),
            low_entropy_ratio=round(low_entropy_ratio, 4),
        )
        
        return features.to_array()
    
    def predict(self, features: np.ndarray) -> float:
        """Predict relevance probability for a feature vector."""
        if not self.is_trained or self.model is None or self.scaler is None:
            raise RuntimeError("Model not trained")
        
        X = features.reshape(1, -1)
        X_scaled = self.scaler.transform(X)
        proba = self.model.predict_proba(X_scaled)[0]
        
        # Return probability of positive class (relevant)
        if len(proba) == 2:
            return float(proba[1])
        else:
            return float(proba[0])
    
    def classify(self, score: float) -> str:
        """Classify a relevance score into a class."""
        if score >= HIGH_RELEVANCE_MIN:
            return "HIGH_RELEVANCE"
        elif score >= UNCERTAIN_MIN:
            return "UNCERTAIN"
        else:
            return "LOW_RELEVANCE"
    
    def predict_fragment(self, fragment: Fragment) -> FragmentRelevanceResult:
        """Predict relevance for a Fragment object."""
        if not self.is_trained:
            raise RuntimeError("Model not trained")
        
        features = self.extract_fragment_features(fragment)
        score = self.predict(features)
        relevance_class = self.classify(score)
        
        # Confidence is distance from nearest threshold
        if score >= HIGH_RELEVANCE_MIN:
            confidence = min(1.0, (score - HIGH_RELEVANCE_MIN) / (1.0 - HIGH_RELEVANCE_MIN))
        elif score >= UNCERTAIN_MIN:
            midpoint = (HIGH_RELEVANCE_MIN + UNCERTAIN_MIN) / 2
            confidence = abs(score - midpoint) / (midpoint - UNCERTAIN_MIN) if midpoint != UNCERTAIN_MIN else 0.0
        else:
            confidence = 1.0 - (score / UNCERTAIN_MIN) if UNCERTAIN_MIN > 0 else 1.0
        
        return FragmentRelevanceResult(
            fragment_id=fragment.fragment_id,
            relevance_score=round(score, 4),
            relevance_class=relevance_class,
            confidence=round(confidence, 4),
        )
    
    def score_fragments(self, fragments: List[Fragment], 
                       reference_fragment: Optional[Fragment] = None) -> List[FragmentRelevanceResult]:
        """Score a list of fragments for relevance."""
        results = []
        for fragment in fragments:
            result = self.predict_fragment(fragment)
            results.append(result)
        return results
    
    def save(self) -> bool:
        """Save model metadata."""
        if not self.is_trained:
            return False
        
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        
        metadata = {
            "model_type": "RandomForestClassifier",
            "n_estimators": 100,
            "max_depth": 10,
            "feature_names": FEATURE_NAMES,
            "data_type": "SYNTHETIC/CONTROLLED",
            "trained": True,
            "thresholds": {
                "high_relevance_min": HIGH_RELEVANCE_MIN,
                "uncertain_min": UNCERTAIN_MIN,
            }
        }
        
        import json
        with open(self.model_path, "w") as f:
            json.dump(metadata, f, indent=2)
        return True


def create_relevance_model() -> Optional[FragmentRelevanceModel]:
    """Create and train a relevance model."""
    if not SKLEARN_AVAILABLE:
        return None
    
    model = FragmentRelevanceModel()
    result = model.train()
    
    if not result.get("trained", False):
        return None
    
    model.save()
    return model


def get_relevance_model() -> FragmentRelevanceModel:
    """Get a pre-trained relevance model."""
    model = FragmentRelevanceModel()
    
    # Try to load existing (re-train if needed since we don't persist weights in prototype)
    if not model.is_trained:
        model.train()
    
    return model