<?xml version="1.0" encoding="UTF-8"?>
<sld:StyledLayerDescriptor xmlns:sld="http://www.opengis.net/sld" xmlns="http://www.opengis.net/sld"
                           xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc"
                           version="1.0.0">
    <sld:NamedLayer>
        <sld:Name>Default Styler</sld:Name>
        <sld:UserStyle>
            <sld:Name>Default Styler</sld:Name>
            <sld:Title>U and V Band Mapping</sld:Title>
            <sld:FeatureTypeStyle>
                <sld:Name>name</sld:Name>
                <sld:Rule>
                    <sld:RasterSymbolizer>
                        <sld:ChannelSelection>
                            <sld:RedChannel>
                                <sld:SourceChannelName>1</sld:SourceChannelName>
                            </sld:RedChannel>
                            <sld:GreenChannel>
                                <sld:SourceChannelName>2</sld:SourceChannelName>
                            </sld:GreenChannel>
                            <sld:BlueChannel>
                                <sld:SourceChannelName>2</sld:SourceChannelName>
                            </sld:BlueChannel>
                        </sld:ChannelSelection>
                    </sld:RasterSymbolizer>
                </sld:Rule>
            </sld:FeatureTypeStyle>
        </sld:UserStyle>
    </sld:NamedLayer>
</sld:StyledLayerDescriptor>

