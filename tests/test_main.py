import signal
import unittest

from lightupthenight import __main__ as entry


class SignalHandlerTests(unittest.TestCase):
    def test_sigterm_is_turned_into_keyboard_interrupt(self) -> None:
        previous = signal.getsignal(signal.SIGTERM)
        try:
            entry.install_signal_handlers()
            handler = signal.getsignal(signal.SIGTERM)
            self.assertTrue(callable(handler))
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGTERM, None)
        finally:
            signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    unittest.main()
