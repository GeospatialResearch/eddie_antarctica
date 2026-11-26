# -*- coding: utf-8 -*-
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
"""The package is eddie_antarctica everywhere; a branch from before the rename brings the old spelling back."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKED = ["src", "tests", "docker", "terriajs", "docker-compose.yml", "docker-compose-dev.yml",
           "docker-compose-prod.yml", "environment.yml", "pyproject.toml", ".flake8", ".pylintrc", "README.md"]


def test_no_file_uses_the_old_package_spelling() -> None:
    """Fails with the files to fix after rebasing an old branch: imports become ``eddie_antarctica.*``."""
    paths = [path for name in CHECKED for path in ([ROOT / name] if (ROOT / name).is_file() else
                                                    (ROOT / name).rglob("*"))]
    old_name = "eddie_" + "antartica"  # split, so this file does not match itself
    old = [str(path.relative_to(ROOT)) for path in paths if path.is_file() and path.suffix not in {".nc", ".tif", ".pyc"}
           and old_name in path.read_text(errors="ignore")]
    assert old == []
