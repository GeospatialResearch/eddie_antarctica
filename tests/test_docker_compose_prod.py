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
    """No production service publishes a host port; nginx-proxy reaches the ingress over webproxy."""
    services = yaml.safe_load(PROD_COMPOSE_PATH.read_text())["services"]
    assert [name for name, service in services.items() if "ports" in service] == []


def test_only_the_ingress_joins_an_external_network() -> None:
    """The v5 exposure check: one virtual host, on the ingress; every other service is internal to the stack."""
    compose = yaml.safe_load(PROD_COMPOSE_PATH.read_text())
    external = {name for name, network in compose["networks"].items() if network and network.get("external")}
    on_external = [name for name, service in compose["services"].items() if external & set(service.get("networks", []))]
    assert on_external == ["ingress"]
    # environment is a mapping or a list of KEY=value strings
    virtual_hosts = [name for name, service in compose["services"].items()
                     if any(str(key).split("=")[0] == "VIRTUAL_HOST" for key in service.get("environment", []))]
    assert virtual_hosts == ["ingress"]


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
