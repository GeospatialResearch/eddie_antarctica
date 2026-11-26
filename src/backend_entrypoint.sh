#!/bin/bash

# Entrypoint for the backend Flask API
# Used by docker to import environment variables into a docker container without baking them into the image.
# Used when runtime environment variables are not enough, for example, when a config file needs to be written.

# The backend's public root, built as in terriajs/entrypoint.sh: <EDDIE_PUBLIC_URL>/api behind an ingress
BACKEND_URL=$BACKEND_HOST
if [[ ! -z "$BACKEND_PORT" ]]; then
  BACKEND_URL=$BACKEND_URL:$BACKEND_PORT
fi
if [[ -n "$EDDIE_PUBLIC_URL" ]]; then
  BACKEND_URL=${EDDIE_PUBLIC_URL%/}/api
fi
export BACKEND_URL

# List of variables to substitute
ENV_VARS_TO_FILL='$BACKEND_URL'

# Substitute variables and save whole file to variable, sponge is not available to buffer.
SUBBED=`envsubst "$ENV_VARS_TO_FILL" < src/pywps.cfg`
# Overwrite original file.
echo "$SUBBED" > src/pywps.cfg

# Activate python virtual environment
source /venv/bin/activate
# Run production HTTP server with threads (gevent) with an extended timeout
gunicorn --bind 0.0.0.0:5000 --timeout 600 -k gevent eddie.app:app


