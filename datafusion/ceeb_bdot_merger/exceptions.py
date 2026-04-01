"""Custom exceptions for BDOT processing.

This module centralizes error types used across the BDOT modification
helpers so other modules can import them without depending on the
large `bdot_modification_functions` file.
"""

from __future__ import annotations


class BdotProcessingError(Exception):
    """Base exception for BDOT processing errors."""

    pass


class GeometryError(BdotProcessingError):
    """Exception raised for geometry parsing or transformation errors."""

    pass


class H3ConversionError(BdotProcessingError):
    """Exception raised for H3 index conversion errors."""

    pass


class ValidationError(BdotProcessingError):
    """Exception raised for input validation errors."""

    pass


class AddressParsingError(BdotProcessingError):
    """Exception raised for address parsing errors during duplication."""

    pass


__all__ = [
    "AddressParsingError",
    "BdotProcessingError",
    "GeometryError",
    "H3ConversionError",
    "ValidationError",
]
