from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

FRAME_S: float = 0.02


def to_vocab_ids(ipa: str, vocab: Mapping[str, int]) -> list[int]:
    """Greedy longest-match conversion of IPA string to vocabulary token IDs."""
    ids: list[int] = []
    i = 0
    n = len(ipa)
    # Sort vocab keys by length descending to match longest phoneme first
    sorted_keys = sorted(vocab.keys(), key=len, reverse=True)

    while i < n:
        matched = False
        for k in sorted_keys:
            if ipa.startswith(k, i):
                ids.append(vocab[k])
                i += len(k)
                matched = True
                break
        if not matched:
            i += 1  # Skip unknown character
    return ids


def ctc_force_align(
    log_probs: Any,
    targets: Sequence[int],
    blank: int = 0,
) -> list[tuple[int, int, int]]:
    """Standard CTC Viterbi forced alignment over a (frames, vocab) log-prob matrix.

    Returns:
        List of (target_index, start_frame, end_frame) for each target.
    """
    num_frames = len(log_probs)
    num_targets = len(targets)

    if num_frames < num_targets:
        raise ValueError(
            f"Fewer frames ({num_frames}) than the minimum targets need ({num_targets})"
        )

    if num_targets == 0:
        return []

    # Build CTC state sequence with interleaved blanks: [blank, t0, blank, t1, ..., blank]
    states: list[int] = []
    for t in targets:
        states.append(blank)
        states.append(t)
    states.append(blank)
    num_states = len(states)

    neg_inf = -1e9

    # Trellis: V[t][s]
    # Backpointers: B[t][s]
    v_prev = [neg_inf] * num_states
    v_prev[0] = float(log_probs[0][states[0]])
    v_prev[1] = float(log_probs[0][states[1]])

    backpointers: list[list[int]] = []

    for t in range(1, num_frames):
        v_curr = [neg_inf] * num_states
        bp_curr = [-1] * num_states
        frame_lp = log_probs[t]

        for s in range(num_states):
            # 1. Stay in same state
            best_prev = s
            best_val = v_prev[s]

            # 2. Transition from previous state
            if s > 0 and v_prev[s - 1] > best_val:
                best_val = v_prev[s - 1]
                best_prev = s - 1

            # 3. Skip blank if target differs from target two steps back
            if (
                s > 1
                and states[s] != blank
                and states[s] != states[s - 2]
                and v_prev[s - 2] > best_val
            ):
                best_val = v_prev[s - 2]
                best_prev = s - 2

            v_curr[s] = best_val + float(frame_lp[states[s]])
            bp_curr[s] = best_prev

        backpointers.append(bp_curr)
        v_prev = v_curr

    # Backtrack path starting from best end state (either final blank or final target)
    if v_prev[num_states - 1] >= v_prev[num_states - 2]:
        curr_state = num_states - 1
    else:
        curr_state = num_states - 2

    path: list[int] = [curr_state]
    for t in range(num_frames - 2, -1, -1):
        curr_state = backpointers[t][curr_state]
        path.append(curr_state)
    path.reverse()

    # Extract start and end frames for each target: state index is 2*k + 1
    alignment: list[tuple[int, int, int]] = []
    for k in range(num_targets):
        target_state = 2 * k + 1
        frames_for_k = [f for f, s in enumerate(path) if s == target_state]
        if frames_for_k:
            alignment.append((k, frames_for_k[0], frames_for_k[-1]))
        else:
            # Fallback if target was assigned a single frame boundary
            alignment.append((k, 0, 0))

    return alignment


def phone_scores(
    log_probs: Any,
    alignment: Sequence[tuple[int, int, int]],
    targets: Sequence[int],
) -> list[float]:
    """Calculates mean confidence score exp(log_prob) over each target's frames."""
    scores: list[float] = []
    for target_idx, start_f, end_f in alignment:
        target_id = targets[target_idx]
        frame_probs = [math.exp(float(log_probs[f][target_id])) for f in range(start_f, end_f + 1)]
        score = sum(frame_probs) / max(len(frame_probs), 1)
        scores.append(round(score, 3))
    return scores
