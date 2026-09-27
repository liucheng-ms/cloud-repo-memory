import os

import pytest

from support import Fixture


@pytest.fixture
def fixture():
    if os.name != "nt":
        pytest.skip("BLOCKED: fixed NTFS Windows fixture required")
    owned = Fixture()
    try:
        yield owned
    finally:
        owned.clean()
