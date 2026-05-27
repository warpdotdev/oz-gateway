"""Exception types shared by webhook handlers.

The ``public_message`` attribute on :class:`WebhookValidationError` is the
contract between webhook handlers and the Flask route in ``app.py``: it is
the message that is safe to return to the HTTP client.

Returning ``str(exception)`` directly to clients is what CodeQL's
``py/stack-trace-exposure`` rule flags, because an arbitrary exception
message can leak internal state. Using an explicit attribute (rather than
``str(e)``) makes the safe-by-design intent visible to both readers and
static analyzers.
"""


class WebhookValidationError(ValueError):
    """A validation error whose message is safe to return to the client.

    Subclasses ``ValueError`` so that existing handler unit tests (which
    assert ``ValueError`` for missing or malformed payloads) keep working
    without modification.

    Args:
        public_message: A short, user-facing description of why the request
            was rejected. This message will be returned verbatim in the
            JSON response body. Do not include internal paths, secrets, or
            arbitrary exception detail here.
    """

    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message
