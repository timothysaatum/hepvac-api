import logging
from typing import Any, Dict, Optional, Union


class LoggerMixin:
    """
    Mixin to add logging capability to classes.

    This mixin provides structured logging methods with support for both
    string and dictionary messages. It automatically creates a logger
    named after the class that uses it.

    Example:
        class MyService(LoggerMixin):
            def process(self):
                self.log_info("Processing started")
                self.log_debug({"action": "process", "status": "complete"})
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logger: Optional[logging.Logger] = None

    @property
    def logger(self) -> logging.Logger:
        """Lazy initialization of logger instance."""
        if self._logger is None:
            self._logger = logging.getLogger(self.__class__.__name__)
        return self._logger

    def _format_message(self, message: Union[str, Dict[str, Any]]) -> str:
        """
        Format message for logging.

        Args:
            message: String or dictionary to be logged

        Returns:
            Formatted string message
        """
        if isinstance(message, dict):
            return str(message)
        return message

    def log_info(self, message: Union[str, Dict[str, Any]], **kwargs) -> None:
        """
        Log an info level message.

        Args:
            message: Message to log (string or dict)
            **kwargs: Additional context to pass to logger
        """
        self.logger.info(self._format_message(message), **kwargs)

    def log_warning(self, message: Union[str, Dict[str, Any]], **kwargs) -> None:
        """
        Log a warning level message.

        Args:
            message: Message to log (string or dict)
            **kwargs: Additional context to pass to logger
        """
        self.logger.warning(self._format_message(message), **kwargs)

    def log_error(
        self, message: Union[str, Dict[str, Any]], exc_info: bool = False, **kwargs
    ) -> None:
        """
        Log an error level message.

        Args:
            message: Message to log (string or dict)
            exc_info: Include exception information if True
            **kwargs: Additional context to pass to logger
        """
        self.logger.error(self._format_message(message), exc_info=exc_info, **kwargs)

    def log_debug(self, message: Union[str, Dict[str, Any]], **kwargs) -> None:
        """
        Log a debug level message.

        Args:
            message: Message to log (string or dict)
            **kwargs: Additional context to pass to logger
        """
        self.logger.debug(self._format_message(message), **kwargs)

    def log_security_event(self, message: Union[str, Dict[str, Any]], **kwargs) -> None:
        """
        Log a security-related event at warning level.

        Security events are logged with a 'SECURITY EVENT:' prefix for
        easy filtering and monitoring.

        Args:
            message: Message to log (string or dict)
            **kwargs: Additional context to pass to logger
        """
        formatted_msg = self._format_message(message)
        self.logger.warning(f"SECURITY EVENT: {formatted_msg}", **kwargs)


class _ModuleLevelLogger(LoggerMixin):
    """Module-level logger instance that uses a fixed name."""

    def __init__(self):
        self._logger = logging.getLogger("app.logger")


logger = _ModuleLevelLogger()
