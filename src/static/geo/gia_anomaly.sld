<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor xmlns="http://www.opengis.net/sld" version="1.0.0" xmlns:gml="http://www.opengis.net/gml" xmlns:ogc="http://www.opengis.net/ogc" xmlns:sld="http://www.opengis.net/sld">
  <UserLayer>
    <sld:LayerFeatureConstraints>
      <sld:FeatureTypeConstraint/>
    </sld:LayerFeatureConstraints>
    <sld:UserStyle>
      <sld:Name>gia_global_bed_topography_mv1e21_fr1e24_w0p0_weakEarth_t20</sld:Name>
      <sld:FeatureTypeStyle>
        <sld:Rule>
          <sld:RasterSymbolizer>
            <sld:ChannelSelection>
              <sld:GrayChannel>
                <sld:SourceChannelName>1</sld:SourceChannelName>
              </sld:GrayChannel>
            </sld:ChannelSelection>
            <sld:ColorMap type="intervals">
              <sld:ColorMapEntry color="#8a0b25" label="Less than -800.00 m" quantity="-800"/>
              <sld:ColorMapEntry color="#c43b3c" label="-800.00 to -600.00 m" quantity="-600"/>
              <sld:ColorMapEntry color="#e58368" label="-600.00 to -400.00 m" quantity="-400"/>
              <sld:ColorMapEntry color="#f8bfa4" label="-400.00 to -200.00 m" quantity="-200"/>
              <sld:ColorMapEntry color="#fae9df" label="-200.00 to 0.00 m" quantity="0"/>
              <sld:ColorMapEntry color="#e4eef4" label="0.00 to 200.00 m" quantity="200"/>
              <sld:ColorMapEntry color="#b1d5e7" label="200.00 to 400.00 m" quantity="400"/>
              <sld:ColorMapEntry color="#68abd0" label="400.00 to 600.00 m" quantity="600"/>
              <sld:ColorMapEntry color="#327cb7" label="600.00 to 800.00 m" quantity="800"/>
              <sld:ColorMapEntry color="#124984" label="Greater than 800.00 m" quantity="1000000"/>
            </sld:ColorMap>
            </sld:ColorMap>
          </sld:RasterSymbolizer>
        </sld:Rule>
      </sld:FeatureTypeStyle>
    </sld:UserStyle>
  </UserLayer>
</StyledLayerDescriptor>
