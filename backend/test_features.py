import pandas as pd

from app.features import AVAIL_LAG, episodes, threshold, visible


def hourly(vals):
    return pd.Series(vals, index=pd.date_range("2020-01-01", periods=len(vals), freq="h"), dtype=float)


def test_episode_rules():
    # hours: 9,9 at 5-6 | gap 5 | 9x3 at 12-14 | gap 6 | 9x3 at 21-23 | gap 7 | 9x4 at 31-34
    s = hourly([0] * 5 + [9, 9] + [0] * 5 + [9] * 3 + [0] * 6 + [9] * 3 + [0] * 7 + [9] * 4)
    e = episodes(s, 5)
    assert e.hours.tolist() == [19, 4]  # first three runs merge (gaps 5 and 6), the 7 h gap splits
    assert e.start.tolist() == [s.index[5], s.index[31]]


def test_short_spike_is_not_an_episode():
    assert episodes(hourly([0, 9, 9, 0, 0]), 5).empty


def test_gap_merge():
    merged = episodes(hourly([9, 9, 9, 0, 0, 0, 0, 0, 0, 9, 9, 9]), 5)  # 6 h gap merges
    split = episodes(hourly([9, 9, 9, 0, 0, 0, 0, 0, 0, 0, 9, 9, 9]), 5)  # 7 h gap does not
    assert len(merged) == 1 and len(split) == 2


def test_post_issue_data_is_excluded():
    ts = pd.date_range("2020-01-01", periods=10, freq="h")
    df = pd.DataFrame({"ts": ts, "availability_ts": ts + AVAIL_LAG, "v": range(10)})
    issue = ts[5]
    out = visible(df, issue)
    assert (out.availability_ts <= issue).all() and out.v.max() == 4  # hour 5 itself is not yet complete
    df.loc[9, "v"] = 999  # a future value must never appear
    assert 999 not in visible(df, issue).v.values


def test_threshold_uses_only_what_it_is_given():
    train = hourly(range(100))
    assert threshold(train) == train.quantile(0.95) and threshold(train) < 99
