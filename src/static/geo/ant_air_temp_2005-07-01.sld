<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0" xmlns:gml="http://www.opengis.net/gml"
                       xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld">
    <UserLayer>
        <sld:LayerFeatureConstraints>
            <sld:FeatureTypeConstraint/>
        </sld:LayerFeatureConstraints>
        <sld:UserStyle>
            <sld:Name>ant_air_temp_2005-07-01</sld:Name>
            <sld:FeatureTypeStyle>
                <sld:Rule>
                    <sld:RasterSymbolizer>
                        <sld:ChannelSelection>
                            <sld:GrayChannel>
                                <sld:SourceChannelName>1</sld:SourceChannelName>
                            </sld:GrayChannel>
                        </sld:ChannelSelection>
                        <sld:ColorMap type="ramp">
                            <sld:ColorMapEntry color="#440154" label="-900" quantity="-900"/>
                            <sld:ColorMapEntry color="#472878" label="-800" quantity="-800"/>
                            <sld:ColorMapEntry color="#3e4a89" label="-700" quantity="-700"/>
                            <sld:ColorMapEntry color="#31688e" label="-600" quantity="-600"/>
                            <sld:ColorMapEntry color="#26838e" label="-500" quantity="-500"/>
                            <sld:ColorMapEntry color="#1e9e89" label="-400" quantity="-400"/>
                            <sld:ColorMapEntry color="#35b779" label="-300" quantity="-300"/>
                            <sld:ColorMapEntry color="#6cce59" label="-200" quantity="-200"/>
                            <sld:ColorMapEntry color="#b4de2c" label="-100" quantity="-100"/>
                            <sld:ColorMapEntry color="#fde725" label="0" quantity="0"/>
                        </sld:ColorMap>
                    </sld:RasterSymbolizer>
                </sld:Rule>
            </sld:FeatureTypeStyle>
        </sld:UserStyle>
    </UserLayer>
</StyledLayerDescriptor>
