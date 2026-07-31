"""Single-instance guard for the LecturePack desktop shell (D-18/D-19).

A second launch must raise and focus the already-running window instead of
exiting silently (D-18) -- silent exit is indistinguishable from a failed
launch, which is what produced the owner's repeated clicking in the first
place. The guard runs in ``main()`` before ``MainWindow()`` is constructed,
and therefore before ``Backend.__init__`` and its deferred
``RuntimeBootstrapService.assess()`` worker (D-19): a guard placed after
window construction would let a second process sit invisible for the whole
pending-admission window.

Mechanism: ``QLocalServer``/``QLocalSocket`` (PySide6.QtNetwork), already
bundled with the PySide6 wheel -- no new dependency. This is the only one of
the three candidates considered (the others were ``QSharedMemory`` and a raw
named mutex) that also gives a second process a channel to ask the first to
raise, rather than merely detecting duplication.

Security (T-01-05-01..04): the entire wire protocol is ONE fixed ASCII
literal, compared by byte equality. There is no message format, no
versioning, no fields. The handler never calls ``json.loads``, ``eval``,
``exec`` or ``pickle`` on anything received from a peer, reads at most
``MAX_MESSAGE_BYTES`` per read, and drops any connection whose payload does
not match exactly. ``QLocalServer`` on Windows scopes its named pipe to the
current user by default; this module never widens that (no
``setSocketOptions`` call), and the endpoint name is a fixed literal derived
from stable application identity -- never from ``sys.argv`` or an
environment variable, so an unprivileged caller cannot choose which
"instance" it collides with.

Every Qt/network call is wrapped so a primitive failure degrades to a safe
default rather than raising or blocking -- mirrors
``app/desktop/win_integration.py``'s stated rule that an OS-integration
failure must never break the frozen EXE. Here that means ``acquire()``
returns ``"primary"`` (fail-open on launch) whenever the IPC primitive is
unavailable or raises, or when a stale endpoint left by a crashed prior
instance needs reclaiming (T-01-05-03) before it can be reclaimed.
"""

from __future__ import annotations

from typing import Callable, Optional

from . import version

# Fixed literal endpoint name derived from stable application identity
# (CONTEXT.md's discretion note: never built from sys.argv or an
# environment variable -- a caller-influenced name would let an
# unprivileged process choose which "instance" it collides with).
SINGLE_INSTANCE_ENDPOINT = f"{version.APP_NAME}.single-instance.v1"

# The entire wire protocol: one fixed ASCII literal. There is no message
# format, no versioning, no fields -- the channel carries one word and
# nothing else (T-01-05-01).
RAISE_SENTINEL = b"RAISE"

# A small bound on how much is ever read from a peer per read() call, so a
# hostile local process cannot force unbounded buffering by streaming bytes
# at the pipe (T-01-05-04).
MAX_MESSAGE_BYTES = 64

# Short, bounded waits -- a silent or hung peer must never stall startup.
_CONNECT_TIMEOUT_MS = 250
_WRITE_TIMEOUT_MS = 250


