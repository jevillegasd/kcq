from kcq.utils.errors import (
    InvalidGeometryError,
    TechnologyNotFoundError,
    KcqConfigError,
    KcqError,
)


def test_all_kcq_exceptions_derive_from_base():
    for exc_cls in (TechnologyNotFoundError, KcqConfigError, InvalidGeometryError):
        assert issubclass(exc_cls, KcqError)


def test_exceptions_are_raisable_and_catchable_via_base():
    for exc_cls in (TechnologyNotFoundError, KcqConfigError, InvalidGeometryError):
        try:
            raise exc_cls("boom")
        except KcqError as exc:
            assert isinstance(exc, exc_cls)
            assert str(exc) == "boom"
        else:
            raise AssertionError(f"{exc_cls} did not raise")
