<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0" xmlns:gml="http://www.opengis.net/gml"
                       xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld">
    <UserLayer>
        <sld:LayerFeatureConstraints>
            <sld:FeatureTypeConstraint/>
        </sld:LayerFeatureConstraints>
        <sld:UserStyle>
            <sld:Name>sic_forecast_8w</sld:Name>
            <sld:FeatureTypeStyle>
                <sld:Rule>
                    <sld:RasterSymbolizer>
                        <sld:ChannelSelection>
                            <sld:GrayChannel>
                                <sld:SourceChannelName>1</sld:SourceChannelName>
                            </sld:GrayChannel>
                        </sld:ChannelSelection>
                         <sld:ColorMap type="intervals">
                            <sld:ColorMapEntry color="#08306b" label="Less than 15% SIC" quantity="0.15"/>
                            <sld:ColorMapEntry color="#2171b5" label="15% to 20% SIC" quantity="0.2"/>
                            <sld:ColorMapEntry color="#4292c6" label="20% to 40% SIC" quantity="0.4"/>
                            <sld:ColorMapEntry color="#6baed6" label="40% to 60% SIC" quantity="0.6"/>
                            <sld:ColorMapEntry color="#9ecae1" label="60% to 80% SIC" quantity="0.8"/>
                            <sld:ColorMapEntry color="#ffffff" label="80% to 100% SIC" quantity="1.0"/>
                        </sld:ColorMap>
                    </sld:RasterSymbolizer>
                </sld:Rule>
            </sld:FeatureTypeStyle>
        </sld:UserStyle>
    </UserLayer>
</StyledLayerDescriptor>