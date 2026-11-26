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


"""Enum(s) used in the sea ice module."""

from enum import StrEnum


class ChartMethod(StrEnum):
    """
    How a chart reads the forecast at a click, as the ``xarray`` interpolation method of the same name.

    Attributes
    ----------
    LINEAR : str
        Blend the four cell centres around the click, as the smoothed (bilinear) map draws it.
    NEAREST : str
        Read the cell the click is in, as the raw map draws it.
    """

    LINEAR = "linear"
    NEAREST = "nearest"
