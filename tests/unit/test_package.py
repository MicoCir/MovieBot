# tests/unit/test_package.py
def test_import_moviebot():
    import moviebot

    assert moviebot is not None


def test_import_movie_candidate():
    from moviebot.common.models import MovieCandidate

    assert MovieCandidate is not None
