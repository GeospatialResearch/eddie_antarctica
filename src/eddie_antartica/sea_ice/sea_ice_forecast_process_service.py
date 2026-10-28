"""Defines the PyWPS process that publishes one week of the sea ice forecast, as Otakaro's MedusaProcessService."""
from pywps import ComplexOutput, Format, LiteralInput, Process, WPSRequest
from pywps.response.execute import ExecuteResponse

from src.eddie_antartica import tasks
from src.eddie_antartica.config import EnvVariable
from src.eddie_antartica.sea_ice.sea_ice_forecast_layer import catalog_item


class SeaIceForecastProcessService(Process):
    """Class representing a WebProcessingService process that maps one week of the sea ice forecast."""

    def __init__(self) -> None:
        """Define inputs and outputs of the WPS process, and assign process handler."""
        inputs = [
            LiteralInput("week", "Forecast week (1-8)", data_type="integer", default=8,
                         allowed_values=list(range(1, 9))),
        ]
        outputs = [
            ComplexOutput("seaIceForecast", "Sea ice concentration forecast",
                          supported_formats=[Format("application/vnd.terriajs.catalog-member+json")]),
        ]
        super().__init__(
            self._handler,
            identifier="sea_ice_forecast",
            title="Sea ice concentration forecast",
            abstract="Map one week of the 8-week sea ice concentration forecast. Click the map to chart all 8 weeks.",
            inputs=inputs,
            outputs=outputs,
            store_supported=True
        )

    @staticmethod
    def _handler(request: WPSRequest, response: ExecuteResponse) -> None:
        """
        Process handler: publish the requested week with a Celery task, then hand Terria the layer.

        Parameters
        ----------
        request : WPSRequest
            The WPS request, containing input parameters.
        response : ExecuteResponse
            The WPS response, containing output data.
        """
        week = request.inputs["week"][0].data
        date = tasks.publish_sea_ice_forecast_week.delay(week).get()
        response.outputs["seaIceForecast"].data = catalog_item(
            week, date,
            geoserver_url=f"{EnvVariable.GEOSERVER_HOST}:{EnvVariable.GEOSERVER_PORT}",
            backend_url=f"{EnvVariable.BACKEND_HOST}:{EnvVariable.BACKEND_PORT}",
        )
