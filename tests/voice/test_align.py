from __future__ import annotations

import numpy as np
import pytest

from techradar.voice.align import ctc_force_align, to_vocab_ids


def test_ctc_force_align_toy() -> None:
    lp = np.log(
        np.array(
            [
                [0.9, 0.1, 0.0, 0.0],
                [0.1, 0.9, 0.0, 0.0],
                [0.9, 0.0, 0.1, 0.0],
                [0.1, 0.0, 0.9, 0.0],
            ]
        )
        + 1e-9
    )
    assert ctc_force_align(lp, [1, 2], blank=0) == [(0, 1, 1), (1, 3, 3)]


def test_ctc_force_align_too_few_frames() -> None:
    with pytest.raises(ValueError):
        ctc_force_align(np.zeros((1, 3)), [1, 2], blank=0)


def test_to_vocab_ids_longest_match() -> None:
    assert to_vocab_ids("tʃa", {"t": 1, "tʃ": 2, "a": 3}) == [2, 3]
