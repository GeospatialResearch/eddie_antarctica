Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau

# EDDIE Template

![image](paper/Capture2024.PNG)

## Introduction
A template repository to be used to quickly start new EDDIE Digital Twin applications.

## Basic running instructions

The following list defines the basic steps required to set up and run the digital twin.

We recommend basing your application on this template and modifying it to suit your needs.
You can find a working example of an EDDIE application based on this template at our 
[Flood Resilience Digital Twin](https://github.com/GeospatialResearch/eddie_floodresilience) repository.

### Requirements

* [Docker](https://www.docker.com/)
* [CUDA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

### Officially Supported Operating Systems

* Windows 10/11
* Ubuntu 22.04

Note: Other Linux-based operating systems are likely to work but have not been as thoroughly tested.

### Unsupported Operating Systems

We unfortunately do not support MacOS. Please
see [Digital-Twins#358](https://github.com/GeospatialResearch/Digital-Twins/issues/358) for updates or to contribute.

### Required Credentials:

Create API keys for each of these services. You may need to create an account and log in

* [Stats NZ API Key](https://datafinder.stats.govt.nz/my/api/)
* [LINZ API Key](https://data.linz.govt.nz/my/api/)
* [MFE API Key](https://data.mfe.govt.nz/my/api/)
* [NIWA Application API Key](https://developer.niwa.co.nz/) - Create an app that has the Tide API enabled.
* [Cesium Ion Access Token](https://ion.cesium.com/tokens)

### Starting the Digital Twin application (localhost)

1. Clone this repository to your local machine.

1. Create a file called `api_keys.env`, copy the contents of `api_keys.env.template` and fill in the blank values with
   API credentials from the above links.

1. Create a file called `.env` in the project root, copy the contents of `.env.template` and fill in all blank fields
   unless a comment says you can leave it blank.
   Blank fields to fill in include fields such as `CESIUM_ACCESS_TOKEN` and `POSTGRES_PASSWORD`. `POSTGRES_PASSWORD` can
   be a password of your choosing. You may modify other configuration variables if needed to suit particular deployment
   environments.

1. From project root, run the command `docker compose up -d` to run the database, backend web servers, and helper
   services.

1. You may inspect the logs of the backend using `docker compose logs -f backend celery_worker`

### Setting up the sea ice forecast

The sea ice forecast runs in the Celery worker. It needs a Copernicus key and the model's files, neither of
which is in this repository.

1. Create a [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/) account, accept the licence on the
   [ERA5 hourly data on single levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels)
   dataset page, then uncomment `CDSAPI_URL` and `CDSAPI_KEY` in `api_keys.env` and fill in your API key. Sea ice
   concentration comes from NSIDC and needs no key.

1. Get these four files from the reference code (the sea ice model's source) and put them in a folder named
   `sic_model` next to `docker-compose.yml`. They are the only files you add by hand; the weekly inputs and forecasts
   are downloaded and written by the worker.
   * `SIC_production_checkpoint.pt`, `multi_mesh_bundle_K5.npz` and `train_stats.npz`
   * `sic_climatology.nc`, from the reference code's `data/historical/`

   The worker reads this folder directly (read-only), so files added or replaced there are used on the next run.

1. The worker runs the forecast every Monday at 03:00 New Zealand time. To run it now instead of waiting:
   ```bash
   docker compose exec celery_worker /venv/bin/celery -A src.eddie_antartica.tasks call src.eddie_antartica.tasks.refresh_sea_ice_forecast
   docker compose logs -f celery_worker
   ```
   This downloads the last six weeks of inputs to `/stored_data/sea_ice_inputs`, writes the forecast to
   `/stored_data/sea_ice_forecasts/sic_forecast_8w_<first week>.nc` and publishes it to GeoServer as `sic_forecast_8w`.

   The "Sea ice concentration forecast" process in Terria and its point chart read the newest file in
   `sea_ice_forecasts`, falling back to `FORECAST_NETCDF_LATEST` until the first forecast is written.

The in-container paths are already set in `.env.docker-override`. The matching values in `.env` are only used when
running the code outside Docker.

## Using the Digital Twin application

1. With the docker compose application running, the default web address is <http://localhost:3001> to view the web
   application.
   * To perform custom modelling, "Explore map data" has configurable models.
1. The API is available by default on <http://localhost:5000>.
   Visit <https://geospatialresearch.github.io/Digital-Twins/swagger> for API documentation.

## Contributing

If you are interested in contributing to this project, please see [our contributing page here](CONTRIBUTING.md).

## Support

If you run into an issue, bug, or need help with the software, please consider opening an issue or discussion, this will
be the best way to reach us.

## Setup for FReDT project software developers

[Visit our wiki](https://github.com/GeospatialResearch/Digital-Twins/wiki/) for some instructions on how to set up your
development machine to work with on the FReDT project.
