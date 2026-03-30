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
   environemnts.

1. From project root, run the command `docker compose up -d` to run the database, backend web servers, and helper
   services.

1. You may inspect the logs of the backend using `docker compose logs -f backend celery_worker`

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