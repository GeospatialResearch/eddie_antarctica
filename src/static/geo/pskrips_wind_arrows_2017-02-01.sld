<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns:ogc="http://www.opengis.net/ogc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns="http://www.opengis.net/sld"
                       xsi:schemaLocation="http://www.opengis.net/sld
http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd" version="1.0.0">
    <NamedLayer>
        <Name>pskrips_wind_arrows_2017-02-01</Name>
        <UserStyle>
            <Title>Wind arrows</Title>
            <Abstract>Wind as a vector field: one arrow per sampled cell, pointing the way the
                wind blows and coloured by speed.
            </Abstract>
            <FeatureTypeStyle>
                <!-- Turns the raster into one point feature per cell, whose attributes are the
                     coverage's band names. scale=0.05 samples roughly every 20th cell, which is
                     what keeps the arrows far enough apart to read; raise it for denser arrows.

                     IMPORTANT: U10 and V10 below must match the layer's band names exactly, as
                     shown in GeoServer under Layers -> (this layer) -> Publishing -> Coverage
                     Band Details. RasterAsPointCollection names each attribute after the band's
                     description, so if the coverage was published with different band names this
                     style renders nothing until the two names are changed to match (either here,
                     or on the layer). -->
                <Transformation>
                    <ogc:Function name="ras:RasterAsPointCollection">
                        <ogc:Function name="parameter">
                            <ogc:Literal>data</ogc:Literal>
                        </ogc:Function>
                    </ogc:Function>
                </Transformation>
                <Rule>
                    <ogc:Filter>
                        <ogc:PropertyIsBetween>
                            <ogc:PropertyName>GRAY_INDEX</ogc:PropertyName>
                            <ogc:LowerBoundary>
                                <ogc:Literal>-1000</ogc:Literal>
                            </ogc:LowerBoundary>
                            <ogc:UpperBoundary>
                                <ogc:Literal>1000</ogc:Literal>
                            </ogc:UpperBoundary>
                        </ogc:PropertyIsBetween>
                    </ogc:Filter>
                    <PointSymbolizer>
                        <Graphic>
                            <Mark>
                                <WellKnownName>extshape://arrow</WellKnownName>
                                <Fill>
                                    <!-- Viridis over 0-24 m/s, matching the wind speed style. -->
                                    <CssParameter name="fill">
                                        <ogc:Function name="Interpolate">
                                            <ogc:Function name="sqrt">
                                                <ogc:Add>
                                                    <ogc:Mul>
                                                        <ogc:PropertyName>GRAY_INDEX</ogc:PropertyName>
                                                        <ogc:PropertyName>GRAY_INDEX</ogc:PropertyName>
                                                    </ogc:Mul>
                                                    <ogc:Mul>
                                                        <ogc:PropertyName>Band2</ogc:PropertyName>
                                                        <ogc:PropertyName>Band2</ogc:PropertyName>
                                                    </ogc:Mul>
                                                </ogc:Add>
                                            </ogc:Function>
                                            <ogc:Literal>0</ogc:Literal>
                                            <ogc:Literal>#440154</ogc:Literal>
                                            <ogc:Literal>6</ogc:Literal>
                                            <ogc:Literal>#3b528b</ogc:Literal>
                                            <ogc:Literal>12</ogc:Literal>
                                            <ogc:Literal>#21908d</ogc:Literal>
                                            <ogc:Literal>18</ogc:Literal>
                                            <ogc:Literal>#5dc963</ogc:Literal>
                                            <ogc:Literal>24</ogc:Literal>
                                            <ogc:Literal>#fde725</ogc:Literal>
                                            <ogc:Literal>color</ogc:Literal>
                                        </ogc:Function>
                                    </CssParameter>
                                </Fill>
                                <Stroke>
                                    <CssParameter name="stroke">#1a1a1a</CssParameter>
                                    <CssParameter name="stroke-width">0.3</CssParameter>
                                </Stroke>
                            </Mark>
                            <Size>16</Size>
                            <!-- extshape://arrow points north at rotation 0 and SLD rotation runs
                                 clockwise, so the compass bearing the wind blows towards drives it
                                 directly. atan2 is given (east, north) rather than the usual
                                 (y, x) to get a bearing clockwise from north instead of a maths
                                 angle anticlockwise from east. The result is -180..180, which is
                                 already a valid rotation: -90 and 270 are the same heading. -->
                            <Rotation>
                                <ogc:Function name="toDegrees">
                                    <ogc:Function name="atan2">
                                        <ogc:PropertyName>GRAY_INDEX</ogc:PropertyName>
                                        <ogc:PropertyName>Band2</ogc:PropertyName>
                                    </ogc:Function>
                                </ogc:Function>
                            </Rotation>
                        </Graphic>
                    </PointSymbolizer>
                </Rule>
            </FeatureTypeStyle>
        </UserStyle>
    </NamedLayer>
</StyledLayerDescriptor>
