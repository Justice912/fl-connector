from analysis_worker.engine import classify_drum_hit, infer_role, quantize_beats


def test_infer_role_recognizes_south_african_stem_names():
    assert infer_role("Main Log Drum.wav", "other") == "log_drum"
    assert infer_role("Shakers and Percs.wav", "other") == "percussion"
    assert infer_role("Lead Vox.wav", "other") == "vocals"


def test_quantize_beats_uses_quarter_beat_grid():
    assert quantize_beats(1.13) == 1.25
    assert quantize_beats(2.01) == 2.0


def test_drum_classifier_maps_low_mid_and_high_energy():
    assert classify_drum_hit(low=0.8, mid=0.1, high=0.1) == 36
    assert classify_drum_hit(low=0.1, mid=0.8, high=0.1) == 39
    assert classify_drum_hit(low=0.1, mid=0.1, high=0.8) == 42
