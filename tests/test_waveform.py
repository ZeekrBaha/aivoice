from aivoice.ui.overlay import WaveformBuffer


def test_push_clamps_to_unit_range():
    b = WaveformBuffer(capacity=4)
    b.push(2.0)
    b.push(-1.0)
    b.push(0.5)
    assert b.levels == [1.0, 0.0, 0.5]


def test_buffer_trims_to_capacity_keeping_most_recent():
    b = WaveformBuffer(capacity=3)
    for v in [0.1, 0.2, 0.3, 0.4, 0.5]:
        b.push(v)
    assert b.levels == [0.3, 0.4, 0.5]


def test_clear_empties_buffer():
    b = WaveformBuffer(capacity=3)
    b.push(0.5)
    b.clear()
    assert b.levels == []


def test_bar_heights_length_matches_capacity():
    b = WaveformBuffer(capacity=5)
    b.push(1.0)
    heights = b.bar_heights(min_h=2.0, max_h=10.0)
    assert len(heights) == 5


def test_bar_heights_left_pads_with_min_and_newest_on_right():
    b = WaveformBuffer(capacity=4)
    b.push(1.0)  # max
    b.push(0.0)  # min
    heights = b.bar_heights(min_h=2.0, max_h=10.0)
    # Two empty slots (min) on the left, then the two pushed values, newest last.
    assert heights == [2.0, 2.0, 10.0, 2.0]


def test_bar_heights_maps_level_linearly():
    b = WaveformBuffer(capacity=1)
    b.push(0.5)
    assert b.bar_heights(min_h=0.0, max_h=10.0) == [5.0]
