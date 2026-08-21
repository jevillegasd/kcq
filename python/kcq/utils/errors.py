"""Exception hierarchy for kcq.

All kcq modules raise one of these instead of letting bare
KeyError/ValueError/etc. propagate, so callers (and the KLayout macro
console) get a consistent, identifiable error type.
"""


class KcqError(Exception):
    """Base class for all kcq-raised exceptions."""


class TechnologyNotFoundError(KcqError):
    """Raised when a named technology cannot be resolved via pya.Technology
    or its expected files (waveguides.xml, materials.xml, ...) are missing."""


class KcqConfigError(KcqError):
    """Raised on malformed or incomplete XML configuration (waveguides.xml,
    materials.xml). Carries enough context (file path, node) to fix the file."""


class InvalidGeometryError(KcqError):
    """Raised when requested geometry violates a technology constraint,
    e.g. a bend radius smaller than the technology's minimum, or an
    unmerged Region passed where merged geometry is required."""