class SingleInstanceGuard:
    """Detects whether another LecturePack instance already owns the
    single-instance endpoint, and gives a second process a channel to ask
    the first to raise its window.
    """

    def __init__(self, endpoint: str = SINGLE_INSTANCE_ENDPOINT) -> None:
        self._endpoint = endpoint
        self._server = None
        self._raise_handler: Optional[Callable[[], None]] = None
        # Keeps accepted QLocalSocket connections alive until they finish
        # delivering (or failing to deliver) a payload -- otherwise Python
        # would garbage-collect them the moment _on_new_connection returns.
        self._live_connections: list = []
        # Keeps an outbound signal_existing() socket alive until its
        # graceful disconnect actually completes -- see signal_existing()'s
        # comment for why a bare local variable is not enough.
        self._pending_outbound: list = []

    def acquire(self) -> str:
        """Return "primary" if this process now owns the endpoint, or
        "secondary" if another instance already does. Never raises: any
        failure of the underlying IPC primitive degrades to "primary" so an
        OS-integration failure can never prevent the app from starting.
        """
        try:
            from PySide6.QtNetwork import QLocalServer, QLocalSocket

            probe = QLocalSocket()
            probe.connectToServer(self._endpoint)
            connected = probe.waitForConnected(_CONNECT_TIMEOUT_MS)
            probe.disconnectFromServer()
            probe.close()
            if connected:
                return "secondary"

            # No listener answered. Reclaim a stale endpoint left behind by
            # a crashed prior instance (T-01-05-03) before listening --
            # unconditionally, since a crashed process never gets a chance
            # to clean up after itself.
            QLocalServer.removeServer(self._endpoint)

            server = QLocalServer()
            server.newConnection.connect(self._on_new_connection)
            if not server.listen(self._endpoint):
                # Could not claim the endpoint for a reason other than a
                # live peer (e.g. a permissions conflict) -- the probe
                # above already proved no live instance is listening, so
                # fail open rather than block startup.
                return "primary"
            self._server = server
            return "primary"
        except Exception:
            return "primary"

    def signal_existing(self) -> bool:
        """Ask the running primary instance to raise its window. Returns
        whether the sentinel was sent; never raises."""
        try:
            from PySide6.QtNetwork import QLocalSocket

            sock = QLocalSocket()
            sock.connectToServer(self._endpoint)
            if not sock.waitForConnected(_CONNECT_TIMEOUT_MS):
                return False
            sock.write(RAISE_SENTINEL)
            sock.flush()
            sock.waitForBytesWritten(_WRITE_TIMEOUT_MS)
            # `sock` is a local variable. If this function returned while
            # it was still the only reference, Python would garbage-collect
            # it -- and PySide6's destructor tears the socket down --
            # before the just-flushed write and the graceful disconnect it
            # schedules could actually complete on the event loop, silently
            # discarding the sentinel before the primary ever read it.
            # Keep a strong reference until the disconnect signal confirms
            # the handshake is done; harmless to leak past process exit
            # (main() calls signal_existing() immediately before exiting).
            self._pending_outbound.append(sock)

            def _cleanup():
                try:
                    self._pending_outbound.remove(sock)
                except ValueError:
                    pass

            sock.disconnected.connect(_cleanup)
            sock.disconnectFromServer()
            return True
        except Exception:
            return False

    def set_raise_handler(self, callback: Callable[[], None]) -> None:
        """Register the callable invoked when a valid raise sentinel
        arrives on the endpoint this instance owns."""
        self._raise_handler = callback

    def release(self) -> None:
        """Stop listening and free the endpoint so a fresh acquire() (in
        this or a future process) can claim it again."""
        try:
            if self._server is not None:
                self._server.close()
                from PySide6.QtNetwork import QLocalServer

                QLocalServer.removeServer(self._endpoint)
        except Exception:
            pass
        finally:
            self._server = None
            self._live_connections.clear()
            self._pending_outbound.clear()

    def _on_new_connection(self) -> None:
        try:
            conn = self._server.nextPendingConnection()
        except Exception:
            return
        if conn is None:
            return
        self._live_connections.append(conn)

        def _cleanup():
            try:
                self._live_connections.remove(conn)
            except ValueError:
                pass

        def _on_ready_read():
            try:
                # Bounded read: a peer cannot force unbounded buffering by
                # streaming bytes at the pipe (T-01-05-04).
                payload = bytes(conn.read(MAX_MESSAGE_BYTES))
            except Exception:
                payload = b""
            # The handler compares the received bytes to the one literal
            # sentinel and nothing else. No json.loads, no eval, no exec,
            # no pickle, no logging of peer-supplied bytes (T-01-05-01) --
            # a local peer's maximum achievable effect is raising a window
            # the user already owns.
            if payload == RAISE_SENTINEL and self._raise_handler is not None:
                try:
                    self._raise_handler()
                except Exception:
                    pass
            try:
                conn.disconnectFromServer()
            except Exception:
                pass

        try:
            conn.readyRead.connect(_on_ready_read)
            conn.disconnected.connect(_cleanup)
        except Exception:
            _cleanup()


__all__ = [
    "SINGLE_INSTANCE_ENDPOINT",
    "RAISE_SENTINEL",
    "MAX_MESSAGE_BYTES",
    "SingleInstanceGuard",
]
