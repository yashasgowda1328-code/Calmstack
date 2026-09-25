from typing import Callable
from app.models.scan import Fragment, Relationship
from app.ai.relationship_scorer import create_ml_scorer, get_baseline_scorer


class RelationshipScorer:
    def __init__(self, use_ml: bool = True):
        self._ml_scorer = create_ml_scorer() if use_ml else None
        self._baseline_scorer = get_baseline_scorer()
        
        # Use ML if available, otherwise baseline
        if self._ml_scorer is not None:
            self.scorer: Callable[[Fragment, Fragment], tuple[float, dict]] = self._ml_scorer
            self._scoring_method = "random_forest"
        else:
            self.scorer = self._baseline_scorer
            self._scoring_method = "baseline"

    def set_scorer(self, scorer: Callable[[Fragment, Fragment], tuple[float, dict]]):
        self.scorer = scorer

    def score(self, frag_a: Fragment, frag_b: Fragment) -> Relationship:
        try:
            score, details = self.scorer(frag_a, frag_b)
        except Exception:
            # Fallback to baseline on any ML error
            if self._scoring_method != "baseline":
                self.scorer = self._baseline_scorer
                self._scoring_method = "baseline"
                score, details = self.scorer(frag_a, frag_b)
            else:
                raise

        return Relationship(
            fragment_a=frag_a.fragment_id,
            fragment_b=frag_b.fragment_id,
            relationship_score=round(score, 4),
            score_details=details
        )

    @property
    def scoring_method(self) -> str:
        return self._scoring_method


def analyze_relationships(fragments: list[Fragment], max_pairs: int = 50) -> list[Relationship]:
    scorer = RelationshipScorer(use_ml=True)
    relationships = []
    
    # Only compare adjacent fragments + a few nearby to limit comparisons
    # For hackathon: compare each fragment with next 3 fragments
    window = 3
    
    for i, frag_a in enumerate(fragments):
        for j in range(i + 1, min(i + window + 1, len(fragments))):
            frag_b = fragments[j]
            rel = scorer.score(frag_a, frag_b)
            relationships.append(rel)
            
            if len(relationships) >= max_pairs:
                break
        if len(relationships) >= max_pairs:
            break
    
    return relationships