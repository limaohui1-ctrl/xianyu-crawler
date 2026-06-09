import warnings


class NullNotifier:
    def show_toast(self, *args, **kwargs):
        return None


class LazyToastNotifier:
    def __init__(self):
        self._notifier = None
        self._failed = False

    def show_toast(self, *args, **kwargs):
        notifier = self._load_notifier()
        return notifier.show_toast(*args, **kwargs)

    def _load_notifier(self):
        if self._notifier is not None:
            return self._notifier
        if self._failed:
            return NullNotifier()

        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="pkg_resources is deprecated as an API.*",
                    category=UserWarning,
                )
                from win10toast import ToastNotifier
            self._notifier = ToastNotifier()
        except Exception:
            self._failed = True
            self._notifier = NullNotifier()

        return self._notifier


def create_notifier():
    return LazyToastNotifier()
