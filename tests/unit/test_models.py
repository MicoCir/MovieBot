# tests/unit/test_models.py
import pytest
from pydantic import ValidationError

from moviebot.agents.netflix.models import NetflixQuery
from moviebot.agents.tmdb.models import TrendingQuery
from moviebot.app.state import ChatState
from moviebot.common.models import AgentResult, MovieCandidate
from moviebot.routing.models import RouteDecision

# === Contract happy paths ===


def test_movie_candidate_valid():
    mc = MovieCandidate(
        id="tt123",
        title="Test Movie",
        source="tmdb",
        content_type="movie",
    )
    assert mc.title == "Test Movie"
    assert mc.genres == []
    assert mc.description is None


def test_movie_candidate_requires_content_type():
    with pytest.raises(ValidationError):
        MovieCandidate(id="tt123", title="Test Movie", source="tmdb")


def test_agent_result_defaults_are_isolated():
    first = AgentResult(query_interpretation={})
    second = AgentResult(query_interpretation={})

    assert first.candidates == []
    assert first.warnings == []
    assert first.candidates is not second.candidates
    assert first.warnings is not second.warnings


def test_netflix_query_defaults():
    nq = NetflixQuery()
    assert nq.semantic_query == ""
    assert nq.type == "any"
    assert nq.genres == []
    assert nq.min_year is None
    assert nq.max_year is None


def test_chat_state_initial():
    state = ChatState(user_query="hello")
    assert state.status is None
    assert state.tmdb_candidates == []
    assert state.netflix_candidates == []
    assert state.route is None
    assert state.warnings == []


def test_route_decision_valid():
    decision = RouteDecision(
        route="both",
        confidence=0.8,
        reason="The query can use both sources",
    )

    assert decision.route == "both"
    assert decision.confidence == 0.8


# === Contract rejection tests ===


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_route_decision_rejects_invalid_confidence(confidence: float):
    with pytest.raises(ValidationError):
        RouteDecision(route="trending", confidence=confidence, reason="test")


@pytest.mark.parametrize("route", ["ambiguous", "invalid"])
def test_route_decision_rejects_invalid_route(route: str):
    with pytest.raises(ValidationError):
        RouteDecision(route=route, confidence=0.9, reason="test")


@pytest.mark.parametrize("type_val", ["series"])
def test_netflix_query_rejects_invalid_type(type_val: str):
    with pytest.raises(ValidationError):
        NetflixQuery(type=type_val)


# === Contract invariants ===


@pytest.mark.parametrize("min_rating", [-0.1, 10.1])
def test_trending_query_rejects_invalid_min_rating(min_rating: float):
    with pytest.raises(ValidationError):
        TrendingQuery(min_rating=min_rating)


@pytest.mark.parametrize(
    "min_year,max_year",
    [(2020, 2019)],
)
def test_netflix_query_rejects_invalid_year_range(min_year: int, max_year: int):
    with pytest.raises(ValidationError):
        NetflixQuery(min_year=min_year, max_year=max_year)
