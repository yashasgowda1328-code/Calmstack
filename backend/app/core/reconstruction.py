from typing import Callable
from app.models.scan import Fragment, Relationship, ReconstructionCandidate


class ReconstructionEngine:
    def __init__(self, min_threshold: float = 0.70):
        self.min_threshold = min_threshold
        self.scorer: Callable[[list[Fragment], list[Relationship]], list[ReconstructionCandidate]] = self._default_reconstructor
        self.validator: Callable[[ReconstructionCandidate, list[Fragment], list[Relationship]], ReconstructionCandidate] = self._default_validator

    def set_scorer(self, scorer: Callable[[list[Fragment], list[Relationship]], list[ReconstructionCandidate]]):
        self.scorer = scorer

    def set_validator(self, validator: Callable[[ReconstructionCandidate, list[Fragment], list[Relationship]], ReconstructionCandidate]):
        self.validator = validator

    def reconstruct(self, fragments: list[Fragment], relationships: list[Relationship]) -> list[ReconstructionCandidate]:
        candidates = self.scorer(fragments, relationships)
        # Validate each candidate
        validated = [self.validator(c, fragments, relationships) for c in candidates]
        validated.sort(key=lambda c: -c.confidence_score)
        return validated

    def _default_reconstructor(self, fragments: list[Fragment], relationships: list[Relationship]) -> list[ReconstructionCandidate]:
        if not fragments:
            return []

        # Build adjacency map from relationships
        adj = {}
        for rel in relationships:
            if rel.relationship_score >= self.min_threshold:
                if rel.fragment_a not in adj:
                    adj[rel.fragment_a] = []
                if rel.fragment_b not in adj:
                    adj[rel.fragment_b] = []
                adj[rel.fragment_a].append((rel.fragment_b, rel.relationship_score))
                adj[rel.fragment_b].append((rel.fragment_a, rel.relationship_score))

        # Find connected components (chains) using DFS
        visited = set()
        candidates = []
        frag_map = {f.fragment_id: f for f in fragments}

        def dfs(node: str, chain: list[str], scores: list[float]):
            visited.add(node)
            chain.append(node)
            
            if node in adj:
                # Sort by score descending to follow strongest relationships first
                for neighbor, score in sorted(adj[node], key=lambda x: -x[1]):
                    if neighbor not in visited:
                        scores.append(score)
                        dfs(neighbor, chain, scores)
                        break  # Only follow the strongest path for linear chain

        # Process each fragment as potential chain start
        for frag in fragments:
            if frag.fragment_id not in visited:
                chain = []
                scores = []
                dfs(frag.fragment_id, chain, scores)
                
                if len(chain) >= 1:
                    candidate = self._build_candidate(chain, scores, frag_map)
                    candidates.append(candidate)

        # Sort by confidence score descending
        candidates.sort(key=lambda c: -c.confidence_score)
        
        return candidates

    def _build_candidate(self, fragment_ids: list[str], scores: list[float], frag_map: dict) -> ReconstructionCandidate:
        if not fragment_ids:
            return None

        # Sort fragments by offset for proper ordering
        sorted_frags = sorted([frag_map[fid] for fid in fragment_ids], key=lambda f: f.offset)
        ordered_ids = [f.fragment_id for f in sorted_frags]
        
        fragment_count = len(ordered_ids)
        total_size = sum(f.size for f in sorted_frags)
        
        # Integrity score: based on relationship consistency within the chain
        if scores:
            integrity_score = sum(scores) / len(scores)
        else:
            integrity_score = 1.0 if fragment_count == 1 else 0.5

        # Confidence score: combines integrity with chain completeness
        # Single fragment has lower confidence
        if fragment_count == 1:
            confidence_score = integrity_score * 0.6
        else:
            # Check if fragments are contiguous (no gaps)
            is_contiguous = True
            for i in range(len(sorted_frags) - 1):
                if sorted_frags[i].offset + sorted_frags[i].size != sorted_frags[i + 1].offset:
                    is_contiguous = False
                    break
            
            contiguous_bonus = 0.2 if is_contiguous else 0.0
            confidence_score = min(1.0, integrity_score * 0.8 + contiguous_bonus)

        # Average relationship score for reference
        avg_rel_score = sum(scores) / len(scores) if scores else 0.0

        # Determine status
        if fragment_count == 1:
            status = "SINGLE_FRAGMENT"
        elif confidence_score >= 0.8 and integrity_score >= 0.7:
            status = "STRONG_CANDIDATE"
        elif confidence_score >= 0.6:
            status = "CANDIDATE"
        else:
            status = "WEAK_CANDIDATE"

        return ReconstructionCandidate(
            reconstruction_id=f"R{len(fragment_ids):03d}",
            fragment_ids=ordered_ids,
            fragment_count=fragment_count,
            integrity_score=round(integrity_score, 4),
            confidence_score=round(confidence_score, 4),
            evidence_quality="UNKNOWN",
            priority="UNKNOWN",
            status=status,
            total_size=total_size,
            avg_relationship_score=round(avg_rel_score, 4),
            validation_details={}
        )

    def _default_validator(self, candidate: ReconstructionCandidate, fragments: list[Fragment], relationships: list[Relationship]) -> ReconstructionCandidate:
        frag_map = {f.fragment_id: f for f in fragments}
        candidate_frags = [frag_map[fid] for fid in candidate.fragment_ids if fid in frag_map]
        
        # --- Validation Metrics ---
        
        # 1. Relationship consistency (std dev of scores)
        rel_scores = []
        for i in range(len(candidate_frags) - 1):
            a, b = candidate_frags[i].fragment_id, candidate_frags[i+1].fragment_id
            for rel in relationships:
                if (rel.fragment_a == a and rel.fragment_b == b) or (rel.fragment_a == b and rel.fragment_b == a):
                    rel_scores.append(rel.relationship_score)
                    break
        
        if rel_scores:
            rel_mean = sum(rel_scores) / len(rel_scores)
            rel_std = (sum((s - rel_mean) ** 2 for s in rel_scores) / len(rel_scores)) ** 0.5
            consistency_score = max(0.0, 1.0 - rel_std * 2)  # Penalize high variance
        else:
            consistency_score = 1.0 if candidate.fragment_count == 1 else 0.3
        
        # 2. Fragment count factor (more fragments = more evidence)
        count_factor = min(1.0, candidate.fragment_count / 5.0)  # Normalize to 5 fragments
        
        # 3. Size completeness (fragments at expected size)
        expected_size = 4096  # FRAGMENT_SIZE
        size_ratios = [f.size / expected_size for f in candidate_frags]
        completeness_score = sum(size_ratios) / len(size_ratios) if size_ratios else 0.0
        
        # 4. Hash availability (all fragments have SHA256)
        hash_score = 1.0 if all(f.sha256 for f in candidate_frags) else 0.0
        
        # 5. Entropy consistency across fragments
        if len(candidate_frags) > 1:
            entropies = [f.entropy for f in candidate_frags]
            entropy_range = max(entropies) - min(entropies)
            entropy_consistency = max(0.0, 1.0 - entropy_range / 4.0)  # Normalize by max possible range
        else:
            entropy_consistency = 1.0
        
        # 6. Incomplete final fragment penalty
        last_frag = candidate_frags[-1]
        is_incomplete = last_frag.size < expected_size
        incomplete_penalty = 0.1 if is_incomplete else 0.0
        
        # --- Integrity Score (internal consistency/completeness) ---
        # Weighted: relationship consistency (0.4), completeness (0.3), entropy consistency (0.2), hash (0.1)
        integrity_score = (
            consistency_score * 0.4 +
            completeness_score * 0.3 +
            entropy_consistency * 0.2 +
            hash_score * 0.1
        )
        integrity_score = max(0.0, integrity_score - incomplete_penalty)
        
        # --- Confidence Score (evidence strength) ---
        # Weighted: integrity (0.5), fragment count (0.2), avg relationship (0.2), contiguous bonus (0.1)
        contiguous_bonus = 0.1 if self._is_contiguous(candidate_frags) else 0.0
        confidence_score = min(1.0, (
            integrity_score * 0.5 +
            count_factor * 0.2 +
            candidate.avg_relationship_score * 0.2 +
            contiguous_bonus
        ))
        
        # Single fragment adjustment
        if candidate.fragment_count == 1:
            confidence_score = integrity_score * 0.6
        
        # --- Evidence Quality ---
        if integrity_score >= 0.85 and confidence_score >= 0.8:
            evidence_quality = "HIGH"
        elif integrity_score >= 0.65 and confidence_score >= 0.6:
            evidence_quality = "MEDIUM"
        else:
            evidence_quality = "LOW"
        
        # --- Priority ---
        if evidence_quality == "HIGH" and candidate.fragment_count >= 3:
            priority = "HIGH"
        elif evidence_quality == "MEDIUM" or (evidence_quality == "HIGH" and candidate.fragment_count < 3):
            priority = "MEDIUM"
        else:
            priority = "LOW"
        
        # --- Status ---
        if candidate.fragment_count == 1:
            status = "SINGLE_FRAGMENT"
        elif evidence_quality == "HIGH" and confidence_score >= 0.85:
            status = "STRONG_CANDIDATE"
        elif evidence_quality == "MEDIUM" and confidence_score >= 0.65:
            status = "CANDIDATE"
        else:
            status = "WEAK_CANDIDATE"
        
        # Build validation details
        validation_details = {
            "relationship_consistency": round(consistency_score, 4),
            "fragment_count_factor": round(count_factor, 4),
            "size_completeness": round(completeness_score, 4),
            "hash_availability": hash_score,
            "entropy_consistency": round(entropy_consistency, 4),
            "incomplete_final_fragment": is_incomplete,
            "incomplete_penalty": incomplete_penalty,
            "contiguous_bonus": contiguous_bonus,
        }
        
        # Update candidate
        candidate.integrity_score = round(integrity_score, 4)
        candidate.confidence_score = round(confidence_score, 4)
        candidate.evidence_quality = evidence_quality
        candidate.priority = priority
        candidate.status = status
        candidate.validation_details = validation_details
        
        return candidate

    def _is_contiguous(self, frags: list[Fragment]) -> bool:
        for i in range(len(frags) - 1):
            if frags[i].offset + frags[i].size != frags[i + 1].offset:
                return False
        return True


def build_reconstructions(
    fragments: list[Fragment],
    relationships: list[Relationship],
    min_threshold: float = 0.70
) -> list[ReconstructionCandidate]:
    engine = ReconstructionEngine(min_threshold=min_threshold)
    candidates = engine.reconstruct(fragments, relationships)
    
    # Update reconstruction IDs to be sequential
    for i, candidate in enumerate(candidates):
        candidate.reconstruction_id = f"R{i+1:03d}"
    
    return candidates