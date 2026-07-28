"""A deterministic, no-output subprocess used only for timeout coverage."""

import time


while True:
    time.sleep(1)
