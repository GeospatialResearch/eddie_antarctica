# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/eddie_antarctica/blob/master/LICENSE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Guards the public backend root that WPS catalog items hand to Terria."""
import importlib

import pytest

from eddie_antarctica import config


@pytest.mark.parametrize("public_url, expected", [("", "http://localhost:5000"),
                                                  ("https://twin.example.org", "https://twin.example.org/api")])
def test_backend_url_follows_eddie_public_url(monkeypatch: pytest.MonkeyPatch, public_url: str,
                                              expected: str) -> None:
    """Behind the ingress links go to <EDDIE_PUBLIC_URL>/api; without it, to BACKEND_HOST:BACKEND_PORT."""
    monkeypatch.setenv("EDDIE_PUBLIC_URL", public_url)
    monkeypatch.setenv("BACKEND_HOST", "http://localhost")
    monkeypatch.setenv("BACKEND_PORT", "5000")
    importlib.reload(importlib.import_module("eddie.config"))
    backend_url = importlib.reload(config).EnvVariable.BACKEND_URL
    monkeypatch.undo()  # put the real environment's classes back for the tests that follow
    importlib.reload(importlib.import_module("eddie.config"))
    importlib.reload(config)
    assert backend_url == expected
