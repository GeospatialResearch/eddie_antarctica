<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xsi:schemaLocation="http://www.opengis.net/sld
http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd" version="1.0.0">
    <NamedLayer>
        <Name>pskrips_wind_arrows_2017-02-01</Name>
        <UserStyle>
            <Title>Wind arrows</Title>
            <Abstract>Wind as a vector field: one arrow per sampled cell, pointing the way the wind blows,
                coloured and lengthened by speed. Clicking a point reports wind speed as sqrt(u^2 + v^2).
            </Abstract>
            <FeatureTypeStyle>
                <Transformation>
                    <ogc:Function name="ras:Jiffle">
                        <ogc:Function name="parameter">
                            <ogc:Literal>coverage</ogc:Literal>
                        </ogc:Function>
                        <ogc:Function name="parameter">
                            <ogc:Literal>script</ogc:Literal>
                            <ogc:Literal>dest = sqrt(src[0] * src[0] + src[1] * src[1]);</ogc:Literal>
                        </ogc:Function>
                        <ogc:Function name="parameter">
                            <ogc:Literal>bandNames</ogc:Literal>
                            <ogc:Literal>wind_speed</ogc:Literal>
                        </ogc:Function>
                    </ogc:Function>
                </Transformation>
                <Rule>
                    <RasterSymbolizer>
                        <Opacity>0.0</Opacity>
                    </RasterSymbolizer>
                </Rule>
                <VendorOption name="inclusion">mapOnly</VendorOption>
            </FeatureTypeStyle>
            <FeatureTypeStyle>
                <Transformation>
                    <ogc:Function name="ras:RasterAsPointCollection">
                        <ogc:Function name="parameter">
                            <ogc:Literal>data</ogc:Literal>
                        </ogc:Function>
                        <ogc:Function name="parameter">
                            <ogc:Literal>scale</ogc:Literal>
                            <ogc:Function name="min">
                                <ogc:Literal>1.0</ogc:Literal>
                                <ogc:Div>
                                    <ogc:Literal>2184696</ogc:Literal>
                                    <ogc:Function name="env">
                                        <ogc:Literal>wms_scale_denominator</ogc:Literal>
                                    </ogc:Function>
                                </ogc:Div>
                            </ogc:Function>
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
                                <WellKnownName>extshape://arrow?hr=3&amp;t=0.45&amp;ab=0.6</WellKnownName>
                                <Fill>
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
                            <Size>
                                <ogc:Mul>
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
                                        <ogc:Literal>12</ogc:Literal>
                                        <ogc:Literal>24</ogc:Literal>
                                        <ogc:Literal>40</ogc:Literal>
                                    </ogc:Function>
                                    <ogc:Function name="min">
                                        <ogc:Literal>4</ogc:Literal>
                                        <ogc:Function name="max">
                                            <ogc:Literal>1</ogc:Literal>
                                            <ogc:Div>
                                                <ogc:Literal>2184696</ogc:Literal>
                                                <ogc:Function name="env">
                                                    <ogc:Literal>wms_scale_denominator</ogc:Literal>
                                                </ogc:Function>
                                            </ogc:Div>
                                        </ogc:Function>
                                    </ogc:Function>
                                </ogc:Mul>
                            </Size>
                            <Rotation>
                                <ogc:Function name="toDegrees">
                                    <ogc:Function name="atan2">
                                        <ogc:PropertyName>Band2</ogc:PropertyName>
                                        <ogc:PropertyName>GRAY_INDEX</ogc:PropertyName>
                                    </ogc:Function>
                                </ogc:Function>
                            </Rotation>
                            <AnchorPoint>
                                <AnchorPointX>0.5</AnchorPointX>
                                <AnchorPointY>0.0</AnchorPointY>
                            </AnchorPoint>
                        </Graphic>
                    </PointSymbolizer>
                    <VendorOption name="inclusion">mapOnly</VendorOption>
                </Rule>
                <Rule>
                    <Title>0 m/s</Title>
                    <PointSymbolizer>
                        <Graphic>
                            <Mark>
                                <WellKnownName>extshape://arrow?hr=3&amp;t=0.45&amp;ab=0.6</WellKnownName>
                                <Fill><CssParameter name="fill">#440154</CssParameter></Fill>
                                <Stroke><CssParameter name="stroke">#1a1a1a</CssParameter><CssParameter name="stroke-width">0.3</CssParameter></Stroke>
                            </Mark>
                            <Size>12</Size>
                        </Graphic>
                    </PointSymbolizer>
                    <VendorOption name="inclusion">legendOnly</VendorOption>
                </Rule>
                <Rule>
                    <Title>6 m/s</Title>
                    <PointSymbolizer>
                        <Graphic>
                            <Mark>
                                <WellKnownName>extshape://arrow?hr=3&amp;t=0.45&amp;ab=0.6</WellKnownName>
                                <Fill><CssParameter name="fill">#3b528b</CssParameter></Fill>
                                <Stroke><CssParameter name="stroke">#1a1a1a</CssParameter><CssParameter name="stroke-width">0.3</CssParameter></Stroke>
                            </Mark>
                            <Size>19</Size>
                        </Graphic>
                    </PointSymbolizer>
                    <VendorOption name="inclusion">legendOnly</VendorOption>
                </Rule>
                <Rule>
                    <Title>12 m/s</Title>
                    <PointSymbolizer>
                        <Graphic>
                            <Mark>
                                <WellKnownName>extshape://arrow?hr=3&amp;t=0.45&amp;ab=0.6</WellKnownName>
                                <Fill><CssParameter name="fill">#21908d</CssParameter></Fill>
                                <Stroke><CssParameter name="stroke">#1a1a1a</CssParameter><CssParameter name="stroke-width">0.3</CssParameter></Stroke>
                            </Mark>
                            <Size>26</Size>
                        </Graphic>
                    </PointSymbolizer>
                    <VendorOption name="inclusion">legendOnly</VendorOption>
                </Rule>
                <Rule>
                    <Title>18 m/s</Title>
                    <PointSymbolizer>
                        <Graphic>
                            <Mark>
                                <WellKnownName>extshape://arrow?hr=3&amp;t=0.45&amp;ab=0.6</WellKnownName>
                                <Fill><CssParameter name="fill">#5dc963</CssParameter></Fill>
                                <Stroke><CssParameter name="stroke">#1a1a1a</CssParameter><CssParameter name="stroke-width">0.3</CssParameter></Stroke>
                            </Mark>
                            <Size>33</Size>
                        </Graphic>
                    </PointSymbolizer>
                    <VendorOption name="inclusion">legendOnly</VendorOption>
                </Rule>
                <Rule>
                    <Title>24+ m/s</Title>
                    <PointSymbolizer>
                        <Graphic>
                            <Mark>
                                <WellKnownName>extshape://arrow?hr=3&amp;t=0.45&amp;ab=0.6</WellKnownName>
                                <Fill><CssParameter name="fill">#fde725</CssParameter></Fill>
                                <Stroke><CssParameter name="stroke">#1a1a1a</CssParameter><CssParameter name="stroke-width">0.3</CssParameter></Stroke>
                            </Mark>
                            <Size>40</Size>
                        </Graphic>
                    </PointSymbolizer>
                    <VendorOption name="inclusion">legendOnly</VendorOption>
                </Rule>
                <VendorOption name="transformFeatureInfo">false</VendorOption>
            </FeatureTypeStyle>
        </UserStyle>
    </NamedLayer>
</StyledLayerDescriptor>
