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

"""Guards docker-compose-prod.yml: no host ports, and the data services stay off the shared webproxy network."""
import pathlib

import yaml

PROD_COMPOSE_PATH = pathlib.Path(__file__).resolve().parent.parent / "docker-compose-prod.yml"


def test_prod_publishes_no_host_ports() -> None:
    """No production service publishes a host port; nginx-proxy reaches the public ones over webproxy."""
    services = yaml.safe_load(PROD_COMPOSE_PATH.read_text())["services"]
    assert [name for name, service in services.items() if "ports" in service] == []
    # The backend image exposes no port, so without this nginx-proxy falls back to port 80 and answers 502.
    assert services["backend"]["environment"]["VIRTUAL_PORT"] == "5000"


def test_prod_keeps_data_services_off_webproxy() -> None:
    """Postgres, Redis and the Celery worker are only on the stack's own network, not the shared webproxy."""
    compose = yaml.safe_load(PROD_COMPOSE_PATH.read_text())
    assert compose["networks"].get("default", {}).get("name") != "webproxy"
    for name in ("db_postgres", "message_broker", "celery_worker"):
        assert "webproxy" not in compose["services"][name].get("networks", []), name


def test_prod_data_services_need_a_password_and_sit_on_an_internal_network() -> None:
    """The static half of the v5 exposure checks that holds without an ingress: Redis wants a password, and
    Postgres and Redis are only on networks with no egress."""
    compose = yaml.safe_load(PROD_COMPOSE_PATH.read_text())
    assert "--requirepass" in compose["services"]["message_broker"]["command"]
    for name in ("backend", "celery_worker"):
        host = compose["services"][name]["environment"]["MESSAGE_BROKER_HOST"]
        assert host == ":${MESSAGE_BROKER_PASSWORD}@message_broker", name
    for name in ("db_postgres", "message_broker"):
        networks = compose["services"][name]["networks"]
        assert all(compose["networks"][network].get("internal") for network in networks), name
