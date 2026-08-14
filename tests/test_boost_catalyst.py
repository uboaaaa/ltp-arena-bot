from decimal import Decimal

from bot.main import count_catalyst_votes
from bot.config import CATALYST_VOTES_NEEDED, UNANIMITY_SIZE_MULT


def _vote(catalyst):
    return {"action": "SHORT", "confidence": 0.7, "catalyst": catalyst}


def boost_for(votes, tally=3, needed=2):
    # mirrors the expression in main.py's entry-vote branch; threshold pinned
    # explicitly (2) rather than echoing live config, per the config-echo lesson
    return UNANIMITY_SIZE_MULT if (
        tally == 3 and len(votes) == 3 and count_catalyst_votes(votes) >= needed
    ) else None


def test_catalyst_votes_needed_blocks_single_noisy_sample():
    # >= 2 is the standing floor; 4 (> max samples) means entries are frozen entirely
    assert CATALYST_VOTES_NEEDED >= 2


def test_live_config_is_frozen():
    # FREEZE 2026-08-14: no possible 3-sample vote can reach the live threshold,
    # so no entry can ever qualify while this holds
    votes = [_vote(True), _vote(True), _vote(True)]
    assert count_catalyst_votes(votes) < CATALYST_VOTES_NEEDED


def test_single_catalyst_sample_no_longer_boosts():
    # Aug 11 regression: one noisy catalyst=true sample out of three chain-fired strikes
    votes = [_vote(False), _vote(True), _vote(False)]
    assert boost_for(votes) is None


def test_two_catalyst_samples_boost():
    votes = [_vote(True), _vote(False), _vote(True)]
    assert boost_for(votes) == Decimal("2")


def test_three_catalyst_samples_boost():
    votes = [_vote(True), _vote(True), _vote(True)]
    assert boost_for(votes) == Decimal("2")


def test_missing_or_nonbool_catalyst_counts_as_false():
    votes = [{"action": "SHORT", "confidence": 0.7}, _vote("yes"), _vote(True)]
    assert count_catalyst_votes(votes) == 1
    assert boost_for(votes) is None


def test_non_unanimous_never_boosts_regardless_of_catalyst():
    votes = [_vote(True), _vote(True), _vote(True)]
    assert boost_for(votes, tally=2) is None
