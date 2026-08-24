<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0" xmlns:gml="http://www.opengis.net/gml"
                       xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld">
    <UserLayer>
        <sld:LayerFeatureConstraints>
            <sld:FeatureTypeConstraint/>
        </sld:LayerFeatureConstraints>
        <sld:UserStyle>
            <sld:Name>pskrips_atmosphere_daily_mean_t2K_2017-02-01</sld:Name>
            <sld:FeatureTypeStyle>
                <sld:Rule>
                    <sld:RasterSymbolizer>
                        <sld:ChannelSelection>
                            <sld:GrayChannel>
                                <sld:SourceChannelName>1</sld:SourceChannelName>
                            </sld:GrayChannel>
                        </sld:ChannelSelection>
                        <sld:ColorMap type="ramp">
                            <sld:ColorMapEntry color="#440154" label="243.15 K" quantity="243.15"/>
                            <sld:ColorMapEntry color="#472878" label="246.90 K" quantity="246.9"/>
                            <sld:ColorMapEntry color="#3e4a89" label="250.65 K" quantity="250.65"/>
                            <sld:ColorMapEntry color="#31688e" label="254.40 K" quantity="254.4"/>
                            <sld:ColorMapEntry color="#26838e" label="258.15 K" quantity="258.15"/>
                            <sld:ColorMapEntry color="#1e9e89" label="261.90 K" quantity="261.9"/>
                            <sld:ColorMapEntry color="#35b779" label="265.65 K" quantity="265.65"/>
                            <sld:ColorMapEntry color="#6cce59" label="269.40 K" quantity="269.4"/>
                            <sld:ColorMapEntry color="#b4de2c" label="273.15 K" quantity="273.15"/>
                            <sld:ColorMapEntry color="#fde725" label="0" quantity="0"/>
                        </sld:ColorMap>
                    </sld:RasterSymbolizer>
                </sld:Rule>
            </sld:FeatureTypeStyle>
        </sld:UserStyle>
    </UserLayer>
</StyledLayerDescriptor>
