<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xsi:schemaLocation="http://www.opengis.net/sld
http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd" version="1.0.0">
    <NamedLayer>
        <Name>pskrips_atmosphere_daily_mean_U10V10_2017-02-01</Name>
        <UserStyle>
            <Title>Wind speed</Title>
            <Abstract>Wind speed magnitude derived from the U and V components as sqrt(u^2 + v^2).</Abstract>
            <FeatureTypeStyle>
                <!-- Collapses the two wind-component bands into a single speed band before
                     symbolising. Bands are addressed by position, so this does not depend on
                     how the coverage names them. Needs the WPS extension, which supplies
                     GeoServer's rendering transformations. -->
                <Transformation>
                    <ogc:Function name="ras:Jiffle">
                        <ogc:Function name="parameter">
                            <ogc:Literal>coverage</ogc:Literal>
                        </ogc:Function>
                        <ogc:Function name="parameter">
                            <ogc:Literal>script</ogc:Literal>
                            <ogc:Literal>dest = sqrt(src[0] * src[0] + src[1] * src[1]);</ogc:Literal>
                        </ogc:Function>
                    </ogc:Function>
                </Transformation>
                <Rule>
                    <RasterSymbolizer>
                        <ColorMap type="ramp">
                            <ColorMapEntry color="#440154" quantity="0" label="0 m/s"/>
                            <ColorMapEntry color="#472c7c" quantity="3" label="3 m/s"/>
                            <ColorMapEntry color="#3b528b" quantity="6" label="6 m/s"/>
                            <ColorMapEntry color="#2c728e" quantity="9" label="9 m/s"/>
                            <ColorMapEntry color="#21908d" quantity="12" label="12 m/s"/>
                            <ColorMapEntry color="#28ae80" quantity="15" label="15 m/s"/>
                            <ColorMapEntry color="#5dc963" quantity="18" label="18 m/s"/>
                            <ColorMapEntry color="#abdc32" quantity="21" label="21 m/s"/>
                            <ColorMapEntry color="#fde725" quantity="24" label="24 m/s"/>
                        </ColorMap>
                        <Opacity>1.0</Opacity>
                    </RasterSymbolizer>
                </Rule>
            </FeatureTypeStyle>
        </UserStyle>
    </NamedLayer>
</StyledLayerDescriptor>