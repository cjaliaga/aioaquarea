import functools
import logging
from typing import TYPE_CHECKING  # Re-add TYPE_CHECKING

from .errors import (  # Added ApiError
    ApiError,
    AuthenticationError,
    AuthenticationErrorCodes,
)

if TYPE_CHECKING:  # Re-add TYPE_CHECKING block
    from .core import AquareaClient

_LOGGER = logging.getLogger(__name__)


def auth_required(fn):
    """Decorator to require authentication and to refresh login if it's able to."""

    @functools.wraps(fn)
    async def _wrap(
        client: "AquareaClient", *args, **kwargs
    ):  # Use string literal for type hint
        if client.is_logged is False:
            client.logger.warning(f"{client}: User is not logged or session is too old")
            await client.login()

        try:
            response = await fn(client, *args, **kwargs)
        except (
            AuthenticationError,
            ApiError,
        ) as exception:  # Catch both AuthenticationError and ApiError
            client.logger.warning(
                f"{client}: API Error: {getattr(exception, 'error_code', 'N/A')} - {getattr(exception, 'error_message', str(exception))}."
            )

            # If the error is invalid credentials, always raise.
            if (
                isinstance(exception, AuthenticationError)
                and exception.error_code
                == AuthenticationErrorCodes.INVALID_USERNAME_OR_PASSWORD
            ):
                raise

            # If refresh is not enabled, always raise.
            if not client.is_refresh_login_enabled:
                raise

            # If it's an ApiError with "Missing Authentication Token" or AuthenticationError with TOKEN_EXPIRED, try to re-login.
            if (
                isinstance(exception, ApiError)
                and "Missing Authentication Token" in str(exception)
            ) or (
                isinstance(exception, AuthenticationError)
                and exception.error_code == AuthenticationErrorCodes.TOKEN_EXPIRED
            ):
                client.logger.warning(
                    f"{client}: Token expired or missing. Trying to login again."
                )
                await client.login()
                response = await fn(client, *args, **kwargs)
            else:
                # For any other unhandled AuthenticationError or ApiError, re-raise.
                raise

        return response

    return _wrap
